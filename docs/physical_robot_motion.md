# Physical FR5 motion model

## What determines a real robot pose

Each commanded FR5 Cartesian pose has six values:

```text
[X_mm, Y_mm, Z_mm, Rx_deg, Ry_deg, Rz_deg]
```

The application deliberately keeps two calibration concerns separate:

1. **Board position (X/Y):** `R1` to `R4` are the four physical board-corner
   teaching points. `board_to_pose_bilinear()` converts a logical grid coordinate
   (including Visual Pick's float coordinate) into a physical X/Y position.
2. **Tool direction (Rx/Ry/Rz):** `PICK_TOOL_ROTATION` and
   `PLACE_TOOL_ROTATION` are the maintained motion profile. They tell the robot
   which wrist pose makes the gripper face the piece correctly.

The camera never controls tool rotation or TCP. It can only make the final pick
XY more precise, and only within the configured 0.25-cell safety limit.

## Motion sequence

For a visual pick target, the robot runs:

```text
HOMECHESS -> [camera snapshot before entering board]
          -> XY actual at SAFE_Z, PICK_TOOL_ROTATION
          -> same XY at PICK_Z
          -> close gripper
          -> same XY at SAFE_Z
          -> destination-cell XY at SAFE_Z, PLACE_TOOL_ROTATION
          -> destination-cell XY at PLACE_Z
          -> open gripper -> SAFE_Z -> HOMECHESS
```

For a capture, the target at `dst` is picked first with the same sequence, then
placed in `R_Trash`, before the moving piece at `src` is picked.

## Teaching and changing gripper rotation

Do **not** guess a wrist angle. With the board clear and the robot in low-speed
manual teaching mode:

1. Move the tool to an empty board position at `SAFE_Z`.
2. Rotate the wrist/tool until the gripper jaws are in the desired physical
   direction and the tool points safely down.
3. Record the displayed `Rx`, `Ry`, and `Rz` from the FR5 controller.
4. Set those three values in `config.py` as `PICK_TOOL_ROTATION`. Normally copy
   the same values to `PLACE_TOOL_ROTATION`.
5. Restart the application so the profile is read again.

`ROTATION` remains the compatibility fallback for HOME/IDLE/trash poses and for
older calls that do not request a motion profile. The code does not modify the
controller's TCP/tool frame, `tool_num`, `user_num`, or the teaching points.

## Maintenance checklist

- If all pieces are offset by the same amount, adjust `OFFSET_X` / `OFFSET_Y`.
- If offset grows toward a board edge, reteach R1-R4 or recalibrate the camera;
  do not widen the Visual Pick maximum offset.
- If the gripper jaw direction is wrong while XY is correct, update only the
  pick/place rotation profile after manual teaching.
- Keep `SAFE_Z`, `PICK_Z`, and `PLACE_Z` conservative. Validate a new profile
  with `DRY_RUN=True` first, then a no-piece, low-speed physical approach.
