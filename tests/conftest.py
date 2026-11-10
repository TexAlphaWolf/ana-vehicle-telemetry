from __future__ import annotations

import os
from datetime import datetime

import numpy as np
import pytest

from vehicletelemetry.generate import GenParams, Truth, generate
from vehicletelemetry.logio import Log, make_log

SEED = int(os.environ.get("VTEL_TEST_SEED", "1"))
DRAWS = int(os.environ.get("VTEL_TEST_DRAWS", "12"))

T0 = datetime(2027, 1, 4, 8, 0, 0)


def steady(speed_kmh: float, seconds: int = 120, **channels: float) -> Log:
    """A log at one sample per second with every channel constant, for hand-computed expectations."""
    t = np.arange(seconds + 1, dtype=float)
    cols = {"speed": np.full(t.size, speed_kmh)}
    for k, v in channels.items():
        cols[k] = np.full(t.size, v)
    return make_log(T0, t, **cols)


def custom(t: list[float], speed: list[float], **channels: list[float]) -> Log:
    return make_log(
        T0,
        np.asarray(t, float),
        speed=np.asarray(speed, float),
        **{k: np.asarray(v, float) for k, v in channels.items()},
    )


@pytest.fixture(scope="session")
def demo() -> tuple[Log, Truth]:
    return generate(GenParams(days=6, seed=SEED))
