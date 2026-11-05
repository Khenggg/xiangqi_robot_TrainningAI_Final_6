"""Map physical gripper actions to viewer payload-animation intent.

The physical arm reports the command it executed, not whether it actually
holds a piece.  The twin therefore uses the command intent only to animate a
believed payload; a safe-gap close must never attach or release one.
"""

import config

IDLE = "idle"
ATTACH = "attach"
RELEASE = "release"


def gripper_intent(action, closed):
    """Return ``attach``/``release``/``idle`` for one gripper command.

    ``action`` is the hardware action string.  Legacy two-argument listeners
    pass ``None`` and keep the old boolean meaning.
    """
    if action == config.GRIPPER_ACTION_CLOSE_TO_SAFE_GAP:
        return IDLE
    if action == config.GRIPPER_ACTION_CLOSE:
        return ATTACH
    if action in (config.GRIPPER_ACTION_OPEN_MAX, config.GRIPPER_ACTION_RELEASE):
        return RELEASE
    return ATTACH if closed else RELEASE
