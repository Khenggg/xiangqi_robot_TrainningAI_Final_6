"""
Robot backends package providing hardware abstraction for physical and virtual robots.
"""

from src.hardware.backends.base import RobotBackend, RobotStateSnapshot
from src.hardware.backends.physical_fr3 import PhysicalFR3Backend

try:
    from src.simulation.virtual_fr3_backend import VirtualFR3Backend
except ImportError:
    VirtualFR3Backend = None  # type: ignore

__all__ = ["RobotBackend", "RobotStateSnapshot", "PhysicalFR3Backend", "VirtualFR3Backend"]
