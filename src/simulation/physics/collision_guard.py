"""
Authoritative FR3 Collision Guard for PyBullet Virtual Physical World.

Implements collision checking abstraction for:
- FR3 links <-> board
- FR3 links <-> pieces
- Gripper proxies <-> board
- Gripper proxies <-> pieces
- FR3 self-collision (filtering legitimate adjacent links)

Enforces mandatory invariants:
- No colliding pose may be committed.
- Trajectories are pre-validated across intermediate samples (anti-tunneling).
- Provides detailed CollisionResult evidence (colliding bodies, links, distances, failure reasons).
"""

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence, Set, Tuple
import numpy as np
import pybullet as p

from src.simulation.physics.state import PiecePhysicalState


@dataclass(frozen=True)
class CollisionResult:
    """Detailed evidence from collision checking."""
    safe: bool
    colliding_body: Optional[str] = None
    robot_link: Optional[int] = None
    obstacle: Optional[str] = None
    distance_m: Optional[float] = None
    penetration_m: Optional[float] = None
    sample_index: Optional[int] = None
    q_failed: Optional[List[float]] = None
    failure_reason: Optional[str] = None

    def __repr__(self) -> str:
        if self.safe:
            return "<CollisionResult: SAFE>"
        dist_str = f"{self.distance_m*1000:.2f}mm" if self.distance_m is not None else "N/A"
        return (
            f"<CollisionResult: COLLISION {self.colliding_body} (link {self.robot_link}) "
            f"<-> {self.obstacle}, dist={dist_str}: {self.failure_reason}>"
        )


