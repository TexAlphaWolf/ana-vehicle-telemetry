"""Thresholds of the analysis, in one validated place."""

from __future__ import annotations

from dataclasses import asdict, dataclass, fields
from typing import Any


class ParamError(ValueError):
    """A parameter is out of range or not a number."""


CHANNELS = ("speed", "rpm", "throttle", "load", "coolant", "fuel")

#: plausible physical range of every channel, in the units of the log file; a sample outside it is a sensor fault
RANGES: dict[str, tuple[float, float]] = {
    "speed": (0.0, 250.0),  # km/h
    "rpm": (0.0, 8000.0),
    "throttle": (0.0, 100.0),  # %
    "load": (0.0, 100.0),  # %
    "coolant": (-30.0, 150.0),  # degrees C
    "fuel": (0.0, 100.0),  # L/h
}


@dataclass(frozen=True)
class Params:
    gap_s: float = 30.0  # a longer time between two samples means the logger was off: no data in between
    max_fill_s: float = 10.0  # missing samples are interpolated when the hole is at most this long
    stop_kmh: float = 2.0  # below this speed the vehicle is stopped
    park_s: float = 600.0  # a stop this long is parking: the trip ended
    bridge_s: float = 60.0  # a hole of unknown speed this short, between two stops, does not interrupt the stop
    min_trip_m: float = 200.0  # shorter trips are dropped (engine started and stopped again)
    accel_ms2: float = 2.5  # harsh acceleration threshold
    brake_ms2: float = 3.0  # harsh braking threshold (deceleration, positive number)
    min_event_s: float = 1.5  # a harsh event lasts at least this long
    phys_ms2: float = 12.0  # no road car accelerates harder than this: a sample that jumps up and back is a spike
    rpm_high: float = 4000.0
    coolant_max_c: float = 110.0
    overheat_s: float = 20.0
    flat_s: float = 30.0  # a channel that does not move for this long is stuck
    afr: float = 14.7  # air-fuel ratio, to turn a mass air flow column into fuel (petrol)
    density_g_l: float = 745.0

    def __post_init__(self) -> None:
        for f in fields(self):
            v = getattr(self, f.name)
            if isinstance(v, bool) or not isinstance(v, int | float) or v != v or v in (float("inf"), float("-inf")):
                raise ParamError(f"{f.name} must be a finite number, got {v!r}")
            if v <= 0:
                raise ParamError(f"{f.name} must be positive, got {v!r}")
        if self.max_fill_s > self.gap_s:
            raise ParamError(f"max_fill_s ({self.max_fill_s:g}) cannot be longer than gap_s ({self.gap_s:g})")

    def as_dict(self) -> dict[str, float]:
        return {k: float(v) for k, v in asdict(self).items()}

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Params:
        known = {f.name for f in fields(cls)}
        extra = set(d) - known
        if extra:
            raise ParamError(f"unknown parameter(s): {', '.join(sorted(extra))}")
        return cls(**d)
