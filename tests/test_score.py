from __future__ import annotations

import copy

import pytest

from vehicletelemetry import pipeline
from vehicletelemetry.generate import GenParams, generate
from vehicletelemetry.score import match, score


def test_match_pairs_each_interval_once():
    assert match([(0, 1), (10, 11)], [(0.5, 0.6), (10, 12)]) == (2, 0, 0)
    assert match([(0, 1)], [(5, 6)]) == (0, 1, 1)
    assert match([(0, 1)], [(0, 1), (0.5, 0.7)]) == (
        1,
        1,
        0,
    )  # one found interval cannot answer two truths, nor the reverse
    assert match([(0, 1), (0.5, 0.7)], [(0, 1)]) == (1, 0, 1)
    assert match([(0, 1)], [(1.2, 2)]) == (0, 1, 1)
    assert match([(0, 1)], [(1.2, 2)], slack=0.5) == (1, 0, 0)
    assert match([], []) == (0, 0, 0)


def test_demo_is_found_accurately(demo):
    log, truth = demo
    s = score(pipeline.analyze(log), truth)
    t = s["trips"]
    assert t["matched"] == t["true"] == t["found"] and t["extra"] == 0
    assert abs(t["distance_total_error"]) < 0.01
    for r in t["per_trip"]:  # a trip is off by little more than the share of it that was a hole in the log
        assert abs(r["distance_error"]) < 0.005 + 3 * (1 - r["covered_share"]), r
    assert t["consumption_error_max"] < 0.05 and t["duration_error_max_s"] < 3
    for k, r in s["events"].items():
        # nothing is invented, and the only things missed are harsh ramps that fell inside a hole of the data
        assert r["fp"] == 0 and r["fn"] == r.get("missed_in_hole", 0), (k, r)
    assert sum(r["true"] for r in s["events"].values()) > 15


def test_missing_detections_lower_recall_and_false_ones_lower_precision(demo):
    log, truth = demo
    a = pipeline.analyze(log)
    cut = copy.deepcopy(a)
    cut["events"]["harsh_brake"] = cut["events"]["harsh_brake"][1:]
    cut["anomalies"]["spikes"] = cut["anomalies"]["spikes"][1:]
    extra = copy.deepcopy(a)
    extra["events"]["harsh_accel"].append(
        {"trip": 0, "t0": -50.0, "t1": -48.0, "start": "", "duration_s": 2.0, "peak_ms2": 3.0}
    )
    s = score(cut, truth)
    assert s["events"]["harsh_brake"]["fn"] == 1 and s["events"]["harsh_brake"]["recall"] < 1.0
    assert s["events"]["spike"]["fn"] == 1
    s = score(extra, truth)
    assert s["events"]["harsh_accel"]["fp"] == 1 and s["events"]["harsh_accel"]["precision"] < 1.0


def test_a_missing_trip_is_not_matched(demo):
    log, truth = demo
    a = pipeline.analyze(log)
    a["trips"] = a["trips"][1:]
    s = score(a, truth)["trips"]
    assert s["matched"] == s["true"] - 1


def test_scores_stay_high_across_seeds():
    for seed in (2, 3, 4):
        log, truth = generate(GenParams(days=5, seed=seed))
        s = score(pipeline.analyze(log), truth)
        assert s["trips"]["matched"] == s["trips"]["true"]
        for k, r in s["events"].items():
            assert (r["recall"] or 1) >= 0.85 and (r["precision"] or 1) >= 0.9, (seed, k, r)


def test_a_log_without_faults_has_no_false_alarms():
    log, truth = generate(GenParams(days=6, seed=7, anomaly_rate=0.0))
    s = score(pipeline.analyze(log), truth)
    assert all(r["fp"] == 0 for r in s["events"].values())
    a = pipeline.analyze(log)
    assert a["quality"]["spikes"] == 0 and a["events"]["overheat"] == [] and a["events"]["flatline"] == []
    assert s["trips"]["consumption_error_median"] == pytest.approx(0.0, abs=0.01)
