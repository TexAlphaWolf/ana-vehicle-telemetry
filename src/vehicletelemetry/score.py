"""Compare an analysis with the truth of a synthetic log: what was found, what was missed, and how far off the numbers are."""

from __future__ import annotations

import statistics
from typing import Any

from vehicletelemetry.generate import Truth

Interval = tuple[float, float]


def missed(truth: list[Interval], found: list[Interval], slack: float = 0.0) -> list[Interval]:
    """The true intervals no found interval answers; every found interval answers at most one true one."""
    used = [False] * len(found)
    lost = []
    ordered = sorted(found)
    for t0, t1 in sorted(truth):
        for k, (f0, f1) in enumerate(ordered):
            if not used[k] and f1 >= t0 - slack and f0 <= t1 + slack:
                used[k] = True
                break
        else:
            lost.append((t0, t1))
    return lost


def match(truth: list[Interval], found: list[Interval], slack: float = 0.0) -> tuple[int, int, int]:
    """True positives, false positives and false negatives."""
    fn = len(missed(truth, found, slack))
    tp = len(truth) - fn
    return tp, len(found) - tp, fn


def _rate(tp: int, fp: int, fn: int) -> dict[str, Any]:
    return {
        "true": tp + fn,
        "found": tp + fp,
        "tp": tp,
        "fp": fp,
        "fn": fn,
        "precision": tp / (tp + fp) if tp + fp else None,
        "recall": tp / (tp + fn) if tp + fn else None,
    }


def _overlap(a: Interval, b: Interval) -> float:
    return max(0.0, min(a[1], b[1]) - max(a[0], b[0]))


def score(analysis: dict[str, Any], truth: Truth) -> dict[str, Any]:
    trips = analysis["trips"]
    # trips: each true trip is answered by the found trip that covers most of it
    rows = []
    taken: set[int] = set()
    for k, tt in enumerate(truth.trips):
        span = (tt["start_s"], tt["end_s"])
        best, best_ov = None, 0.0
        for f in trips:
            ov = _overlap(span, (f["start_s"], f["end_s"]))
            if f["index"] not in taken and ov > best_ov:
                best, best_ov = f, ov
        if best is None or best_ov < 0.5 * (span[1] - span[0]):
            continue
        taken.add(best["index"])
        rows.append(
            {
                "true_trip": k,
                "found_trip": best["index"],
                "distance_true_km": tt["distance_km"],
                "distance_found_km": best["distance_km"],
                "distance_error": best["distance_km"] / tt["distance_km"] - 1.0,
                "consumption_true": tt["l_per_100km"],
                "consumption_found": best["l_per_100km"],
                "consumption_error": best["l_per_100km"] / tt["l_per_100km"] - 1.0
                if best["l_per_100km"] is not None
                else None,
                "duration_error_s": best["duration_s"] - (span[1] - span[0]),
                "covered_share": best["covered_share"],
            }
        )
    d_err = [abs(r["distance_error"]) for r in rows]
    c_err = [abs(r["consumption_error"]) for r in rows if r["consumption_error"] is not None]
    dur = [abs(r["duration_error_s"]) for r in rows]
    true_km = sum(r["distance_true_km"] for r in rows)
    found_km = sum(r["distance_found_km"] for r in rows)
    out: dict[str, Any] = {
        "kind": "accuracy",
        "trips": {
            "true": len(truth.trips),
            "found": len(trips),
            "matched": len(rows),
            "extra": len(trips) - len(rows),
            "distance_total_error": found_km / true_km - 1.0 if true_km else None,
            "distance_error_median": statistics.median(d_err) if d_err else None,
            "distance_error_max": max(d_err) if d_err else None,
            "consumption_error_median": statistics.median(c_err) if c_err else None,
            "consumption_error_max": max(c_err) if c_err else None,
            "duration_error_median_s": statistics.median(dur) if dur else None,
            "duration_error_max_s": max(dur) if dur else None,
            "per_trip": rows,
        },
        "events": {},
    }
    ev = analysis["events"]
    for kind in ("harsh_accel", "harsh_brake"):
        tr = [(h["t0"], h["t1"]) for h in truth.harsh if h["kind"] == kind]
        fo = [(e["t0"], e["t1"]) for e in ev[kind]]
        out["events"][kind] = _rate(*match(tr, fo, 1.5))
        holes = [(r["t0"], r["t1"]) for r in truth.anomalies["dropout"]]
        # a harsh ramp inside a hole of the data cannot be seen: say how many of the misses are of that kind
        out["events"][kind]["missed_in_hole"] = sum(
            1 for m in missed(tr, fo, 1.5) if any(h1 >= m[0] and h0 <= m[1] for h0, h1 in holes)
        )
    an = truth.anomalies
    out["events"]["spike"] = _rate(
        *match([(r["t"], r["t"]) for r in an["spike"]], [(x, x) for x in analysis["anomalies"]["spikes"]], 0.5)
    )
    tp = fp = fn = 0
    for ch in ("speed", "rpm", "coolant"):
        a, b, c = match(
            [(r["t"], r["t"]) for r in an["out_of_range"] if r["channel"] == ch],
            [(r["t"], r["t"]) for r in analysis["anomalies"]["out_of_range"] if r["channel"] == ch],
            0.5,
        )
        tp, fp, fn = tp + a, fp + b, fn + c
    out["events"]["out_of_range"] = _rate(tp, fp, fn)
    out["events"]["dropout"] = _rate(
        *match(
            [(r["t0"], r["t1"]) for r in an["dropout"]],
            [(d["t0"], d["t1"]) for d in analysis["anomalies"]["dropouts"]],
            0.5,
        )
    )
    out["events"]["overheat"] = _rate(
        *match([(r["t0"], r["t1"]) for r in an["overheat"]], [(e["t0"], e["t1"]) for e in ev["overheat"]])
    )
    tp = fp = fn = 0
    for ch in ("rpm", "load"):
        a, b, c = match(
            [(r["t0"], r["t1"]) for r in an["flatline"] if r["channel"] == ch],
            [(e["t0"], e["t1"]) for e in ev["flatline"] if e["channel"] == ch],
        )
        tp, fp, fn = tp + a, fp + b, fn + c
    out["events"]["flatline"] = _rate(tp, fp, fn)
    # the holes that were interpolated, and the ones that were not, among the injected dropouts
    long_true = [r for r in an["dropout"] if r["long"]]
    out["dropouts"] = {
        "short": len(an["dropout"]) - len(long_true),
        "long": len(long_true),
        "filled_found": sum(1 for d in analysis["anomalies"]["dropouts"] if d["filled"]),
        "left_found": sum(1 for d in analysis["anomalies"]["dropouts"] if not d["filled"]),
    }
    return out
