"""Hand-computed cases. Each one is also run through the literal implementation, which must give the same answer."""

from __future__ import annotations

import math

import numpy as np
import pytest

from tests.conftest import custom, steady
from vehicletelemetry import pipeline, reference
from vehicletelemetry.params import Params
from vehicletelemetry.verify import compare


def both(log, **params):
    p = Params(**params)
    a, b = pipeline.analyze(log, p), reference.analyze(log, p)
    n, _, bad = compare(a, b)
    assert bad is None and n > 0, bad
    return a


def test_steady_drive_by_hand():
    a = both(steady(36.0, 120, fuel=5.0))
    (t,) = a["trips"]
    assert t["distance_km"] == pytest.approx(1.2)
    assert t["duration_s"] == 120 and t["valid_s"] == 120 and t["covered_share"] == 1.0
    assert t["avg_speed_kmh"] == pytest.approx(36.0)
    assert t["max_speed_kmh"] == pytest.approx(36.0)
    assert t["fuel_l"] == pytest.approx(5.0 * 120 / 3600)
    assert t["l_per_100km"] == pytest.approx(5.0 * 120 / 3600 / 1.2 * 100)
    assert t["idle_s"] == 0 and t["moving_s"] == 120
    assert a["totals"]["trips"] == 1 and a["totals"]["harsh_accel"] == 0
    assert a["quality"]["sessions"] == 1


def test_no_fuel_channel_means_no_consumption():
    a = both(steady(36.0))
    t = a["trips"][0]
    assert t["fuel_l"] is None and t["l_per_100km"] is None and t["fuel_share"] is None
    assert a["totals"]["fuel_l"] is None and a["totals"]["l_per_100km"] is None
    assert not a["log"]["channels"]["fuel"]


def test_parking_ends_a_trip_and_starts_the_next():
    speed = [0.0] * 701 + [36.0] * 100
    a = both(custom(list(range(801)), speed))
    (t,) = a["trips"]
    assert t["start_s"] == 700 and t["end_s"] == 800
    assert t["distance_km"] == pytest.approx((5 + 99 * 10) / 1000)  # the first interval goes from 0 to 10 m/s: 5 m


def test_a_shorter_stop_stays_inside_the_trip():
    speed = [36.0] * 60 + [0.0] * 120 + [36.0] * 60
    a = both(custom(list(range(240)), speed))
    (t,) = a["trips"]
    assert t["idle_s"] == pytest.approx(119)  # 120 samples at 0 km/h: 119 stopped intervals
    assert t["idle_share"] == pytest.approx(119 / 239)


def test_logger_off_splits_trips_and_counts_sessions():
    t = list(range(101)) + [1100 + i for i in range(101)]
    a = both(custom(t, [36.0] * 202))
    assert len(a["trips"]) == 2 and a["quality"]["sessions"] == 2
    assert a["quality"]["longest_gap_s"] == 1000
    assert all(x["distance_km"] == pytest.approx(1.0) for x in a["trips"])


def test_very_short_trips_are_dropped_and_counted():
    a = both(steady(36.0, 15))  # 150 m
    assert a["trips"] == [] and a["quality"]["short_trips_dropped"] == 1
    assert (
        a["totals"]["trips"] == 0 and a["totals"]["harsh_accel_per_100km"] is None and a["totals"]["idle_share"] is None
    )


def test_harsh_acceleration_and_braking():
    v = [3.0 * i for i in range(6)] + [15.0] * 60 + [15.0 - 3.5 * i for i in range(1, 5)] + [1.0] * 10
    a = both(custom(list(range(len(v))), [x * 3.6 for x in v]))
    (acc,), (brk,) = a["events"]["harsh_accel"], a["events"]["harsh_brake"]
    assert acc["duration_s"] == 5 and acc["peak_ms2"] == pytest.approx(3.0) and acc["trip"] == 0
    assert brk["duration_s"] == 4 and brk["peak_ms2"] == pytest.approx(3.5)
    assert a["trips"][0]["harsh_accel"] == 1 and a["trips"][0]["harsh_brake"] == 1
    assert a["totals"]["harsh_accel_per_100km"] == pytest.approx(100 / a["totals"]["distance_km"])


def test_thresholds_are_inclusive_and_a_short_burst_is_not_an_event():
    v = [0.0, 2.5, 5.0, 7.5] + [7.5] * 200  # exactly 2.5 m/s2 for 3 s
    a = both(custom(list(range(len(v))), [x * 3.6 for x in v]))
    assert len(a["events"]["harsh_accel"]) == 1
    a = both(custom(list(range(len(v))), [x * 3.6 for x in v]), accel_ms2=2.6)
    assert a["events"]["harsh_accel"] == []
    v = [0.0, 3.0] + [3.0] * 200 + [12.0] * 100  # one second only, shorter than min_event_s
    a = both(custom(list(range(len(v))), [x * 3.6 for x in v]))
    assert a["events"]["harsh_accel"] == []
    a = both(custom(list(range(len(v))), [x * 3.6 for x in v]), min_event_s=1.0)
    assert len(a["events"]["harsh_accel"]) == 2


def test_a_spike_is_removed_and_does_not_count_as_driving():
    s = [36.0] * 121
    s[50] = 126.0
    a = both(custom(list(range(121)), s))
    assert a["quality"]["spikes"] == 1 and a["anomalies"]["spikes"] == [50.0]
    assert a["trips"][0]["distance_km"] == pytest.approx(1.2)
    assert a["events"]["harsh_accel"] == [] and a["events"]["harsh_brake"] == []
    assert a["trips"][0]["max_speed_kmh"] == pytest.approx(36.0)


