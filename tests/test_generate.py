from __future__ import annotations

import numpy as np
import pytest

from vehicletelemetry import generate as gen
from vehicletelemetry.generate import GenParams, Truth, generate


def test_same_seed_same_log():
    a, ta = generate(GenParams(days=3, seed=5))
    b, tb = generate(GenParams(days=3, seed=5))
    assert np.array_equal(a.t, b.t) and np.array_equal(a.speed, b.speed, equal_nan=True)
    assert ta.to_dict() == tb.to_dict()
    c, _ = generate(GenParams(days=3, seed=6))
    assert len(c) != len(a) or not np.array_equal(c.speed, a.speed, equal_nan=True)


def test_log_is_well_formed(demo):
    log, truth = demo
    assert (np.diff(log.t) > 0).all()
    assert log.t[0] == 0.0
    assert len(truth.trips) > 5
    assert set(truth.anomalies) == {"dropout", "spike", "out_of_range", "overheat", "flatline"}
    # no bookkeeping left in the truth
    for recs in truth.anomalies.values():
        for r in recs:
            assert "i" not in r and "j" not in r and "ch" not in r


def test_clean_log_has_no_faults():
    log, truth = generate(GenParams(days=4, seed=2, anomaly_rate=0.0))
    assert all(not v for v in truth.anomalies.values())
    for c in ("speed", "rpm", "throttle", "load", "coolant", "fuel"):
        assert np.isfinite(log.channel(c)).all()
    assert log.speed.max() < 250 and log.rpm.max() < 8000


def test_truth_trips_match_the_physics():
    """The distance of a trip is the integral of its speed: check a trip against the samples (clean log, no noise on the truth)."""
    log, truth = generate(GenParams(days=2, seed=3, anomaly_rate=0.0))
    for tt in truth.trips:
        m = (log.t >= tt["start_s"]) & (log.t <= tt["end_s"])
        km = np.trapezoid(log.speed[m] / 3.6, log.t[m]) / 1000.0
        assert km == pytest.approx(tt["distance_km"], rel=0.02)
        assert 3.0 < tt["l_per_100km"] < 12.0


def test_harsh_ramps_are_harsh_and_the_rest_are_not():
    log, truth = generate(GenParams(days=14, seed=1, anomaly_rate=0.0))
    acc = np.diff(log.speed / 3.6) / np.diff(log.t)
    for h in truth.harsh:
        assert h["ms2"] >= (3.0 if h["kind"] == "harsh_accel" else 3.8)
        assert h["t1"] - h["t0"] >= 3.0
    assert (acc < 2.5).sum() > 0.99 * acc.size  # nothing but the harsh ramps (and the interval around them) comes close


def test_gears_and_fuel_cut():
    v = np.array([0.0, 15.0, 30.0, 50.0, 120.0])
    rpm, _thr, _load, fuel = gen.physics(v, np.zeros(5))
    assert rpm[0] == gen.IDLE_RPM
    assert 1500 < rpm[1] < 2600 and 1500 < rpm[3] < 3000 and 2000 < rpm[4] < 3500
    assert (fuel >= gen.IDLE_LPH).all() and fuel[4] > fuel[3]
    _, _, _, cut = gen.physics(np.array([60.0]), np.array([-1.0]))
    assert cut[0] == gen.FUEL_CUT_LPH


def test_truth_round_trip_and_rejects_other_json():
    _, truth = generate(GenParams(days=2, seed=1))
    assert Truth.from_dict(truth.to_dict()).to_dict() == truth.to_dict()
    with pytest.raises(ValueError, match="not a truth"):
        Truth.from_dict({"kind": "report"})


def test_no_trips_is_an_error():
    with pytest.raises(ValueError, match="no trips"):
        generate(GenParams(days=0))
