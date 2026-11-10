"""Command line: generate, validate, analyze, verify, bench, render."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import fields
from pathlib import Path
from typing import Any

from vehicletelemetry import __version__, analysis, bench, logio, report, verify
from vehicletelemetry.generate import GenParams, Truth, generate
from vehicletelemetry.logio import Log, LogError
from vehicletelemetry.params import ParamError, Params

Error = (LogError, ParamError, ValueError)


def params_from(args: argparse.Namespace) -> Params:
    given = {f.name: getattr(args, f.name) for f in fields(Params) if getattr(args, f.name, None) is not None}
    return Params(**given)


def read_truth(path: str) -> Truth:
    try:
        return Truth.from_dict(json.loads(Path(path).read_text(encoding="utf-8")))
    except (OSError, json.JSONDecodeError, KeyError) as exc:
        raise LogError(f"cannot read the truth file {path}: {exc}") from exc


def summary_lines(rep: dict[str, Any]) -> list[str]:
    a = rep["analysis"]
    t, q = a["totals"], a["quality"]
    lg = a["log"]
    lines = [
        f"{rep['source']}: {lg['samples']:,} samples, {t['trips']} trips, {t['distance_km']:,.1f} km in {t['valid_h']:.1f} h"
        + (f", {t['l_per_100km']:.2f} L/100 km" if t["l_per_100km"] is not None else ""),
        f"harsh acceleration {t['harsh_accel']} ({t['harsh_accel_per_100km']:.2f} per 100 km), "
        f"harsh braking {t['harsh_brake']} ({t['harsh_brake_per_100km']:.2f} per 100 km)",
        f"faults: {t['overheat_events']} overheating, {t['flatline_events']} stuck sensor; {q['spikes']} spikes, "
        f"{sum(q['out_of_range'].values())} out-of-range samples, {q['dropout_runs']} holes in the speed signal",
    ]
    acc = rep["accuracy"]
    if acc:
        tr = acc["trips"]
        ev = acc["events"]
        lines.append(
            f"against the truth: {tr['matched']} of {tr['true']} trips matched, distance error {100 * tr['distance_total_error']:+.2f}% "
            f"in total, consumption error {100 * tr['consumption_error_median']:.2f}% (median per trip)"
        )
        found = sum(r["tp"] for r in ev.values())
        total = sum(r["true"] for r in ev.values())
        false = sum(r["fp"] for r in ev.values())
        lines.append(f"events and faults: {found} of {total} found, {false} false alarms")
    return lines


def cmd_generate(a: argparse.Namespace) -> int:
    log, truth = generate(GenParams(days=a.days, seed=a.seed, anomaly_rate=0.0 if a.clean else 1.0))
    out = Path(a.output)
    if out.exists():
        raise LogError(f"{out} already exists")
    logio.write_csv(log, out)
    print(f"written: {out} ({len(log):,} samples, {len(truth.trips)} trips)")
    if a.truth:
        Path(a.truth).write_text(json.dumps(truth.to_dict(), indent=1) + "\n", encoding="utf-8")
        print(f"written: {a.truth}")
    return 0


def cmd_validate(a: argparse.Namespace) -> int:
    log = logio.read_csv(a.file, a.afr, a.density)
    present = [c for c, ok in log.present().items() if ok]
    print(
        f"ok: {len(log):,} samples from {logio.clock(log.t0, log.t[0])} to {logio.clock(log.t0, log.t[-1])}; channels: {', '.join(present)}"
    )
    return 0


def load(a: argparse.Namespace) -> tuple[Log, Truth | None, str]:
    if a.file:
        log = logio.read_csv(a.file, a.afr, a.density)
        return log, read_truth(a.truth) if a.truth else None, a.file
    if a.truth:
        raise LogError("--truth needs the log file it belongs to")
    log, truth = generate(GenParams())
    return log, truth, "demo drive log (synthetic, 14 days, seed 1)"


def cmd_analyze(a: argparse.Namespace) -> int:
    log, truth, source = load(a)
    rep = analysis.build_report(log, params_from(a), truth, source)
    for line in summary_lines(rep):
        print(line)
    if a.out:
        out = Path(a.out)
        out.mkdir(parents=True, exist_ok=True)
        (out / "report.json").write_text(json.dumps(rep, indent=1) + "\n", encoding="utf-8")
        (out / "report.md").write_text(report.render_report(rep), encoding="utf-8")
        report.report_figure(rep, out / "summary.png")
        print(f"written: {out / 'report.json'}, {out / 'report.md'}, {out / 'summary.png'}")
    return 0


def cmd_verify(a: argparse.Namespace) -> int:
    checks = verify.verify(a.draws, a.seed)
    bad = [c for c in checks if not c.ok]
    for c in checks:
        print(
            f"{'ok  ' if c.ok else 'FAIL'} {c.name}: {c.numbers:,} values, largest relative difference {c.max_rel_error:.2e} ({c.detail})"
        )
    print(f"{len(checks) - len(bad)} of {len(checks)} comparisons agree with the literal implementation")
    return 1 if bad else 0


def cmd_bench(a: argparse.Namespace) -> int:
    sizes = [int(p.replace("_", "")) for p in a.sizes.split(",") if p.strip()]
    if not sizes or any(s < 100 for s in sizes):
        raise ValueError("--sizes needs at least one whole number of 100 or more")
    result = bench.run_bench(
        sizes, a.repeat, a.seed, a.draws, a.cmdline, a.ref_samples, a.seeds, lambda m: print(m, flush=True)
    )
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "bench.json").write_text(json.dumps(result, indent=1) + "\n", encoding="utf-8")
    (out / "bench.md").write_text(report.render_bench(result), encoding="utf-8")
    report.bench_figure(result, out / "summary.png")
    print(f"written: {out / 'bench.json'}, {out / 'bench.md'}, {out / 'summary.png'}")
    return 0 if result["verification"]["ok"] else 1


def cmd_render(a: argparse.Namespace) -> int:
    try:
        data = json.loads(Path(a.file).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise LogError(f"cannot read {a.file}: {exc}") from exc
    kind = data.get("kind") if isinstance(data, dict) else None
    if kind not in ("report", "bench"):
        raise LogError(f"{a.file} is neither a report.json nor a bench.json")
    text = report.render_report(data) if kind == "report" else report.render_bench(data)
    if a.output:
        Path(a.output).write_text(text, encoding="utf-8")
        print(f"written: {a.output}")
    else:
        print(text, end="")
    if a.figure:
        (report.report_figure if kind == "report" else report.bench_figure)(data, Path(a.figure))
        print(f"written: {a.figure}")
    return 0


HELP = {
    "gap_s": "seconds between samples above which the logger was off",
    "max_fill_s": "longest hole (s) that is interpolated",
    "stop_kmh": "speed below which the vehicle is stopped",
    "park_s": "seconds standing that end a trip",
    "bridge_s": "longest hole of unknown speed (s) that does not interrupt a stop",
    "min_trip_m": "shortest trip kept (m)",
    "accel_ms2": "harsh acceleration threshold (m/s2)",
    "brake_ms2": "harsh braking threshold (m/s2, positive)",
    "min_event_s": "shortest harsh event (s)",
    "phys_ms2": "acceleration no car can reach: a jump up and back this fast is a spike",
    "rpm_high": "rpm counted as high",
    "coolant_max_c": "coolant temperature above which the engine overheats (C)",
    "overheat_s": "seconds above it that make an event",
    "flat_s": "seconds without any change that make a sensor stuck",
    "afr": "air-fuel ratio, for a mass air flow column",
    "density_g_l": "fuel density in g/L, for a mass air flow column",
}


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="vtel", description="Telemetry from OBD-II drive logs.")
    p.add_argument("--version", action="version", version=f"vtel {__version__}")
    sub = p.add_subparsers(dest="command", required=True)

    def reading(sp: argparse.ArgumentParser) -> None:
        sp.add_argument("--afr", type=float, default=14.7, help=HELP["afr"])
        sp.add_argument("--density", type=float, default=745.0, help=HELP["density_g_l"])

    g = sub.add_parser("generate", help="write a synthetic drive log (and its truth)")
    g.add_argument("-o", "--output", required=True)
    g.add_argument("--truth", help="also write the truth (trips, harsh ramps, injected faults) here")
    g.add_argument("--days", type=int, default=14)
    g.add_argument("--seed", type=int, default=1)
    g.add_argument("--clean", action="store_true", help="no injected faults")
    g.set_defaults(func=cmd_generate)

    v = sub.add_parser("validate", help="read a log and say what is in it")
    v.add_argument("file")
    reading(v)
    v.set_defaults(func=cmd_validate)

    r = sub.add_parser("analyze", help="trips, consumption, harsh driving and faults (the demo log without a file)")
    r.add_argument("file", nargs="?", help="drive log CSV (default: a synthetic demo log, with its truth)")
    r.add_argument("--truth", help="the truth file of a synthetic log, to score the analysis")
    r.add_argument("--out", help="write report.json, report.md and summary.png here")
    reading(r)
    for f in fields(Params):
        if f.name in ("afr", "density_g_l"):
            continue
        r.add_argument(
            "--" + f.name.replace("_", "-"), dest=f.name, type=float, help=f"{HELP[f.name]} (default {f.default:g})"
        )
    r.set_defaults(func=cmd_analyze, afr=14.7, density=745.0)

    c = sub.add_parser("verify", help="compare with the literal implementation on random logs; exit 1 on a difference")
    c.add_argument("--draws", type=int, default=25)
    c.add_argument("--seed", type=int, default=1)
    c.set_defaults(func=cmd_verify)

    b = sub.add_parser("bench", help="speed of the analysis, and agreement with the literal implementation")
    b.add_argument("--sizes", default="10000,100000,1000000,3000000")
    b.add_argument("--repeat", type=int, default=5)
    b.add_argument("--draws", type=int, default=50)
    b.add_argument("--ref-samples", type=int, default=20_000)
    b.add_argument("--seeds", type=int, default=20, help="synthetic logs (seeds 1..N) for the accuracy sweep")
    b.add_argument("--seed", type=int, default=1)
    b.add_argument("--out", default="vtel-out")
    b.set_defaults(func=cmd_bench)

    n = sub.add_parser("render", help="rebuild the Markdown (and figure) from report.json or bench.json")
    n.add_argument("file")
    n.add_argument("-o", "--output")
    n.add_argument("--figure")
    n.set_defaults(func=cmd_render)
    return p


def main(argv: list[str] | None = None) -> int:
    given = sys.argv[1:] if argv is None else argv
    args = build_parser().parse_args(given)
    args.cmdline = " ".join(given)
    try:
        return int(args.func(args))
    except Error as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
