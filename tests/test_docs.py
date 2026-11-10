"""The documentation must say what the measurements say."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pytest

from vehicletelemetry import cli, pipeline, report
from vehicletelemetry.generate import GenParams, generate
from vehicletelemetry.params import Params
from vehicletelemetry.report import pct

ROOT = Path(__file__).resolve().parent.parent
REPORT = json.loads((ROOT / "docs" / "report.json").read_text(encoding="utf-8"))
BENCH = json.loads((ROOT / "docs" / "bench.json").read_text(encoding="utf-8"))
README = (ROOT / "README.md").read_text(encoding="utf-8")
ANALYSIS = (ROOT / "docs" / "analysis.md").read_text(encoding="utf-8")
A, ACC = REPORT["analysis"], REPORT["accuracy"]
TOT, Q, TRIPS = A["totals"], A["quality"], A["trips"]
SW = BENCH["accuracy"]
ROWS = {r["samples"]: r["seconds"] for r in BENCH["analysis"]}
REF_RATE = BENCH["reference"]["samples"] / BENCH["reference"]["seconds"]


def assert_close(a: Any, b: Any) -> None:
    """Equal structure; numbers equal to 12 digits (the file keeps full precision)."""
    if isinstance(b, dict):
        assert a.keys() == b.keys()
        for k in b:
            assert_close(a[k], b[k])
    elif isinstance(b, list):
        assert len(a) == len(b)
        for x, y in zip(a, b, strict=True):
            assert_close(x, y)
    elif isinstance(b, float):
        assert a == pytest.approx(b, rel=1e-12)
    else:
        assert a == b


def test_the_benchmark_is_what_the_text_says_it_is() -> None:
    env = BENCH["environment"]
    assert env["vehicletelemetry"] == "1.0.0" and env["seed"] == 1 and env["repeat"] == 5 and env["cpus"] == 12
    assert env["python"] == "3.14.10" and env["numpy"] == "2.5.4"
    assert sorted(ROWS) == [10_000, 100_000, 1_000_000, 3_000_000]
    v = BENCH["verification"]
    assert (
        v["ok"] is True
        and v["checks"] == 51
        and v["numbers"] == 15_960
        and v["max_rel_error"] == pytest.approx(2.08e-16, rel=1e-2)
    )
    assert SW["seeds"] == 20 and SW["days"] == 14


def test_markdown_is_the_render_of_the_json(tmp_path: Path) -> None:
    for name in ("report", "bench"):
        out = tmp_path / f"{name}.md"
        assert cli.main(["render", str(ROOT / "docs" / f"{name}.json"), "-o", str(out)]) == 0
        assert out.read_text(encoding="utf-8") == (ROOT / "docs" / f"{name}.md").read_text(encoding="utf-8")


def test_the_report_is_what_the_demo_gives_today() -> None:
    log, truth = generate(GenParams())
    from vehicletelemetry import analysis

    fresh = analysis.build_report(log, Params(), truth, "demo drive log (synthetic, 14 days, seed 1)")
    assert_close(json.loads(json.dumps(fresh)), REPORT)


def test_figures_exist() -> None:
    for name in ("report.png", "bench.png"):
        assert (ROOT / "docs" / name).stat().st_size > 10_000


@pytest.mark.parametrize("text", [README, ANALYSIS], ids=["README", "analysis"])
def test_no_scaffold_left(text: str) -> None:
    assert not re.search(
        r"work in progress|TODO|TBD|lorem|measurements pending|provisional|pre-measurement", text, re.I
    )


@pytest.mark.parametrize("name", ["README.md", "docs/analysis.md"])
def test_local_links_resolve(name: str) -> None:
    path = ROOT / name
    for target in re.findall(r"\]\(([^)#\s]+)(?:#[^)]*)?\)", path.read_text(encoding="utf-8")):
        if target.startswith(("http://", "https://")):
            continue
        assert (path.parent / target).exists(), f"{name}: {target}"


def test_the_real_output_block_is_the_real_output(capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main(["analyze"]) == 0
    block = re.search(r"`vtel analyze` \(the demo log\):\n\n```text\n(.*?)```", README, re.S)
    assert block and block.group(1) == capsys.readouterr().out


def test_the_readme_numbers_are_the_measurements() -> None:
    lg = A["log"]
    must = [
        f"{lg['samples']:,} samples",
        f"{TOT['trips']} trips",
        f"{TOT['distance_km']:.1f} km in {TOT['valid_h']:.1f} hours",
        f"{TOT['l_per_100km']:.2f} L/100 km",
        f"{100 * TOT['idle_share']:.1f}% of the",
        f"{min(t['l_per_100km'] for t in TRIPS):.2f} to {max(t['l_per_100km'] for t in TRIPS):.2f} L/100 km",
        f"{TOT['harsh_accel']} harsh accelerations ({TOT['harsh_accel_per_100km']:.2f} per 100 km)",
        f"{TOT['harsh_brake']} harsh brakings ({TOT['harsh_brake_per_100km']:.2f} per 100 km)",
        f"{TOT['harsh_accel'] + TOT['harsh_brake']} harsh events",
        f"{Q['spikes']} speed spikes",
        f"{sum(Q['out_of_range'].values())} values outside the",
        f"{Q['dropout_runs']} holes in the speed signal",
        f"{TOT['overheat_events']} overheatings",
        f"{TOT['flatline_events']} stuck sensors",
        f"all {ACC['trips']['true']} trips are found",
        f"is off by {100 * ACC['trips']['distance_total_error']:.2f}%",
        f"{100 * ACC['trips']['consumption_error_median']:.2f}% (median) and {100 * ACC['trips']['consumption_error_max']:.2f}% (worst)",
        f"{BENCH['environment']['cpus']} CPUs, Python {BENCH['environment']['python']} and\nNumPy {BENCH['environment']['numpy']}",
        f"{SW['trips']['matched']} trips, {SW['true_km']:,.0f} km",
        f"{pct(SW['distance_error_median'], 2)[:-1]}% (median)",
        f"{pct(SW['distance_error_p95'], 2)[:-1]}% (95th percentile)",
        f"{pct(SW['consumption_error_median'], 2)[:-1]}% and {pct(SW['consumption_error_p95'], 2)[:-1]}%",
        f"{SW['events']['harsh_accel']['tp']} of {SW['events']['harsh_accel']['true']} harsh accelerations",
        f"{SW['events']['harsh_brake']['tp']} of {SW['events']['harsh_brake']['true']} harsh\n   brakings",
        f"{BENCH['verification']['max_rel_error']:.2e}",
        f"{BENCH['verification']['checks']}\n   comparisons and {BENCH['verification']['numbers']:,} numbers",
        f"{max(ROWS):,} samples ({max(ROWS) / 3600:.0f} hours of driving)",
        f"{ROWS[max(ROWS)]:.2f} s, {max(ROWS) / ROWS[max(ROWS)] / 1e6:.2f} million samples a second",
        f"{REF_RATE:,.0f} a second",
    ]
    flat = re.sub(r"\s+", " ", README)
    for s in must:
        assert re.sub(r"\s+", " ", s) in flat, s


def test_the_two_bin_claims() -> None:
    bins = {(b["lo"], b["hi"]): b for b in report.consumption_by_speed(TRIPS)}
    assert f"{bins[(0, 25)]['l_per_100km']:.2f} L/100 km under 25 km/h" in README
    assert f"{bins[(40, 60)]['l_per_100km']:.2f} at\n   40 to 60 km/h" in README
    assert f"{bins[(80, 100)]['l_per_100km']:.2f} at 80 to 100 km/h" in README
    # the minimum is in the 40 to 60 group, as the analysis says
    pts = [b for b in bins.values() if b["l_per_100km"] is not None]
    assert min(pts, key=lambda b: b["l_per_100km"])["lo"] == 40
    mid = bins[(40, 60)]["trips"] + bins[(60, 80)]["trips"]
    assert mid == 20 and len(TRIPS) == 27
    assert (bins[(40, 60)]["km"] + bins[(60, 80)]["km"]) / TOT["distance_km"] == pytest.approx(0.83, abs=0.005)


def test_the_analysis_table_rows() -> None:
    for b in report.consumption_by_speed(TRIPS):
        if b["trips"]:
            assert (
                f"| {report.speed_label(b['lo'], b['hi'])} | {b['trips']} | {b['km']:.1f} | {b['l_per_100km']:.2f} |"
                in ANALYSIS
            )
    for k, label in report.DETECTORS.items():
        r = SW["events"][k]
        hole = str(r["missed_in_hole"]) if k.startswith("harsh") else "-"
        row = f"| {label} | {r['true']} | {r['found']} | {r['fn']} | {hole} | {pct(r['precision'], 1)} | {pct(r['recall'], 1)} |"
        assert row in ANALYSIS, row
    for n, secs in ROWS.items():
        assert f"| {n:,} | {n / 3600:.0f} | {report._t(secs)} | {n / secs:,.0f} |" in ANALYSIS
    assert (
        f"{REF_RATE:,.0f} samples a second" in ANALYSIS
        and f"{BENCH['parse']['samples'] / BENCH['parse']['seconds']:,.0f} samples a second" in ANALYSIS
    )


def test_what_the_analysis_says_about_holes_faults_and_events() -> None:
    holes = A["anomalies"]["dropouts"]
    short = [h for h in holes if h["filled"]]
    left = [h for h in holes if not h["filled"]]
    assert (len(holes), len(short), len(left)) == (20, 15, 5)
    assert all(14 <= round(h["t1"] - h["t0"]) <= 24 for h in left) and all(h["t1"] - h["t0"] <= 9 for h in short)
    assert sum(1 for t in TRIPS if t["covered_share"] < 1) == 4  # "four trips have a share with no known speed"
    assert Q["short_trips_dropped"] == 0 and A["log"]["median_dt_s"] == pytest.approx(1.0, abs=0.005)
    ev = A["events"]
    assert max(e["peak_ms2"] for e in ev["harsh_accel"]) == pytest.approx(3.69, abs=0.005)
    assert max(e["peak_ms2"] for e in ev["harsh_brake"]) == pytest.approx(4.67, abs=0.005)
    assert sorted(round(e["duration_s"]) for e in ev["overheat"]) == [75, 76]
    assert sorted(round(e["peak_c"], 1) for e in ev["overheat"]) == [115.7, 116.0]
    assert sorted(round(e["duration_s"]) for e in ev["flatline"]) == [44, 47, 66] and {
        e["channel"] for e in ev["flatline"]
    } == {"load"}
    for t, km, n, per100 in ((18, 3.2, 2, 61.6), (26, 5.1, 2, 39.5)):
        x = TRIPS[t - 1]
        assert round(x["distance_km"], 1) == km and x["harsh_accel"] + x["harsh_brake"] == n
        assert round(n / x["distance_km"] * 100, 1) == per100
    assert (
        ACC["trips"]["duration_error_max_s"] < 12.5 and f"{ACC['trips']['distance_error_max'] * 100:.2f}%" in ANALYSIS
    )


def test_every_miss_over_the_sweep_is_explained_and_nothing_is_invented() -> None:
    ev = SW["events"]
    assert all(r["fp"] == 0 for r in ev.values())
    assert sum(r["found"] for r in ev.values()) == 1400
    for k in ("harsh_accel", "harsh_brake"):
        assert ev[k]["fn"] == ev[k]["missed_in_hole"]
    assert SW["trips"]["true"] == SW["trips"]["found"] == SW["trips"]["matched"] == 564


def test_the_speed_claims() -> None:
    speedups = [(n / REF_RATE) / s for n, s in ROWS.items()]
    assert round(min(speedups)) == 12 and round(max(speedups)) == 15
    year = 365 * 86400 / (max(ROWS) / ROWS[max(ROWS)])
    assert round(year) == 10
    assert BENCH["parse"]["samples"] / BENCH["parse"]["seconds"] < 0.1 * min(n / s for n, s in ROWS.items())


def test_spike_removal_changes_the_maximum_speed_not_the_counts() -> None:
    log, _ = generate(GenParams())
    with_removal = pipeline.analyze(log, Params())
    without = pipeline.analyze(log, Params(phys_ms2=1e5))
    for k in ("harsh_accel", "harsh_brake"):
        assert with_removal["totals"][k] == without["totals"][k]
    worse = [
        (a, b)
        for a, b in zip(with_removal["trips"], without["trips"], strict=True)
        if b["max_speed_kmh"] > a["max_speed_kmh"] + 1
    ]
    assert len(worse) == 6
    assert max(b["max_speed_kmh"] for _, b in worse) == pytest.approx(212.5, abs=0.05)
    assert max(a["max_speed_kmh"] for a in with_removal["trips"]) == pytest.approx(131.5, abs=0.05)
    assert without["totals"]["distance_km"] - with_removal["totals"]["distance_km"] == pytest.approx(0.25, abs=0.005)


def test_the_stop_bridge_and_threshold_claims() -> None:
    """The two bugs the truth found stay fixed: the defaults are the ones the docs give."""
    p = Params()
    assert p.bridge_s == 60.0 and p.stop_kmh == 2.0 and p.park_s == 600.0 and p.max_fill_s == 10.0 and p.gap_s == 30.0
    assert p.accel_ms2 == 2.5 and p.brake_ms2 == 3.0 and p.min_event_s == 1.5 and p.phys_ms2 == 12.0
    method = (ROOT / "docs" / "method.md").read_text(encoding="utf-8")
    for row in (
        "| `bridge_s` | 60 s |",
        "| `stop_kmh` | 2 km/h |",
        "| `park_s` | 600 s |",
        "| `accel_ms2` | 2.5 m/s2 |",
        "| `brake_ms2` | 3.0 m/s2 |",
    ):
        assert row in method
