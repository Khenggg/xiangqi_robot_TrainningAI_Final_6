"""
Robot backends package providing hardware abstraction for physical and virtual robots.
"""

from src.hardware.backends.base import RobotBackend, RobotStateSnapshot

__all__ = ["RobotBackend", "RobotStateSnapshot"]
