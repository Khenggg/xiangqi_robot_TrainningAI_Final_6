"""Virtual playback presets; both use the complete existing physics executor."""
from dataclasses import dataclass
import math


@dataclass(frozen=True)
class SimulationPlaybackProfile:
    name: str
    speed_factor: float

    def to_dict(self):
        return dict(name=self.name, speed_factor=self.speed_factor,
                    physics="FULL", trajectory_samples="ALL", collision_checks="REQUIRED")


def resolve_simulation_playback(config):
    name = str(getattr(config, "SIMULATION_PROFILE", "detailed")).strip().lower()
    if name not in {"detailed", "fast"}:
        raise ValueError("SIMULATION_PROFILE must be detailed or fast")
    detailed = getattr(config, "SIMULATION_SPEED_FACTOR", 0.2)
    fast = getattr(config, "SIMULATION_FAST_SPEED_FACTOR", 1.0)
    for value in (detailed, fast):
        if isinstance(value, bool) or not math.isfinite(float(value)) or not .05 <= float(value) <= 1.0:
            raise ValueError("Simulation playback speeds must be within the viewer's 0.05–1.0 range")
    if float(fast) < float(detailed):
        raise ValueError("Fast simulation playback cannot be slower than detailed playback")
    return SimulationPlaybackProfile(name, float(fast if name == "fast" else detailed))
