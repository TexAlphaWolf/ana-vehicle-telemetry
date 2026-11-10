from __future__ import annotations

import numpy as np

from tests.conftest import steady
from vehicletelemetry import analysis, report
from vehicletelemetry.logio import make_log
from vehicletelemetry.params import Params


def test_report_with_truth_has_every_section(demo):
    log, truth = demo
    rep = analysis.build_report(log, Params(), truth, "test")
    md = report.render_report(rep)
    for h in (
        "# Vehicle telemetry: test",
        "## 1. Data quality",
        "## 2. Trips",
        "## 3. Fuel consumption",
        "## 4. Driving style",
        "## 5. Sensor faults",
        "## 6. Against the truth",
    ):
        assert h in md
    assert md.count("\n| ") > 40
    assert rep["showcase"] and len(rep["showcase"]["t_s"]) <= analysis.TRACE_POINTS + 1


def test_report_without_truth_or_fuel():
    log = steady(36.0, 400)
    rep = analysis.build_report(log, Params(), None, "plain")
    md = report.render_report(rep)
    assert "## 6." not in md and "## 3." not in md and "L/100 km on average" not in md
    assert "No overheating or stuck sensor found." in md


def test_report_with_no_trips():
    rep = analysis.build_report(steady(5.0, 20), Params(), None, "idle")
    assert rep["showcase"] is None
    assert "0 trips" in report.render_report(rep)


def test_long_trip_tables_are_cut(demo):
    log, _ = demo
    rep = analysis.build_report(log, Params(), None, "x")
    rep["analysis"]["trips"] = rep["analysis"]["trips"] * 10
    assert "more trips" in report.render_report(rep)


def test_consumption_bins_weight_by_distance(demo):
    log, _ = demo
    trips = analysis.build_report(log, Params(), None, "x")["analysis"]["trips"]
    rows = report.consumption_by_speed(trips)
    assert sum(r["trips"] for r in rows) == len(trips)
    for r in rows:
        sel = [t for t in trips if r["lo"] <= t["avg_speed_kmh"] < r["hi"]]
        if sel:
            assert r["l_per_100km"] == np.float64(
                sum(t["fuel_l"] for t in sel) / sum(t["fuel_distance_km"] for t in sel) * 100
            )


def test_figures_are_written(demo, tmp_path):
    log, truth = demo
    for t, name in ((truth, "with"), (None, "without")):
        rep = analysis.build_report(log, Params(), t, "x")
        report.report_figure(rep, tmp_path / f"{name}.png")
        assert (tmp_path / f"{name}.png").read_bytes()[1:4] == b"PNG"
    rep = analysis.build_report(make_log(steady(0, 3).t0, np.arange(4.0), speed=np.zeros(4)), Params(), None, "empty")
    report.report_figure(rep, tmp_path / "empty.png")


def test_times_are_formatted():
    assert (
        report._t(0.0000123) == "12 µs"
        and report._t(0.0123) == "12.3 ms"
        and report._t(3.0) == "3.00 s"
        and report._t(12345.0) == "12,345 s"
    )
    assert report.pct(None) == "n/a" and report.num(None) == "n/a" and report.speed_label(100, 1000) == "100+ km/h"
