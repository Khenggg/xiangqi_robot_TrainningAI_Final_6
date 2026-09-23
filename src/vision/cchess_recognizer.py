"""
=============================================================================
=== FILE: cchess_recognizer.py ===
=== Nhận diện bàn cờ và quân cờ tướng bằng ONNX Models ===
=== Nguồn model: TheOne1006/chinese-chess-recognition ===
=============================================================================
"""

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Union

import cv2
import numpy as np
import onnxruntime as ort

# Danh sách tên các điểm mốc (keypoints) 4 góc bàn cờ
BONE_NAMES = ["A0", "A8", "J0", "J8"]

# 16 class của model classification
CLASS_NAMES = [
    "point",
    "other",
    "red_king",
    "red_advisor",
    "red_bishop",
    "red_knight",
    "red_rook",
    "red_cannon",
    "red_pawn",
    "black_king",
    "black_advisor",
    "black_bishop",
    "black_knight",
    "black_rook",
    "black_cannon",
    "black_pawn",
]

# Ký hiệu ngắn FEN-like
CLASS_TO_SHORT = {
    "point": ".",
    "other": "x",
    "red_king": "K",
    "red_advisor": "A",
    "red_bishop": "B",
    "red_knight": "N",
    "red_rook": "R",
    "red_cannon": "C",
    "red_pawn": "P",
    "black_king": "k",
    "black_advisor": "a",
    "black_bishop": "b",
    "black_knight": "n",
    "black_rook": "r",
    "black_cannon": "c",
    "black_pawn": "p",
}

# Mapping sang ký hiệu nội bộ của xiangqi robot project:
# Ví dụ: K -> r_K, B -> r_E (Elephant/Tượng), b -> b_E, . -> .
SHORT_TO_PROJECT = {
    ".": ".",
    "x": "x",
    "K": "r_K",
    "A": "r_A",
    "B": "r_E",
    "N": "r_N",
    "R": "r_R",
    "C": "r_C",
    "P": "r_P",
    "k": "b_K",
    "a": "b_A",
    "b": "b_E",
    "n": "b_N",
    "r": "b_R",
    "c": "b_C",
    "p": "b_P",
}

PROJECT_TO_SHORT = {v: k for k, v in SHORT_TO_PROJECT.items() if k not in (".", "x")}
PROJECT_TO_SHORT["."] = "."
PROJECT_TO_SHORT["x"] = "x"


def validate_board_sanity(board: List[List[str]]) -> Tuple[bool, Optional[str]]:
    """Kiểm tra tính hợp lệ cơ bản của bàn cờ tướng (Sanity check).
    
    Phát hiện các trạng thái bất thường / lỗi nhận diện như:
      - Thiếu hoặc thừa Tướng (Red King 'r_K', Black King 'b_K')
      - Tướng nằm ngoài Cung (Palace)
      - Số lượng quân vượt quá giới hạn luật cờ (tối đa 16 quân mỗi bên)
    """
    if not board or len(board) != 10 or any(len(r) != 9 for r in board):
        return False, "Kích thước ma trận bàn cờ không hợp lệ (phải là 10 hàng x 9 cột)"

    r_kings = []
    b_kings = []
    red_count = 0
    black_count = 0

    for r in range(10):
        for c in range(9):
            p = board[r][c]
            if p == "r_K":
                r_kings.append((c, r))
                red_count += 1
            elif p == "b_K":
                b_kings.append((c, r))
                black_count += 1
            elif p.startswith("r"):
                red_count += 1
            elif p.startswith("b"):
                black_count += 1

    if len(r_kings) != 1:
        return False, f"Bàn cờ không hợp lệ: Yêu cầu đúng 1 Tướng Đỏ (r_K), phát hiện {len(r_kings)}"
    if len(b_kings) != 1:
        return False, f"Bàn cờ không hợp lệ: Yêu cầu đúng 1 Tướng Đen (b_K), phát hiện {len(b_kings)}"

    # Cung Tướng Đỏ: cột 3..5, hàng 7..9
    rk_c, rk_r = r_kings[0]
    if not (3 <= rk_c <= 5 and 7 <= rk_r <= 9):
        return False, f"Tướng Đỏ ở vị trí ({rk_c}, {rk_r}) ngoài Cung (cột 3-5, hàng 7-9)"

    # Cung Tướng Đen: cột 3..5, hàng 0..2
    bk_c, bk_r = b_kings[0]
    if not (3 <= bk_c <= 5 and 0 <= bk_r <= 2):
        return False, f"Tướng Đen ở vị trí ({bk_c}, {bk_r}) ngoài Cung (cột 3-5, hàng 0-2)"

    if red_count > 16:
        return False, f"Số lượng quân Đỏ vượt quá giới hạn ({red_count} > 16)"
    if black_count > 16:
        return False, f"Số lượng quân Đen vượt quá giới hạn ({black_count} > 16)"

    return True, None


