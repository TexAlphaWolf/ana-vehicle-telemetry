"""Markdown and figures built from a report or a benchmark (both are plain JSON)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

COLORS = {"blue": "#0072b2", "orange": "#d55e00", "green": "#009e73", "pink": "#cc79a7", "grey": "#666666"}
SPEED_BINS = [(0, 25), (25, 40), (40, 60), (60, 80), (80, 100), (100, 1000)]
MAX_TRIPS_SHOWN = 40
DETECTORS = {
    "harsh_accel": "Harsh acceleration",
    "harsh_brake": "Harsh braking",
    "spike": "Speed spike",
    "out_of_range": "Out-of-range value",
    "dropout": "Hole in the speed signal",
    "overheat": "Overheating",
    "flatline": "Stuck sensor",
}


def pct(x: float | None, digits: int = 1) -> str:
    return "n/a" if x is None else f"{100 * x:.{digits}f}%"


def num(x: float | None, digits: int = 1) -> str:
    return "n/a" if x is None else f"{x:,.{digits}f}"


def minutes(s: float) -> str:
    return f"{s / 60:.0f}"


def speed_label(lo: int, hi: int) -> str:
    return f"{lo}+ km/h" if hi >= 1000 else f"{lo}-{hi} km/h"


def consumption_by_speed(trips: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for lo, hi in SPEED_BINS:
        sel = [x for x in trips if lo <= x["avg_speed_kmh"] < hi and x["fuel_l"] is not None]
        km = sum(x["fuel_distance_km"] for x in sel)
        rows.append(
            {
                "lo": lo,
                "hi": hi,
                "trips": len(sel),
                "km": sum(x["distance_km"] for x in sel),
                "l_per_100km": sum(x["fuel_l"] for x in sel) / km * 100.0 if km > 0 else None,
            }
        )
    return rows


def render_report(rep: dict[str, Any]) -> str:
    a = rep["analysis"]
    lg, q, tot, p = a["log"], a["quality"], a["totals"], a["params"]
    trips = a["trips"]
    present = [c for c, ok in lg["channels"].items() if ok]
    out = [
        f"# Vehicle telemetry: {rep['source']}",
        "",
        f"{lg['samples']:,} samples from {lg['start']} to {lg['end']} (median {lg['median_dt_s']:.2f} s between samples), in "
        f"{q['sessions']} recording sessions. Channels with data: {', '.join(present)}. The log holds {tot['trips']} trips, "
        f"{num(tot['distance_km'])} km in {num(tot['valid_h'])} hours of driving"
        + (f", {num(tot['l_per_100km'], 2)} L/100 km on average." if tot["l_per_100km"] is not None else "."),
        "",
        "## 1. Data quality",
        "",
        "| What | Count |",
        "|---|---|",
    ]
    oor = q["out_of_range"]
    out.append(
        f"| Samples outside the physical range (made missing) | {sum(oor.values())} ({', '.join(f'{c} {n}' for c, n in oor.items() if n) or 'none'}) |"
    )
    out.append(f"| Speed spikes (made missing) | {q['spikes']} |")
    dr = a["anomalies"]["dropouts"]
    filled = sum(1 for d in dr if d["filled"])
    out.append(
        f"| Holes in the speed signal | {len(dr)} ({filled} interpolated, at most {p['max_fill_s']:g} s; {len(dr) - filled} left as holes) |"
    )
    out.append(f"| Samples interpolated (all channels) | {sum(q['filled'].values())} |")
    out.append(f"| Samples still missing (all channels) | {sum(q['missing_after'].values())} |")
    out.append(f"| Very short trips dropped (under {p['min_trip_m']:g} m) | {q['short_trips_dropped']} |")
    out += [
        "",
        "## 2. Trips",
        "",
        "A trip ends when the vehicle stops for at least "
        f"{p['park_s'] / 60:g} minutes, or when the logger goes quiet for more than {p['gap_s']:g} seconds.",
        "",
        "| Trip | Start | Minutes | km | Average km/h | Max km/h | Standing | L/100 km | Harsh accel. | Harsh braking |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for x in trips[:MAX_TRIPS_SHOWN]:
        out.append(
            f"| {x['index'] + 1} | {x['start'][:16].replace('T', ' ')} | {minutes(x['duration_s'])} | {num(x['distance_km'])} | "
            f"{num(x['avg_speed_kmh'], 0)} | {num(x['max_speed_kmh'], 0)} | {pct(x['idle_share'], 0)} | {num(x['l_per_100km'], 2)} | "
            f"{x['harsh_accel']} | {x['harsh_brake']} |"
        )
    if len(trips) > MAX_TRIPS_SHOWN:
        out.append(f"| ... | {len(trips) - MAX_TRIPS_SHOWN} more trips | | | | | | | | |")
    bins = consumption_by_speed(trips)
    if any(b["l_per_100km"] is not None for b in bins):
        out += [
            "",
            "## 3. Fuel consumption by average speed",
            "",
            "Slow, stop-and-go trips burn fuel idling; fast trips spend it against drag. Trips are grouped by their average "
            "speed, and the consumption of a group is its fuel over its distance.",
            "",
            "| Average speed of the trip | Trips | km | L/100 km |",
            "|---|---|---|---|",
        ]
        for b in bins:
            if b["trips"]:
                out.append(
                    f"| {speed_label(b['lo'], b['hi'])} | {b['trips']} | {num(b['km'])} | {num(b['l_per_100km'], 2)} |"
                )
    ev = a["events"]
    out += [
        "",
        "## 4. Driving style",
        "",
        f"Harsh acceleration is above {p['accel_ms2']:g} m/s2 and harsh braking above {p['brake_ms2']:g} m/s2, for at least "
        f"{p['min_event_s']:g} s. Samples that jump up and back down by more than {p['phys_ms2']:g} m/s2 on both sides are spikes, "
        "not driving, and are removed first.",
        "",
        "| | Events | Per 100 km |",
        "|---|---|---|",
        f"| Harsh acceleration | {tot['harsh_accel']} | {num(tot['harsh_accel_per_100km'], 2)} |",
        f"| Harsh braking | {tot['harsh_brake']} | {num(tot['harsh_brake_per_100km'], 2)} |",
    ]
    worst = sorted(trips, key=lambda x: -(x["harsh_accel"] + x["harsh_brake"]) / max(x["distance_km"], 0.1))[:5]
    worst = [x for x in worst if x["harsh_accel"] + x["harsh_brake"] > 0]
    if worst:
        out += [
            "",
            "The trips with the most harsh events for their length:",
            "",
            "| Trip | Start | km | Harsh accel. | Harsh braking | Events per 100 km |",
            "|---|---|---|---|---|---|",
        ]
        for x in worst:
            n = x["harsh_accel"] + x["harsh_brake"]
            out.append(
                f"| {x['index'] + 1} | {x['start'][:16].replace('T', ' ')} | {num(x['distance_km'])} | {x['harsh_accel']} | {x['harsh_brake']} | {num(n / x['distance_km'] * 100, 1)} |"
            )
    out += ["", "## 5. Sensor faults", ""]
    if ev["overheat"] or ev["flatline"]:
        out += ["| Fault | Start | Seconds | Detail |", "|---|---|---|---|"]
        for e in ev["overheat"]:
            out.append(
                f"| Coolant above {p['coolant_max_c']:g} C | {e['start'][:19].replace('T', ' ')} | {num(e['duration_s'], 0)} | peak {num(e['peak_c'])} C |"
            )
        for e in ev["flatline"]:
            out.append(
                f"| {e['channel']} stuck | {e['start'][:19].replace('T', ' ')} | {num(e['duration_s'], 0)} | at {num(e['value'])} |"
            )
    else:
        out.append("No overheating or stuck sensor found.")
    acc = rep.get("accuracy")
    if acc:
        t = acc["trips"]
        out += [
            "",
            "## 6. Against the truth",
            "",
            "The log is synthetic, so the true distance and fuel of every trip, every harsh ramp and every injected fault are known.",
            "",
            f"Trips: {t['found']} found for {t['true']} true ({t['matched']} matched, {t['extra']} extra). Distance: total error "
            f"{pct(t['distance_total_error'], 2)}, median per trip {pct(t['distance_error_median'], 2)}, worst {pct(t['distance_error_max'], 2)}. "
            f"Consumption: median error per trip {pct(t['consumption_error_median'], 2)}, worst {pct(t['consumption_error_max'], 2)}. "
            f"Trip duration: median error {num(t['duration_error_median_s'], 1)} s, worst {num(t['duration_error_max_s'], 1)} s.",
            "",
            "| Detector | True | Found | Correct | False alarms | Missed | Precision | Recall |",
            "|---|---|---|---|---|---|---|---|",
        ]
        names = {
            "harsh_accel": "Harsh acceleration",
            "harsh_brake": "Harsh braking",
            "spike": "Speed spike",
            "out_of_range": "Out-of-range value",
            "dropout": "Hole in the speed signal",
            "overheat": "Overheating",
            "flatline": "Stuck sensor",
        }
        for k, label in names.items():
            r = acc["events"][k]
            out.append(
                f"| {label} | {r['true']} | {r['found']} | {r['tp']} | {r['fp']} | {r['fn']} | {pct(r['precision'], 0)} | {pct(r['recall'], 0)} |"
            )
        d = acc["dropouts"]
        out += [
            "",
            f"Of the {d['short'] + d['long']} holes injected ({d['short']} short, {d['long']} long), {d['filled_found']} were interpolated and {d['left_found']} left as holes.",
        ]
    return "\n".join(out) + "\n"


def report_figure(rep: dict[str, Any], path: Path) -> None:
    a = rep["analysis"]
    trips = a["trips"]
    fig, axes = plt.subplots(1, 3, figsize=(16, 4.8), dpi=130)
    ax = axes[0]
    sc = rep.get("showcase")
    if sc:
        ax.plot([x / 60 for x in sc["t_s"]], sc["speed_kmh"], color=COLORS["blue"], lw=1.1)
        k = sc["trip"]
        first = True
        for kind, color, label in (
            ("harsh_accel", COLORS["green"], "harsh acceleration"),
            ("harsh_brake", COLORS["orange"], "harsh braking"),
        ):
            xs = [(e["t0"] - trips[k]["start_s"]) / 60 for e in a["events"][kind] if e["trip"] == k]
            ys = [
                max((s for t_, s in zip(sc["t_s"], sc["speed_kmh"], strict=True) if abs(t_ - x * 60) < 6), default=0)
                for x in xs
            ]
            ax.scatter(xs, ys, color=color, s=38, zorder=3, label=label)
            first = False
        del first
        ax.legend(frameon=False, fontsize=8, loc="upper left")
        ax.set_title(f"Trip {k + 1}: the one with the most harsh events", fontsize=10)
    ax.set_xlabel("minutes into the trip")
    ax.set_ylabel("speed (km/h)")
    ax.set_ylim(0, None)
    ax = axes[1]
    pts = [x for x in trips if x["l_per_100km"] is not None]
    ax.scatter(
        [x["avg_speed_kmh"] for x in pts],
        [x["l_per_100km"] for x in pts],
        s=[10 + 2.5 * x["distance_km"] for x in pts],
        color=COLORS["blue"],
        alpha=0.7,
    )
    ax.set_xlabel("average speed of the trip (km/h)")
    ax.set_ylabel("fuel (L/100 km)")
    ax.set_ylim(0, None)
    ax.set_title("Consumption of every trip (dot size: distance)", fontsize=10)
    ax = axes[2]
    acc = rep.get("accuracy")
    if acc:
        labels = {
            "harsh_accel": "harsh accel.",
            "harsh_brake": "harsh braking",
            "spike": "spike",
            "out_of_range": "out of range",
            "dropout": "dropout",
            "overheat": "overheat",
            "flatline": "stuck",
        }
        ys = list(range(len(labels)))
        rec = [acc["events"][k]["recall"] or 0 for k in labels]
        prec = [acc["events"][k]["precision"] or 0 for k in labels]
        ax.barh([y + 0.2 for y in ys], rec, 0.38, color=COLORS["green"], label="recall (found / true)")
        ax.barh([y - 0.2 for y in ys], prec, 0.38, color=COLORS["blue"], label="precision (true / found)")
        ax.set_yticks(ys, [f"{lab} ({acc['events'][k]['true']})" for k, lab in labels.items()], fontsize=8)
        ax.invert_yaxis()
        ax.set_xlim(0, 1.05)
        ax.legend(frameon=False, fontsize=8, loc="upper center", bbox_to_anchor=(0.5, -0.1), ncol=2)
        ax.set_title("Detection against the injected truth", fontsize=10)
    else:
        per = [(x["harsh_accel"] + x["harsh_brake"]) / max(x["distance_km"], 0.1) * 100 for x in trips]
        ax.bar(range(len(per)), per, color=COLORS["orange"])
        ax.set_xlabel("trip")
        ax.set_ylabel("harsh events per 100 km")
        ax.set_title("Harsh events per 100 km", fontsize=10)
    for ax in axes:
        ax.spines[["top", "right"]].set_visible(False)
        ax.grid(alpha=0.25)
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)


def render_bench(b: dict[str, Any]) -> str:
    e = b["environment"]
    out = [
        "# Benchmark",
        "",
        f"Run on {e['system']}, {e['cpus']} CPUs, Python {e['python']}, NumPy {e['numpy']}; seed {e['seed']}; each time is the median of "
        f"{e['repeat']} runs; command `{e['command']}`.",
        "",
        "## 1. Analysis time by log size",
        "",
        "Logs are synthetic drive logs at about one sample per second (about 3,750 samples, an hour, per day of driving). *Literal "
        f"implementation* is the time of the sample-by-sample Python version on a log of {b['reference']['samples']:,} samples, scaled to "
        "each size: an extrapolation, not a measurement.",
        "",
        "| Samples | Hours of driving | Time | Samples per second | Literal implementation (extrapolated) | Speed-up |",
        "|---|---|---|---|---|---|",
    ]
    ref_rate = b["reference"]["samples"] / b["reference"]["seconds"]
    for r in b["analysis"]:
        lit = r["samples"] / ref_rate
        out.append(
            f"| {r['samples']:,} | {r['samples'] / 3600:,.0f} | {_t(r['seconds'])} | {r['samples'] / r['seconds']:,.0f} | {_t(lit)} | {lit / r['seconds']:,.0f}x |"
        )
    out += [
        "",
        f"The literal implementation analyses {b['reference']['samples']:,} samples in {_t(b['reference']['seconds'])} "
        f"({ref_rate:,.0f} samples per second).",
        "",
        "## 2. Reading, writing and generating",
        "",
        "| Step | Samples | Time | Samples per second |",
        "|---|---|---|---|",
    ]
    for k, label in (
        ("generate", "Generate a log with its truth"),
        ("write", "Write the CSV text"),
        ("parse", "Parse the CSV text"),
    ):
        r = b[k]
        out.append(f"| {label} | {r['samples']:,} | {_t(r['seconds'])} | {r['samples'] / r['seconds']:,.0f} |")
    sw = b["accuracy"]
    tr = sw["trips"]
    out += [
        "",
        f"## 3. Accuracy against the truth, over {sw['seeds']} synthetic logs",
        "",
        f"Logs of {sw['days']} days with seeds 1 to {sw['seeds']} ({sw['true_km']:,.0f} km, {tr['true']} trips). Trips: {tr['matched']} of "
        f"{tr['true']} matched, {tr['found'] - tr['matched']} extra. Error against the true value, per trip, median and 95th percentile: "
        f"distance {pct(sw['distance_error_median'], 2)} and {pct(sw['distance_error_p95'], 2)}; consumption "
        f"{pct(sw['consumption_error_median'], 2)} and {pct(sw['consumption_error_p95'], 2)}; trip length {sw['duration_error_median_s']:.1f} s "
        f"and {sw['duration_error_p95_s']:.1f} s.",
        "",
        "| Detector | True | Found | Correct | False alarms | Missed | Missed inside a hole | Precision | Recall |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for k, label in DETECTORS.items():
        r = sw["events"][k]
        hole = str(r["missed_in_hole"]) if k.startswith("harsh") else "-"
        out.append(
            f"| {label} | {r['true']} | {r['found']} | {r['tp']} | {r['fp']} | {r['fn']} | {hole} | {pct(r['precision'], 1)} | {pct(r['recall'], 1)} |"
        )
    v = b["verification"]
    out += [
        "",
        "## 4. Agreement with the literal implementation",
        "",
        f"{v['checks']} comparisons (a generated log and {v['checks'] - 1} random, partly spoiled logs with random thresholds): "
        f"{v['numbers']:,} numbers compared. Largest relative difference {v['max_rel_error']:.2e} (tolerance {v['tolerance']:.0e}); "
        + ("all match." if v["ok"] else "THERE ARE DIFFERENCES."),
        "",
    ]
    return "\n".join(out)


def _t(s: float) -> str:
    if s < 1e-3:
        return f"{s * 1e6:.0f} µs"
    if s < 1:
        return f"{s * 1e3:.1f} ms"
    if s < 600:
        return f"{s:.2f} s"
    return f"{s:,.0f} s"


def bench_figure(b: dict[str, Any], path: Path) -> None:
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.6), dpi=130)
    rows = b["analysis"]
    ref_rate = b["reference"]["samples"] / b["reference"]["seconds"]
    ax = axes[0]
    xs = [r["samples"] for r in rows]
    ax.plot(xs, [r["seconds"] for r in rows], "o-", color=COLORS["blue"], label="NumPy analysis (measured)")
    ax.plot(
        xs, [x / ref_rate for x in xs], "s--", color=COLORS["orange"], label="literal implementation (extrapolated)"
    )
    ax.set_xscale("log")
    ax.set_yscale("log")
    ax.set_xlabel("samples in the log")
    ax.set_ylabel("seconds")
    ax.legend(frameon=False, fontsize=8)
    ax.set_title("Analysis time by log size", fontsize=10)
    ax = axes[1]
    ax.bar([str(r["samples"]) for r in rows], [r["samples"] / r["seconds"] / 1e6 for r in rows], color=COLORS["blue"])
    ax.axhline(ref_rate / 1e6, color=COLORS["orange"], ls="--", label="literal implementation")
    ax.set_xlabel("samples in the log")
    ax.set_ylabel("million samples per second")
    ax.set_ylim(0, None)
    ax.legend(frameon=False, fontsize=8)
    ax.set_title("Throughput", fontsize=10)
    for ax in axes:
        ax.spines[["top", "right"]].set_visible(False)
        ax.grid(alpha=0.25)
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)
