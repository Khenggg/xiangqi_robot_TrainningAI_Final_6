"""Read-only R1-R4 display mapping; never a calibration or motion provider.

Robot-base XY is in mm. The four corners retain their semantic row/col order,
including opposite winding from a nominal simulation board. Surface height is
independent of the taught approach Z and is explicitly unverified if unavailable.
"""
import math


class PhysicalBoardDisplay:
    def __init__(self, robot, config, preview_surface_z_m):
        corners = robot._validated_corners()
        self.points = {name: [float(v) for v in xyz]
                       for name, xyz in zip(("R1", "R2", "R3", "R4"), corners)}
        if len(self.points) != 4 or any(len(p) != 3 or not all(map(math.isfinite, p))
                                       for p in self.points.values()):
            raise ValueError("Display requires four finite robot-base corners")
        if robot.user_num != 0:
            raise ValueError("Physical display requires normalized robot-base/user 0 points")
        self.version = int(getattr(robot, "teaching_points_version", 1))
        measured_z = getattr(config, "BOARD_CALIBRATION_SURFACE_Z_MM", None)
        self.z_verified = measured_z is not None
        self.surface_z_m = float(measured_z) / 1000 if self.z_verified else float(preview_surface_z_m)
        if isinstance(measured_z, bool) or not math.isfinite(self.surface_z_m):
            raise ValueError("Display surface Z must be finite mm")
        self.profile_id = getattr(robot, "teaching_points_profile_id", None)

    def cell_robot(self, row, col, height_m=0):
        u, v = float(col)/8, float(row)/9
        a, b, c, d = (self.points[n] for n in ("R1", "R2", "R3", "R4"))
        xy = [(1-v)*((1-u)*a[i]+u*b[i])+v*((1-u)*d[i]+u*c[i]) for i in (0, 1)]
        return [xy[0]/1000, xy[1]/1000, self.surface_z_m+height_m]

    def packet(self):
        center = self.cell_robot(4.5, 4)
        return dict(type="board_placement", placement_source="R1_R4_PHYSICAL_DISPLAY",
                    calibration_space="TAUGHT_XY_DISPLAY_ONLY", motion_authority=False,
                    coordinate_frame="robot_base", position_unit="mm",
                    display_teaching_points_mm=self.points, surface_z_verified=self.z_verified,
                    board_surface_z_robot_m=self.surface_z_m, board_surface_z_m=self.surface_z_m,
                    board_center_world_m=[-center[1], center[2], -center[0]],
                    grid_origin_robot_m=self.cell_robot(0, 0),
                    placement_version=self.version, T_robot_from_board=None)

    def project_pieces(self, packet, cells, world, excluded=()):
        by_id = {piece_id: cell for cell, piece_id in cells.items()}
        for piece in packet.get("pieces", []):
            piece_id = piece["id"]
            if (piece_id not in by_id or piece_id in excluded
                    or piece.get("is_grasped") or piece.get("captured")):
                continue
            row, col = by_id[piece_id]
            pos = self.cell_robot(row, col, world.pieces[piece_id].height_m/2)
            view = [-pos[1], pos[2], -pos[0]]
            piece.update(pose_robot=pos, position_robot_base_m=pos,
                         pose_world=view, position_3d_world_m=view,
                         nearest_row=row, nearest_col=col, row_float=row, col_float=col,
                         status="RESTING", physical_state="RESTING")
        packet.update(payload_evidence="TAUGHT_XY_DISPLAY_ONLY", motion_authority=False,
                      surface_z_verified=self.z_verified)
