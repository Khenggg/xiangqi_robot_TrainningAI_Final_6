"""Read-only explanations of board-verification failures; no acceptance authority."""
import numpy as np

from src.core.fen_utils import board_array_to_fen


REASONS = {
    "CALIBRATION_UNAVAILABLE": "Chưa có calibration camera hợp lệ",
    "CAMERA_UNAVAILABLE": "Camera hoặc bộ nhận diện chưa sẵn sàng",
    "NO_FRESH_OBSERVATION": "Camera chưa trả được ảnh mới kèm kết quả nhận diện",
    "FRAME_UNAVAILABLE": "Không lấy được ảnh camera",
    "INVALID_TIMESTAMP": "Thời gian của ảnh không hợp lệ",
    "FUTURE_FRAME": "Thời gian ảnh nằm trong tương lai",
    "STALE_FRAME": "Ảnh quá cũ để xác nhận bàn",
    "OUT_OF_ORDER_FRAME": "Ảnh đến sai thứ tự thời gian",
    "DUPLICATE_FRAME": "Ảnh/mã quan sát bị lặp; không được tính thành mẫu mới",
    "INVALID_OBSERVATION_ID": "Mã quan sát không hợp lệ",
    "RECOGNITION_FAILED": "Model không trả kết quả nhận diện thành công",
    "MALFORMED_BOARD": "Layout không đúng ma trận 10 hàng × 9 cột",
    "BOARD_SANITY_FAILED": "Bàn nhận diện không hợp lệ theo luật cơ bản",
    "QUALITY_REJECTED": "Kết quả nhận diện không đạt quality_ok",
    "CONFIDENCE_INVALID": "Dữ liệu confidence thiếu hoặc không hợp lệ",
    "LOW_PIECE_CONFIDENCE": "Confidence của quân cờ thấp hơn ngưỡng",
    "BOARD_MISMATCH": "Bàn không khớp FEN dự kiến",
    "LAYOUT_UNSTABLE": "Hai lần quét nhận được hai bàn khác nhau",
    "INSUFFICIENT_STABLE_SAMPLES": "Chưa đủ mẫu mới hợp lệ liên tiếp",
    "EXCEPTION": "Có lỗi trong quá trình lấy ảnh/xác thực bàn",
    "MATCH": "Mẫu nhận diện đạt điều kiện",
}


def piece_name(symbol):
    if symbol == ".":
        return "ô trống (.)"
    names = {"K": "Tướng", "A": "Sĩ", "E": "Tượng", "N": "Mã",
             "R": "Xe", "C": "Pháo", "P": "Tốt"}
    if isinstance(symbol, str) and len(symbol) == 3 and symbol[1] == "_":
        side = {"r": "Đỏ", "b": "Đen"}.get(symbol[0], symbol[0])
        return f"{names.get(symbol[2], symbol[2])} {side} ({symbol})"
    return str(symbol)


def board_position_fen(board):
    """Only the position field: a camera image cannot establish whose turn it is."""
    try:
        return board_array_to_fen(board).split()[0]
    except (TypeError, ValueError, IndexError, KeyError):
        return None


def confidence_details(board, confidence, minimum):
    details = {"confidence_threshold": minimum}
    if not np.isfinite(minimum) or minimum < 0:
        return dict(confidence_threshold=None, confidence_error=f"ngưỡng confidence không hợp lệ: {minimum!r}")
    try:
        values = np.asarray(confidence, dtype=float)
    except (TypeError, ValueError):
        return dict(details, confidence_error="confidence không phải ma trận số")
    if values.shape != (10, 9):
        return dict(details, confidence_error=f"shape={values.shape}, cần (10, 9)")
    if not np.isfinite(values).all():
        return dict(details, confidence_error="confidence chứa NaN/Infinity")
    if (values < 0).any() or (values > 1).any():
        return dict(details, confidence_error="confidence nằm ngoài [0, 1]")
    occupied = [(r, c) for r in range(10) for c in range(9) if board[r][c] not in (".", "x", "")]
    details["min_piece_confidence"] = min((float(values[r, c]) for r, c in occupied), default=None)
    details["low_confidence_cells"] = [
        dict(row=r, col=c, piece=board[r][c], confidence=float(values[r, c]))
        for r, c in occupied if values[r, c] < minimum]
    return details


def recognition_diagnostics(result, minimum, *, sane, sanity_error, quality,
                            exact=None, diff_cells=None):
    """Describe decisions already made by the verifier, without changing them."""
    result = result if isinstance(result, dict) else {}
    board = result.get("board")
    details = {"sanity_error": sanity_error, "recognition_error": result.get("error"),
               "cell_order": "row,col", "cell_index_base": 0}
    shape_ok = (isinstance(board, (list, tuple)) and len(board) == 10
                and all(isinstance(row, (list, tuple)) and len(row) == 9 for row in board))
    if shape_ok:
        details.update(confidence_details(board, result.get("confidence"), minimum))
        details["observed_red_count"] = sum(isinstance(p, str) and p.startswith("r_") for row in board for p in row)
        details["observed_black_count"] = sum(isinstance(p, str) and p.startswith("b_") for row in board for p in row)
        if sane:
            details["observed_board_fen"] = board_position_fen(board)
    if diff_cells is not None:
        details["board_diff_count"] = len(diff_cells)
        details["diff_cells"] = diff_cells
    if not result.get("success"):
        reason = "RECOGNITION_FAILED"
    elif not shape_ok:
        reason = "MALFORMED_BOARD"
    elif not sane:
        reason = "BOARD_SANITY_FAILED"
    elif not quality:
        reason = ("QUALITY_REJECTED" if "quality_ok" in result else
                  "CONFIDENCE_INVALID" if details.get("confidence_error") else
                  "LOW_PIECE_CONFIDENCE")
    elif exact is False:
        reason = "BOARD_MISMATCH"
    else:
        reason = "MATCH"
    return reason, details


def diagnostic_message(reason, details):
    message = f"FEN [{reason}]: {REASONS.get(reason, reason)}."
    if details.get("exception_type"):
        message += f" Loại lỗi: {details['exception_type']}."
    differences = details.get("diff_cells") or []
    if differences:
        message += f" {len(differences)} ô lệch; hàng/cột tính từ 0."
        for cell in differences[:20]:
            message += (f"\n  hàng={cell['row']}, cột={cell['col']}: "
                        f"dự kiến {piece_name(cell['expected'])}; nhận {piece_name(cell['observed'])}.")
        if len(differences) > 20:
            message += f"\n  Còn {len(differences) - 20} ô; xem toàn bộ data.diff_cells."
    for key in ("sanity_error", "recognition_error", "confidence_error", "error"):
        if details.get(key):
            message += f" {details[key]}."
    for cell in details.get("low_confidence_cells", [])[:20]:
        message += (f"\n  hàng={cell['row']}, cột={cell['col']}: {piece_name(cell['piece'])}, "
                    f"confidence={cell['confidence']:.3f} < {details['confidence_threshold']:.3f}.")
    if "frame_age_s" in details and details.get("max_frame_age_s") is not None:
        message += f" Tuổi ảnh={details['frame_age_s']:.3f}s, giới hạn={details['max_frame_age_s']:.3f}s."
    if "consecutive" in details:
        message += f" Mẫu liên tiếp={details['consecutive']}/{details['required']}."
    return message