def test_out_of_range_values_become_holes_and_are_filled():
    s = [36.0] * 121
    s[40] = 255.0
    a = both(custom(list(range(121)), s, rpm=[2000.0] * 120 + [-5.0]))
    assert a["quality"]["out_of_range"]["speed"] == 1 and a["quality"]["out_of_range"]["rpm"] == 1
    assert a["quality"]["filled"]["speed"] == 1
    assert a["anomalies"]["out_of_range"][0] == {"channel": "speed", "t": 40.0, "value": 255.0}
    assert a["trips"][0]["distance_km"] == pytest.approx(1.2)


def test_short_hole_is_interpolated_long_hole_is_not():
    s = [36.0] * 121
    for i in range(50, 55):  # 5 samples: 6 s between the good ones
        s[i] = math.nan
    a = both(custom(list(range(121)), s))
    assert a["trips"][0]["distance_km"] == pytest.approx(1.2) and a["quality"]["filled"]["speed"] == 5
    assert a["anomalies"]["dropouts"] == [{"t0": 50.0, "t1": 54.0, "samples": 5, "filled": True}]
    s = [36.0] * 121
    for i in range(50, 70):  # 20 samples: 21 s
        s[i] = math.nan
    a = both(custom(list(range(121)), s))
    t = a["trips"][0]
    assert t["distance_km"] == pytest.approx(0.99) and t["covered_share"] == pytest.approx(99 / 120)
    assert a["anomalies"]["dropouts"][0]["filled"] is False and a["quality"]["missing_after"]["speed"] == 20


def test_interpolation_is_linear_in_time():
    s = [0.0, 36.0, math.nan, math.nan, 72.0, 72.0] + [72.0] * 100
    t = [0, 1, 2, 4, 5, 6, *range(7, 107)]
    a = both(custom(t, s), min_trip_m=1.0)
    # the speed at t=2 and t=4 is on the line between 36 km/h at t=1 and 72 km/h at t=5
    assert a["quality"]["filled"]["speed"] == 2
    # 0 -> 10 m/s: 5 m; 10 -> 12.5: 11.25 m; 12.5 -> 17.5 over 2 s: 30 m; 17.5 -> 20: 18.75 m; then 101 intervals at 20 m/s
    assert a["trips"][0]["distance_km"] == pytest.approx((5 + 11.25 + 30 + 18.75 + 101 * 20) / 1000)


def test_a_hole_inside_a_long_stop_does_not_split_it():
    speed = [36.0] * 101 + [0.0] * 400 + [math.nan] * 30 + [0.0] * 400 + [36.0] * 101
    t = list(range(len(speed)))
    assert len(both(custom(t, speed))["trips"]) == 2  # parked once: two trips, one before and one after
    assert (
        len(both(custom(t, speed), bridge_s=10)["trips"]) == 1
    )  # two stops of 400 s each, nothing long enough to park


def test_overheating_and_stuck_sensors():
    n = 200
    temp = [90.0] * 60 + [112.0] * 40 + [90.0] * 100
    rpm = [2000.0 + (i % 7) for i in range(n)]
    for i in range(80, 130):
        rpm[i] = 2500.0
    a = both(custom(list(range(n)), [36.0] * n, coolant=temp, rpm=rpm, load=[40.0 + (i % 3) for i in range(n)]))
    (hot,) = a["events"]["overheat"]
    assert hot["t0"] == 60 and hot["duration_s"] == 39 and hot["peak_c"] == 112.0
    (flat,) = a["events"]["flatline"]
    assert flat["channel"] == "rpm" and flat["value"] == 2500.0 and flat["duration_s"] == 49
    assert a["totals"]["overheat_events"] == 1 and a["totals"]["flatline_events"] == 1
    a = both(custom(list(range(n)), [36.0] * n, coolant=[105.0] * n))
    assert a["events"]["overheat"] == []


def test_high_rpm_and_max_coolant_are_per_trip():
    n = 120
    a = both(
        custom(list(range(n)), [36.0] * n, rpm=[4500.0] * 30 + [2000.0] * 90, coolant=[80.0 + i / 10 for i in range(n)])
    )
    t = a["trips"][0]
    assert t["high_rpm_s"] == 29 and t["max_coolant_c"] == pytest.approx(91.9)


def test_irregular_sampling_integrates_over_the_real_time():
    t = [0, 0.5, 2.0, 2.2, 10.0, 60.0 - 40, 25, 30.5] + [30.5 + k for k in range(1, 40)]
    t = sorted(set(t))
    a = both(custom(t, [36.0] * len(t)))
    assert a["trips"][0]["distance_km"] == pytest.approx((t[-1] - t[0]) * 10 / 1000)
    assert a["log"]["median_dt_s"] == pytest.approx(float(np.median(np.diff(t))))


def test_minimal_logs_do_not_crash():
    a = both(custom([0, 1], [10.0, 10.0]))
    assert a["trips"] == [] and a["totals"]["trips"] == 0
    a = both(custom([0, 1, 2], [math.nan, math.nan, math.nan]))
    assert a["trips"] == [] and a["quality"]["missing_after"]["speed"] == 3


def test_every_channel_is_reported_missing_when_absent(demo):
    log, _ = demo
    a = pipeline.analyze(log.head(500))
    assert a["log"]["samples"] == 500 and all(a["log"]["channels"].values())


def test_runs_helper():
    s, e = pipeline.runs(np.array([True, True, False, True, False, False, True]))
    assert s.tolist() == [0, 3, 6] and e.tolist() == [1, 3, 6]
    s, e = pipeline.runs(np.array([], dtype=bool))
    assert s.size == 0 and e.size == 0
