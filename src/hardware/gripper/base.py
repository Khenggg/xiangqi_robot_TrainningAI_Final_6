"""
Abstract Base Interface for Robot Gripper Drivers.
"""

from abc import ABC, abstractmethod


class GripperDriver(ABC):
    """Abstract protocol for robot end-effector gripping mechanisms."""

    @abstractmethod
    def open(self) -> bool:
        """Open / release gripper."""
        pass

    @abstractmethod
    def close(self) -> bool:
        """Close / grip gripper."""
        pass

    @abstractmethod
    def stop(self) -> bool:
        """Halt gripper motion and enter safe idle state."""
        pass

    @abstractmethod
    def is_closed(self) -> bool:
        """Return True if gripper is in gripped state."""
        pass
