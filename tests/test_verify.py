from __future__ import annotations

import math

import numpy as np

from tests.conftest import DRAWS, SEED
from vehicletelemetry import pipeline, verify
from vehicletelemetry.verify import compare


def test_the_two_implementations_agree_on_random_logs():
    checks = verify.verify(DRAWS, SEED)
    assert len(checks) == DRAWS + 1
    assert all(c.ok for c in checks), [c for c in checks if not c.ok]
    assert sum(c.numbers for c in checks) > 1000
    assert max(c.max_rel_error for c in checks) < verify.RTOL


def test_random_cases_exercise_the_hard_paths():
    """Over the random cases, trips are cut by parking and by gaps, events are found, holes are filled and left."""
    rng = np.random.default_rng(SEED)
    seen = {
        "trips": 0,
        "events": 0,
        "filled": 0,
        "left": 0,
        "spikes": 0,
        "oor": 0,
        "sessions": 0,
        "flat": 0,
        "dropped": 0,
    }
    for _ in range(max(DRAWS, 12)):
        from vehicletelemetry.generate import GenParams, generate

        base, _t = generate(GenParams(days=1, seed=int(rng.integers(0, 10**6))))
        log, p = verify.hostile(base, rng), verify.random_params(rng)
        a = pipeline.analyze(log, p)
        seen["trips"] += a["totals"]["trips"]
        seen["events"] += a["totals"]["harsh_accel"] + a["totals"]["harsh_brake"]
        seen["filled"] += sum(a["quality"]["filled"].values())
        seen["left"] += sum(a["quality"]["missing_after"].values())
        seen["spikes"] += a["quality"]["spikes"]
        seen["oor"] += sum(a["quality"]["out_of_range"].values())
        seen["sessions"] += a["quality"]["sessions"] - 1
        seen["flat"] += a["totals"]["flatline_events"]
        seen["dropped"] += a["quality"]["short_trips_dropped"]
    assert all(v > 0 for v in seen.values()), seen


def test_a_difference_is_reported(monkeypatch):
    real = pipeline.analyze

    def broken(log, p=None):
        out = real(log, p)
        out["totals"]["distance_km"] *= 1.001
        return out

    monkeypatch.setattr(verify.pipeline, "analyze", broken)
    checks = verify.verify(2, 1)
    assert not any(c.ok for c in checks)
    assert "distance_km" in checks[0].detail


def test_compare():
    assert compare({"a": [1.0, 2]}, {"a": [1.0 + 1e-12, 2]})[2] is None
    n, worst, bad = compare({"a": 1.0}, {"a": 1.001})
    assert n == 1 and worst > 5e-4 and bad == "/a: 1.0 against 1.001"
    assert compare({"a": 1}, {"b": 1})[2].startswith(": keys differ")
    assert "2 items against 3" in compare([1, 2], [1, 2, 3])[2]
    assert compare(math.nan, math.nan)[2] is None
    assert compare(None, 1.0)[2] is not None
    assert compare("x", "y")[2] == ": 'x' against 'y'"
    assert compare(1, 1.0)[2] is not None  # an int is not a float: the shapes must match too
