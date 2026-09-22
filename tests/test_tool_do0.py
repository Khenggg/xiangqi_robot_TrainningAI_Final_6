"""Deprecated one-output gripper diagnostic.

The direct-drive gripper now uses Tool DO1 for open and Tool DO0 for close.
This script intentionally performs no hardware I/O. Use
``test_tool_gripper_two_output.py`` for the guarded manual diagnostic.
"""


def main():
    print("Deprecated: no Tool DO command was sent.")
    print("Use test_tool_gripper_two_output.py for the two-output diagnostic.")


if __name__ == "__main__":
    main()