@dataclass
class RecognitionQuality:
    """Detailed quality assessment of a CChess recognition output."""
    is_valid: bool
    corner_quality_ok: bool = True
    geometry_quality_ok: bool = True
    layout_quality_ok: bool = True
    board_sanity_ok: bool = True
    min_kpt_score: float = 0.0
    mean_kpt_score: float = 0.0
    mean_layout_conf: float = 0.0
    mean_piece_conf: float = 0.0
    error: Optional[str] = None


def check_recognition_quality(
    result: Dict,
    img_shape: Optional[Tuple[int, int]] = None,
    min_kpt_conf: float = 0.08,
    mean_kpt_conf: float = 0.15,
    min_layout_conf: float = 0.25,
    min_piece_conf: float = 0.35,
) -> RecognitionQuality:
    """Kiểm tra toàn diện chất lượng nhận diện:
    1. Điểm tin cậy (confidence) của 4 góc bàn cờ (SimCC)
    2. Tính hợp lệ hình học (quadrilateral geometry, bounds, lồi, thứ tự góc)
    3. Điểm tin cậy layout classification (toàn bàn cờ & các ô có quân)
    4. Kiểm tra tính hợp lệ cờ tướng (Sanity check: Tướng, Cung, số lượng quân)
    """
    if not result or not result.get("success"):
        return RecognitionQuality(
            is_valid=False,
            error=result.get("error") if result else "Kết quả nhận diện trống hoặc báo lỗi",
        )

    # 1. Kiểm tra 4 góc keypoint scores
    kpts = result.get("keypoints") if result.get("keypoints") is not None else result.get("corners")
    kpt_scores = result.get("keypoint_scores") if result.get("keypoint_scores") is not None else result.get("corner_scores")
    if kpts is None or kpt_scores is None or len(kpts) != 4 or len(kpt_scores) != 4:
        return RecognitionQuality(
            is_valid=False,
            corner_quality_ok=False,
            error="Không đủ 4 keypoints góc bàn cờ",
        )

    min_kpt = float(np.min(kpt_scores))
    mean_kpt = float(np.mean(kpt_scores))
    if min_kpt < min_kpt_conf or mean_kpt < mean_kpt_conf:
        return RecognitionQuality(
            is_valid=False,
            corner_quality_ok=False,
            min_kpt_score=min_kpt,
            mean_kpt_score=mean_kpt,
            error=(
                f"Độ tin cậy góc bàn cờ quá thấp (min={min_kpt:.3f} < {min_kpt_conf}, "
                f"mean={mean_kpt:.3f} < {mean_kpt_conf})"
            ),
        )

    # 2. Kiểm tra hình học góc bàn cờ (Geometry Sanity)
    # CChess keypoint order: [0]=A0, [1]=A8, [2]=J0, [3]=J8
    # Clockwise contour order: P0=A0, P1=A8, P2=J8, P3=J0
    P0 = np.array(kpts[0], dtype=np.float32)
    P1 = np.array(kpts[1], dtype=np.float32)
    P2 = np.array(kpts[3], dtype=np.float32)
    P3 = np.array(kpts[2], dtype=np.float32)

    if img_shape is not None:
        img_h, img_w = img_shape[:2]
        for i, pt in enumerate([P0, P1, P2, P3]):
            x, y = float(pt[0]), float(pt[1])
            if x < -0.05 * img_w or x > 1.05 * img_w or y < -0.05 * img_h or y > 1.05 * img_h:
                return RecognitionQuality(
                    is_valid=False,
                    geometry_quality_ok=False,
                    min_kpt_score=min_kpt,
                    mean_kpt_score=mean_kpt,
                    error=f"Góc P{i} nằm ngoài biên ảnh ({x:.1f}, {y:.1f})",
                )
        # Minimum span check
        min_w = img_w * 0.10
        min_h = img_h * 0.10
        if np.linalg.norm(P1 - P0) < min_w or np.linalg.norm(P2 - P3) < min_w:
            return RecognitionQuality(
                is_valid=False,
                geometry_quality_ok=False,
                min_kpt_score=min_kpt,
                mean_kpt_score=mean_kpt,
                error="Chiều rộng bàn cờ quá nhỏ so với khung hình",
            )
        if np.linalg.norm(P3 - P0) < min_h or np.linalg.norm(P2 - P1) < min_h:
            return RecognitionQuality(
                is_valid=False,
                geometry_quality_ok=False,
                min_kpt_score=min_kpt,
                mean_kpt_score=mean_kpt,
                error="Chiều cao bàn cờ quá nhỏ so với khung hình",
            )

    # Convex quadrilateral check (tích có hướng các cạnh liên tiếp phải cùng dấu)
    poly = [P0, P1, P2, P3]
    cross_signs = []
    for i in range(4):
        v1 = poly[(i + 1) % 4] - poly[i]
        v2 = poly[(i + 2) % 4] - poly[(i + 1) % 4]
        cross = v1[0] * v2[1] - v1[1] * v2[0]
        cross_signs.append(cross)

    all_pos = all(c > 0 for c in cross_signs)
    all_neg = all(c < 0 for c in cross_signs)
    if not (all_pos or all_neg):
        return RecognitionQuality(
            is_valid=False,
            geometry_quality_ok=False,
            min_kpt_score=min_kpt,
            mean_kpt_score=mean_kpt,
            error="4 góc không tạo thành tứ giác lồi hợp lệ (bị xoắn hoặc tự cắt)",
        )

    # Area ratio check (tỷ lệ diện tích tứ giác so với bounding rect)
    quad_pts = np.array([P0, P1, P2, P3], dtype=np.float32)
    quad_area = cv2.contourArea(quad_pts)
    _, _, bw, bh = cv2.boundingRect(quad_pts)
    bbox_area = max(bw * bh, 1.0)
    area_ratio = quad_area / bbox_area
    if area_ratio < 0.35:
        return RecognitionQuality(
            is_valid=False,
            geometry_quality_ok=False,
            min_kpt_score=min_kpt,
            mean_kpt_score=mean_kpt,
            error=f"Tứ giác góc bàn cờ bị biến dạng quá mức (area_ratio={area_ratio:.2f} < 0.35)",
        )

    # 3. Kiểm tra độ tin cậy layout
    confs = result.get("confidence")
    board = result.get("board")
    mean_layout_conf = 1.0
    mean_piece_conf = 1.0

    if confs is not None:
        if len(confs) != 10 or any(len(r) != 9 for r in confs):
            return RecognitionQuality(
                is_valid=False,
                layout_quality_ok=False,
                error="Ma trận độ tin cậy layout không hợp lệ",
            )

        flat_confs = [c for r in confs for c in r]
        mean_layout_conf = float(np.mean(flat_confs)) if flat_confs else 0.0

        piece_confs = []
        if board and len(board) == 10:
            for r in range(10):
                for c in range(9):
                    if board[r][c] not in (".", "x", ""):
                        piece_confs.append(confs[r][c])
        mean_piece_conf = float(np.mean(piece_confs)) if piece_confs else mean_layout_conf

        if piece_confs and mean_piece_conf < min_piece_conf:
            return RecognitionQuality(
                is_valid=False,
                layout_quality_ok=False,
                min_kpt_score=min_kpt,
                mean_kpt_score=mean_kpt,
                mean_layout_conf=mean_layout_conf,
                mean_piece_conf=mean_piece_conf,
                error=f"Độ tin cậy phân loại quân cờ quá thấp (mean={mean_piece_conf:.3f} < {min_piece_conf})",
            )
        if mean_layout_conf < min_layout_conf:
            return RecognitionQuality(
                is_valid=False,
                layout_quality_ok=False,
                min_kpt_score=min_kpt,
                mean_kpt_score=mean_kpt,
                mean_layout_conf=mean_layout_conf,
                mean_piece_conf=mean_piece_conf,
                error=f"Độ tin cậy phân loại toàn bàn cờ quá thấp (mean={mean_layout_conf:.3f} < {min_layout_conf})",
            )

    # 4. Kiểm tra tính hợp lệ bàn cờ (Board Sanity)
    if board is not None:
        is_sane, sanity_err = validate_board_sanity(board)
        if not is_sane:
            return RecognitionQuality(
                is_valid=False,
                board_sanity_ok=False,
                min_kpt_score=min_kpt,
                mean_kpt_score=mean_kpt,
                mean_layout_conf=mean_layout_conf,
                mean_piece_conf=mean_piece_conf,
                error=sanity_err,
            )

    return RecognitionQuality(
        is_valid=True,
        min_kpt_score=min_kpt,
        mean_kpt_score=mean_kpt,
        mean_layout_conf=mean_layout_conf,
        mean_piece_conf=mean_piece_conf,
    )