class FR3CollisionGuard:
    """
    Authoritative collision validator querying PyBullet for robot, gripper, board, and piece interactions.
    """

    # Adjacent link pairs derived from URDF chain (-1 is base_link, 0..5 are joints/links)
    IGNORED_ADJACENT_PAIRS = frozenset({
        (-1, 0), (0, -1),
        (0, 1), (1, 0),
        (1, 2), (2, 1),
        (2, 3), (3, 2),
        (3, 4), (4, 3),
        (4, 5), (5, 4),
    })

    def __init__(
        self,
        world,  # VirtualPhysicalWorld
        safety_margin_m: float = 0.002,  # 2.0 mm default safety margin for links & obstacles
        gripper_board_margin_m: float = 0.0005,  # 0.5 mm clearance for gripper tips above board surface
        self_collision_margin_m: float = 0.0005,  # 0.5 mm clearance for non-adjacent robot links
    ):
        self.world = world
        self.safety_margin_m = float(safety_margin_m)
        self.gripper_board_margin_m = float(gripper_board_margin_m)
        self.self_collision_margin_m = float(self_collision_margin_m)

    def validate_configuration(
        self,
        joints_rad: Sequence[float],
        allowed_grasp_piece_id: Optional[str] = None,
        safety_margin_m: Optional[float] = None,
        gripper_board_margin_m: Optional[float] = None,
        self_collision_margin_m: Optional[float] = None,
        restore_state: bool = False,
    ) -> CollisionResult:
        physics_lock = getattr(self.world, "_physics_lock", None)
        if physics_lock is not None:
            with physics_lock:
                return self._validate_configuration_locked(
                    joints_rad=joints_rad,
                    allowed_grasp_piece_id=allowed_grasp_piece_id,
                    safety_margin_m=safety_margin_m,
                    gripper_board_margin_m=gripper_board_margin_m,
                    self_collision_margin_m=self_collision_margin_m,
                    restore_state=restore_state,
                )
        return self._validate_configuration_locked(
            joints_rad=joints_rad,
            allowed_grasp_piece_id=allowed_grasp_piece_id,
            safety_margin_m=safety_margin_m,
            gripper_board_margin_m=gripper_board_margin_m,
            self_collision_margin_m=self_collision_margin_m,
            restore_state=restore_state,
        )

    def _validate_configuration_locked(
        self,
        joints_rad: Sequence[float],
        allowed_grasp_piece_id: Optional[str] = None,
        safety_margin_m: Optional[float] = None,
        gripper_board_margin_m: Optional[float] = None,
        self_collision_margin_m: Optional[float] = None,
        restore_state: bool = False,
    ) -> CollisionResult:
        margin = safety_margin_m if safety_margin_m is not None else self.safety_margin_m
        gb_margin = gripper_board_margin_m if gripper_board_margin_m is not None else self.gripper_board_margin_m
        self_margin = self_collision_margin_m if self_collision_margin_m is not None else self.self_collision_margin_m
        client = self.world.client_id
        robot_id = self.world.robot_body_id
        board_id = self.world.board_body_id

        q_bullet_orig = None
        if restore_state:
            q_bullet_orig = [p.getJointState(robot_id, j, physicsClientId=client)[0] for j in range(6)]

        try:
            return self._validate_configuration_internal(
                joints_rad=joints_rad,
                allowed_grasp_piece_id=allowed_grasp_piece_id,
                margin=margin,
                gb_margin=gb_margin,
                self_margin=self_margin,
                client=client,
                robot_id=robot_id,
                board_id=board_id,
            )
        finally:
            if q_bullet_orig is not None:
                sync_fn = getattr(self.world, "sync_robot_collision_configuration", getattr(self.world, "sync_robot_configuration", None))
                if sync_fn:
                    sync_fn(q_bullet_orig)

    def _validate_configuration_internal(
        self,
        joints_rad: Sequence[float],
        allowed_grasp_piece_id: Optional[str],
        margin: float,
        gb_margin: float,
        self_margin: float,
        client: int,
        robot_id: int,
        board_id: int,
    ) -> CollisionResult:
        # 1. Side-effect-free sync of PyBullet robot and gripper proxies to candidate q
        sync_fn = getattr(self.world, "sync_robot_collision_configuration", getattr(self.world, "sync_robot_configuration", None))
        if sync_fn:
            sync_fn(joints_rad)
        p.performCollisionDetection(physicsClientId=client)

        # 2. Check FR3 links <-> board
        pts = p.getClosestPoints(robot_id, board_id, distance=margin, physicsClientId=client)
        for pt in pts:
            dist = float(pt[8])
            if dist < margin:
                link = int(pt[3])
                penetration = max(0.0, -dist)
                return CollisionResult(
                    safe=False,
                    colliding_body="robot",
                    robot_link=link,
                    obstacle="board",
                    distance_m=dist,
                    penetration_m=penetration,
                    q_failed=[round(float(q), 4) for q in joints_rad],
                    failure_reason=(
                        f"Robot link {link} colliding with board (distance {dist*1000:.2f}mm < margin {margin*1000:.2f}mm)"
                    ),
                )

        # 3. Check Gripper proxies <-> board
        # Gripper fingertips intentionally hover close to board (e.g. 1.0mm-1.5mm) during grasp.
        # Enforces gb_margin to guarantee positive clearance without board penetration.
        for proxy_id in self.world.gripper.proxy_body_ids:
            pts = p.getClosestPoints(proxy_id, board_id, distance=gb_margin, physicsClientId=client)
            for pt in pts:
                dist = float(pt[8])
                if dist < gb_margin:
                    penetration = max(0.0, -dist)
                    return CollisionResult(
                        safe=False,
                        colliding_body="gripper",
                        robot_link=5,
                        obstacle="board",
                        distance_m=dist,
                        penetration_m=penetration,
                        q_failed=[round(float(q), 4) for q in joints_rad],
                        failure_reason=(
                            f"Gripper proxy colliding with board (distance {dist*1000:.2f}mm < margin {gb_margin*1000:.2f}mm)"
                        ),
                    )

        # 4. Check FR3 links <-> pieces
        for pid, piece in self.world.pieces.items():
            if piece.physical_state == PiecePhysicalState.OUT_OF_BOUNDS:
                continue
            # Non-gripper robot links may NEVER collide with any piece (even target piece)
            pts = p.getClosestPoints(robot_id, piece.body_id, distance=margin, physicsClientId=client)
            for pt in pts:
                dist = float(pt[8])
                if dist < margin:
                    link = int(pt[3])
                    return CollisionResult(
                        safe=False,
                        colliding_body="robot",
                        robot_link=link,
                        obstacle=f"piece:{pid}",
                        distance_m=dist,
                        penetration_m=max(0.0, -dist),
                        q_failed=[round(float(q), 4) for q in joints_rad],
                        failure_reason=f"Robot link {link} colliding with piece {pid} (dist={dist*1000:.2f}mm)",
                    )

        # 5. Check Gripper proxies <-> pieces
        attached_p = self.world.get_attached_piece()
        attached_id = attached_p.piece_id if attached_p is not None else None
        for pid, piece in self.world.pieces.items():
            if piece.physical_state == PiecePhysicalState.OUT_OF_BOUNDS:
                continue
            is_target_piece = (pid == allowed_grasp_piece_id) or (pid == attached_id) or (piece.attached_to_gripper)
            if is_target_piece:
                # Allowed grasp piece: finger jaws may contact piece. Palm must not penetrate.
                if self.world.gripper.palm_body_id >= 0:
                    pts = p.getClosestPoints(
                        self.world.gripper.palm_body_id,
                        piece.body_id,
                        distance=0.0,
                        physicsClientId=client,
                    )
                    if pts and pts[0][8] < -1e-4:
                        dist = float(pts[0][8])
                        return CollisionResult(
                            safe=False,
                            colliding_body="gripper_palm",
                            robot_link=5,
                            obstacle=f"piece:{pid}",
                            distance_m=dist,
                            penetration_m=-dist,
                            q_failed=[round(float(q), 4) for q in joints_rad],
                            failure_reason=(
                                f"Gripper palm penetrating target piece {pid} (penetration={-dist*1000:.2f}mm)"
                            ),
                        )
            else:
                for proxy_id in self.world.gripper.proxy_body_ids:
                    pts = p.getClosestPoints(proxy_id, piece.body_id, distance=margin, physicsClientId=client)
                    for pt in pts:
                        dist = float(pt[8])
                        if dist < margin:
                            return CollisionResult(
                                safe=False,
                                colliding_body="gripper",
                                robot_link=5,
                                obstacle=f"piece:{pid}",
                                distance_m=dist,
                                penetration_m=max(0.0, -dist),
                                q_failed=[round(float(q), 4) for q in joints_rad],
                                failure_reason=(
                                    f"Gripper colliding with obstacle piece {pid} "
                                    f"(dist={dist*1000:.2f}mm < margin {margin*1000:.2f}mm)"
                                ),
                            )

        # 6. Check FR3 self-collision (excluding adjacent pairs)
        pts = p.getClosestPoints(robot_id, robot_id, distance=self_margin, physicsClientId=client)
        for pt in pts:
            linkA, linkB = int(pt[3]), int(pt[4])
            if linkA == linkB or (linkA, linkB) in self.IGNORED_ADJACENT_PAIRS:
                continue
            dist = float(pt[8])
            if dist < self_margin:
                return CollisionResult(
                    safe=False,
                    colliding_body="robot",
                    robot_link=linkA,
                    obstacle=f"self_link_{linkB}",
                    distance_m=dist,
                    penetration_m=max(0.0, -dist),
                    q_failed=[round(float(q), 4) for q in joints_rad],
                    failure_reason=(
                        f"Robot self-collision between link {linkA} and link {linkB} "
                        f"(dist={dist*1000:.2f}mm < margin {self_margin*1000:.2f}mm)"
                    ),
                )

        return CollisionResult(safe=True)

    def validate_trajectory(
        self,
        q_samples: Sequence[Sequence[float]],
        allowed_grasp_piece_id: Optional[str] = None,
        safety_margin_m: Optional[float] = None,
        max_subdivision_step_rad: float = 0.0174533,  # 1.0 degree max joint delta
        self_collision_margin_m: Optional[float] = None,
        restore_state: bool = False,
    ) -> CollisionResult:
        """
        Validate an entire trajectory sample-by-sample with defensive intermediate
        subdivision between consecutive waypoints to strictly eliminate collision tunneling.
        """
        if not q_samples:
            return CollisionResult(safe=True)

        physics_lock = getattr(self.world, "_physics_lock", None)
        if physics_lock is not None:
            with physics_lock:
                return self._validate_trajectory_locked(
                    q_samples=q_samples,
                    allowed_grasp_piece_id=allowed_grasp_piece_id,
                    safety_margin_m=safety_margin_m,
                    max_subdivision_step_rad=max_subdivision_step_rad,
                    self_collision_margin_m=self_collision_margin_m,
                    restore_state=restore_state,
                )
        return self._validate_trajectory_locked(
            q_samples=q_samples,
            allowed_grasp_piece_id=allowed_grasp_piece_id,
            safety_margin_m=safety_margin_m,
            max_subdivision_step_rad=max_subdivision_step_rad,
            self_collision_margin_m=self_collision_margin_m,
            restore_state=restore_state,
        )

    def _validate_trajectory_locked(
        self,
        q_samples: Sequence[Sequence[float]],
        allowed_grasp_piece_id: Optional[str] = None,
        safety_margin_m: Optional[float] = None,
        max_subdivision_step_rad: float = 0.0174533,
        self_collision_margin_m: Optional[float] = None,
        restore_state: bool = False,
    ) -> CollisionResult:
        q_bullet_orig = None
        if restore_state:
            q_bullet_orig = [p.getJointState(self.world.robot_body_id, j, physicsClientId=self.world.client_id)[0] for j in range(6)]

        try:
            return self._validate_trajectory_internal(
                q_samples=q_samples,
                allowed_grasp_piece_id=allowed_grasp_piece_id,
                safety_margin_m=safety_margin_m,
                max_subdivision_step_rad=max_subdivision_step_rad,
                self_collision_margin_m=self_collision_margin_m,
            )
        finally:
            if q_bullet_orig is not None:
                sync_fn = getattr(self.world, "sync_robot_collision_configuration", getattr(self.world, "sync_robot_configuration", None))
                if sync_fn:
                    sync_fn(q_bullet_orig)

    def _validate_trajectory_internal(
        self,
        q_samples: Sequence[Sequence[float]],
        allowed_grasp_piece_id: Optional[str],
        safety_margin_m: Optional[float],
        max_subdivision_step_rad: float,
        self_collision_margin_m: Optional[float],
    ) -> CollisionResult:

        prev_q: Optional[np.ndarray] = None
        global_step_idx = 0

        for idx, q_step in enumerate(q_samples):
            curr_q = np.array(q_step, dtype=float)

            # Defensive subdivision: if consecutive waypoints exceed max_subdivision_step_rad,
            # interpolate and check all intermediate configurations.
            if prev_q is not None:
                max_diff = float(np.max(np.abs(curr_q - prev_q)))
                if max_diff > max_subdivision_step_rad:
                    n_sub = int(np.ceil(max_diff / max_subdivision_step_rad))
                    for k in range(1, n_sub):
                        alpha = float(k) / float(n_sub)
                        q_interp = prev_q + alpha * (curr_q - prev_q)
                        res = self.validate_configuration(
                            q_interp,
                            allowed_grasp_piece_id=allowed_grasp_piece_id,
                            safety_margin_m=safety_margin_m,
                            self_collision_margin_m=self_collision_margin_m,
                        )
                        if not res.safe:
                            return CollisionResult(
                                safe=False,
                                colliding_body=res.colliding_body,
                                robot_link=res.robot_link,
                                obstacle=res.obstacle,
                                distance_m=res.distance_m,
                                penetration_m=res.penetration_m,
                                sample_index=global_step_idx,
                                q_failed=res.q_failed,
                                failure_reason=(
                                    f"Intermediate trajectory segment {idx-1}->{idx} (substep {k}/{n_sub}) "
                                    f"failed collision check: {res.failure_reason}"
                                ),
                            )
                        global_step_idx += 1

            # Validate the waypoint itself
            res = self.validate_configuration(
                curr_q,
                allowed_grasp_piece_id=allowed_grasp_piece_id,
                safety_margin_m=safety_margin_m,
                self_collision_margin_m=self_collision_margin_m,
            )
            if not res.safe:
                return CollisionResult(
                    safe=False,
                    colliding_body=res.colliding_body,
                    robot_link=res.robot_link,
                    obstacle=res.obstacle,
                    distance_m=res.distance_m,
                    penetration_m=res.penetration_m,
                    sample_index=global_step_idx,
                    q_failed=res.q_failed,
                    failure_reason=f"Waypoint {idx}/{len(q_samples)} failed collision check: {res.failure_reason}",
                )
            global_step_idx += 1
            prev_q = curr_q

        return CollisionResult(safe=True)
