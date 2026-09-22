"""
Robot backends package providing hardware abstraction for physical and virtual robots.
"""

from src.hardware.backends.base import RobotBackend, RobotStateSnapshot
from src.hardware.backends.physical_fr3 import PhysicalFR3Backend

__all__ = ["RobotBackend", "RobotStateSnapshot", "PhysicalFR3Backend"]