def validate_recognition_result(
    result: Dict,
    img_shape: Optional[Tuple[int, int]] = None,
    min_kpt_conf: float = 0.08,
    mean_kpt_conf: float = 0.15,
    min_layout_conf: float = 0.25,
    min_piece_conf: float = 0.35,
) -> Tuple[bool, Optional[str]]:
    """Quality gate wrapper returning (is_valid, error_message)."""
    quality = check_recognition_quality(
        result,
        img_shape=img_shape,
        min_kpt_conf=min_kpt_conf,
        mean_kpt_conf=mean_kpt_conf,
        min_layout_conf=min_layout_conf,
        min_piece_conf=min_piece_conf,
    )
    return quality.is_valid, quality.error


class CChessRecognizer:
    """Hệ thống nhận diện bàn cờ và phân loại 90 vị trí quân cờ tướng bằng ONNX."""

    def __init__(
        self,
        pose_model_path: Union[str, Path],
        layout_model_path: Union[str, Path],
        use_gpu: bool = False,
        min_kpt_conf: float = 0.08,
        mean_kpt_conf: float = 0.15,
        min_layout_conf: float = 0.25,
        min_piece_conf: float = 0.35,
    ):
        """
        Args:
            pose_model_path: Đường dẫn model RTMPose 4 keypoints (.onnx)
            layout_model_path: Đường dẫn model Layout classifier (.onnx)
            use_gpu: Cho phép sử dụng CUDA Execution Provider nếu có
            min_kpt_conf: Ngưỡng score tối thiểu cho từng keypoint SimCC (default: 0.08)
            mean_kpt_conf: Ngưỡng trung bình keypoint score SimCC (default: 0.15)
            min_layout_conf: Ngưỡng confidence trung bình layout (default: 0.25)
            min_piece_conf: Ngưỡng confidence trung bình cho các ô có quân (default: 0.35)
        """
        self.pose_model_path = str(pose_model_path)
        self.layout_model_path = str(layout_model_path)
        self.min_kpt_conf = float(min_kpt_conf)
        self.mean_kpt_conf = float(mean_kpt_conf)
        self.min_layout_conf = float(min_layout_conf)
        self.min_piece_conf = float(min_piece_conf)

        providers = ["CPUExecutionProvider"]
        if use_gpu and "CUDAExecutionProvider" in ort.get_available_providers():
            providers.insert(0, "CUDAExecutionProvider")

        # 1. Khởi tạo RTMPose Session
        self.pose_session = ort.InferenceSession(self.pose_model_path, providers=providers)
        self.pose_input_name = self.pose_session.get_inputs()[0].name
        self.pose_input_size = (256, 256)  # (w, h)
        self.pose_padding = 1.25

        # 2. Khởi tạo Layout Classifier Session
        self.layout_session = ort.InferenceSession(self.layout_model_path, providers=providers)
        self.layout_input_name = self.layout_session.get_inputs()[0].name
        self.layout_input_size = (280, 315)  # (w, h)
        self.layout_crop_size = (400, 450)  # (w, h)
        self.rectified_board_size = (450, 500)  # (w, h)

        # Chuẩn hóa ImageNet
        self.norm_mean = np.array([123.675, 116.28, 103.53], dtype=np.float32)
        self.norm_std = np.array([58.395, 57.12, 57.375], dtype=np.float32)

    # -------------------------------------------------------------------------
    # 1. POSE ESTIMATION (Detect 4 Corners: A0, A8, J0, J8)
    # -------------------------------------------------------------------------

    @staticmethod
    def _rotate_point(pt: np.ndarray, angle_rad: float) -> np.ndarray:
        sn, cs = np.sin(angle_rad), np.cos(angle_rad)
        return np.array([[cs, -sn], [sn, cs]]) @ pt

    @staticmethod
    def _get_3rd_point(a: np.ndarray, b: np.ndarray) -> np.ndarray:
        direction = a - b
        return b + np.r_[-direction[1], direction[0]]

    def _get_warp_matrix(
        self,
        center: np.ndarray,
        scale: np.ndarray,
        output_size: Tuple[int, int],
        inv: bool = False,
    ) -> np.ndarray:
        src_w, src_h = scale[:2]
        dst_w, dst_h = output_size[:2]

        src_dir = np.array([src_w * -0.5, 0.0])
        dst_dir = np.array([dst_w * -0.5, 0.0])

        src = np.zeros((3, 2), dtype=np.float32)
        src[0, :] = center
        src[1, :] = center + src_dir

        dst = np.zeros((3, 2), dtype=np.float32)
        dst[0, :] = [dst_w * 0.5, dst_h * 0.5]
        dst[1, :] = np.array([dst_w * 0.5, dst_h * 0.5]) + dst_dir

        src[2, :] = self._get_3rd_point(src[0, :], src[1, :])
        dst[2, :] = self._get_3rd_point(dst[0, :], dst[1, :])

        if inv:
            return cv2.getAffineTransform(np.float32(dst), np.float32(src))
        return cv2.getAffineTransform(np.float32(src), np.float32(dst))

    def _get_warp_size_with_input_size(
        self, center: np.ndarray, scale: np.ndarray, inv: bool = False
    ) -> np.ndarray:
        w, h = self.pose_input_size
        scale_w, scale_h = scale
        aspect_ratio = w / h
        if scale_w > scale_h * aspect_ratio:
            scale_adjusted = [scale_w, scale_w / aspect_ratio]
        else:
            scale_adjusted = [scale_h * aspect_ratio, scale_h]

        return self._get_warp_matrix(
            center, np.array(scale_adjusted, dtype=np.float32), self.pose_input_size, inv=inv
        )

    def detect_board_corners(
        self, frame_bgr: np.ndarray
    ) -> Tuple[np.ndarray, np.ndarray]:
        """Phát hiện 4 góc bàn cờ (A0, A8, J0, J8).

        Returns:
            keypoints: np.ndarray shape (4, 2) toạ độ pixel [x, y]
            scores: np.ndarray shape (4,) độ tin cậy [0..1]
        """
        h, w = frame_bgr.shape[:2]
        center = np.array([w / 2.0, h / 2.0], dtype=np.float32)
        scale = np.array([w, h], dtype=np.float32) * self.pose_padding

        # 1. Top-down affine warp to 256x256
        warp_mat = self._get_warp_size_with_input_size(center, scale, inv=False)
        dst_img = cv2.warpAffine(frame_bgr, warp_mat, self.pose_input_size, flags=cv2.INTER_LINEAR)

        # 2. Normalization
        img_rgb = cv2.cvtColor(dst_img, cv2.COLOR_BGR2RGB)
        img_norm = (img_rgb - self.norm_mean) / self.norm_std
        inp = np.transpose(img_norm.astype(np.float32), (2, 0, 1))
        inp = np.expand_dims(inp, axis=0)

        # 3. ONNX Inference
        simcc_x, simcc_y = self.pose_session.run(None, {self.pose_input_name: inp})

        # 4. SimCC decode
        x_indices = np.argmax(simcc_x[0], axis=1)
        y_indices = np.argmax(simcc_y[0], axis=1)
        input_w, input_h = self.pose_input_size
        x_coords = (x_indices / (input_w * 2)) * input_w
        y_coords = (y_indices / (input_h * 2)) * input_h
        scores = np.max(simcc_x[0], axis=1) * np.max(simcc_y[0], axis=1)

        # 5. Transform back to original frame coordinates
        target_coords = np.stack([x_coords, y_coords], axis=1)
        warp_mat_inv = self._get_warp_size_with_input_size(center, scale, inv=True)
        ones = np.ones((len(target_coords), 1), dtype=np.float32)
        target_coords_homo = np.hstack([target_coords, ones])
        original_keypoints = target_coords_homo @ warp_mat_inv.T

        return original_keypoints, scores

    # -------------------------------------------------------------------------
    # 2. PERSPECTIVE WARPING TO RECTIFIED BOARD
    # -------------------------------------------------------------------------

    def extract_rectified_board(
        self, frame_bgr: np.ndarray, keypoints: np.ndarray
    ) -> Tuple[np.ndarray, np.ndarray]:
        """Cắt và nắn bàn cờ thành góc nhìn vuông góc (450x500).

        keypoints: 4 điểm [A0, A8, J0, J8]
        Returns:
            warped_bgr: ảnh bàn cờ đã nắn phẳng kích thước (500, 450, 3)
            matrix: ma trận phối cảnh 3x3
        """
        src = np.float32(keypoints)
        dst_w, dst_h = self.rectified_board_size
        pad = 50.0
        dst = np.float32(
            [
                [pad, pad],  # A0 (Top-Left)
                [dst_w - pad, pad],  # A8 (Top-Right)
                [pad, dst_h - pad],  # J0 (Bottom-Left)
                [dst_w - pad, dst_h - pad],  # J8 (Bottom-Right)
            ]
        )

        matrix = cv2.getPerspectiveTransform(src, dst)
        warped_bgr = cv2.warpPerspective(frame_bgr, matrix, (dst_w, dst_h))
        return warped_bgr, matrix

    # -------------------------------------------------------------------------
    # 3. LAYOUT CLASSIFICATION (90 Squares)
    # -------------------------------------------------------------------------

    def recognize_layout(
        self, warped_bgr: np.ndarray
    ) -> Tuple[List[List[str]], List[List[str]], List[List[float]]]:
        """Phân loại quân cờ trên bàn cờ đã nắn phẳng.

        Args:
            warped_bgr: Ảnh bàn cờ (500, 450, 3) BGR

        Returns:
            board_project: 10x9 list chứa ký hiệu quân của project ('r_K', 'b_P', '.', 'x')
            board_short: 10x9 list chứa ký hiệu ngắn ('K', 'k', '.', 'x')
            confidences: 10x9 list chứa confidence tương ứng
        """
        h, w = warped_bgr.shape[:2]
        crop_w, crop_h = self.layout_crop_size

        # 1. Center crop
        cx, cy = w // 2, h // 2
        start_x = int(cx - crop_w // 2)
        start_y = int(cy - crop_h // 2)
        cropped = warped_bgr[start_y : start_y + crop_h, start_x : start_x + crop_w]

        # 2. Resize to (280, 315)
        resized = cv2.resize(cropped, self.layout_input_size)

        # 3. Normalization (BGR -> RGB)
        img_rgb = cv2.cvtColor(resized, cv2.COLOR_BGR2RGB)
        img_norm = (img_rgb - self.norm_mean) / self.norm_std
        inp = np.transpose(img_norm.astype(np.float32), (2, 0, 1))
        inp = np.expand_dims(inp, axis=0)

        # 4. Inference
        outputs = self.layout_session.run(None, {self.layout_input_name: inp})[0]
        # outputs shape: (1, 90, 16)
        preds_90 = outputs[0]

        label_indices = np.argmax(preds_90, axis=-1)
        confidences_flat = preds_90[np.arange(preds_90.shape[0]), label_indices]

        # 5. Map labels sang ký hiệu
        short_flat = [CLASS_TO_SHORT[CLASS_NAMES[idx]] for idx in label_indices]
        project_flat = [SHORT_TO_PROJECT.get(s, ".") for s in short_flat]

        # Reshape sang 10 hàng x 9 cột
        board_project = [project_flat[i * 9 : (i + 1) * 9] for i in range(10)]
        board_short = [short_flat[i * 9 : (i + 1) * 9] for i in range(10)]
        confidences = [confidences_flat[i * 9 : (i + 1) * 9].tolist() for i in range(10)]

        return board_project, board_short, confidences

    # -------------------------------------------------------------------------
    # 4. FULL PIPELINE & UTILITIES
    # -------------------------------------------------------------------------

    def check_recognition_quality(
        self, result: Dict, img_shape: Optional[Tuple[int, int]] = None
    ) -> RecognitionQuality:
        return check_recognition_quality(
            result,
            img_shape=img_shape,
            min_kpt_conf=self.min_kpt_conf,
            mean_kpt_conf=self.mean_kpt_conf,
            min_layout_conf=self.min_layout_conf,
            min_piece_conf=self.min_piece_conf,
        )

    def validate_recognition_result(
        self, result: Dict, img_shape: Optional[Tuple[int, int]] = None
    ) -> Tuple[bool, Optional[str]]:
        quality = self.check_recognition_quality(result, img_shape=img_shape)
        return quality.is_valid, quality.error

    def full_recognize(self, frame_bgr: np.ndarray) -> Dict:
        """Thực hiện toàn bộ quy trình:
        frame camera -> tìm 4 góc -> nắn bàn cờ -> nhận diện 90 ô cờ -> quality gate.

        Returns:
            Dict chứa:
                'success': bool
                'quality_ok': bool
                'keypoints': np.ndarray (4, 2)
                'keypoint_scores': np.ndarray (4,)
                'warped_image': np.ndarray (500, 450, 3)
                'board': List[List[str]] (10x9 project format: 'r_R', 'b_K', '.', ...)
                'board_short': List[List[str]] (10x9 short: 'R', 'k', '.', ...)
                'confidence': List[List[float]] (10x9 conf)
                'error': Optional[str]
        """
        try:
            h, w = frame_bgr.shape[:2]
            kpts, kpt_scores = self.detect_board_corners(frame_bgr)
            warped_bgr, _ = self.extract_rectified_board(frame_bgr, kpts)
            board_proj, board_short, confs = self.recognize_layout(warped_bgr)

            result = {
                "success": True,
                "quality_ok": True,
                "keypoints": kpts,
                "keypoint_scores": kpt_scores,
                "warped_image": warped_bgr,
                "board": board_proj,
                "board_short": board_short,
                "confidence": confs,
                "error": None,
            }

            quality = self.check_recognition_quality(result, img_shape=(h, w))
            if not quality.is_valid:
                result["success"] = False
                result["quality_ok"] = False
                result["error"] = f"Quality gate rejected: {quality.error}"
                print(f"[CChessRecognizer] ⚠️ {result['error']}")

            return result
        except Exception as e:
            return {
                "success": False,
                "quality_ok": False,
                "keypoints": None,
                "keypoint_scores": None,
                "warped_image": None,
                "board": [["." for _ in range(9)] for _ in range(10)],
                "board_short": [["." for _ in range(9)] for _ in range(10)],
                "confidence": [[0.0 for _ in range(9)] for _ in range(10)],
                "error": str(e),
            }

    def draw_visualization(
        self, frame_bgr: np.ndarray, result: Dict
    ) -> np.ndarray:
        """Vẽ kết quả nhận diện lên ảnh để hiển thị giám sát trực quan."""
        vis = frame_bgr.copy()
        if not result.get("success"):
            return vis

        kpts = result.get("keypoints")
        if kpts is not None:
            # Vẽ 4 góc bàn cờ và khung tứ giác
            pts = kpts.astype(int)
            for i, name in enumerate(BONE_NAMES):
                x, y = pts[i]
                cv2.circle(vis, (x, y), 6, (0, 0, 255), -1)
                cv2.putText(
                    vis, name, (x + 8, y - 8), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2
                )

            # Nối 4 cạnh bàn cờ: A0-A8, A8-J8, J8-J0, J0-A0
            links = [(0, 1), (1, 3), (3, 2), (2, 0)]
            for p1_idx, p2_idx in links:
                cv2.line(
                    vis,
                    (pts[p1_idx][0], pts[p1_idx][1]),
                    (pts[p2_idx][0], pts[p2_idx][1]),
                    (0, 255, 0),
                    2,
                )

        return vis

