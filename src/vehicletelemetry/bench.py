"""How fast the analysis is, and that it still agrees with the literal implementation."""

from __future__ import annotations

import io
import os
import platform
import statistics
import time
from collections.abc import Callable
from functools import partial
from typing import Any

import numpy as np

from vehicletelemetry import __version__, logio, pipeline, reference, score, verify
from vehicletelemetry.generate import GenParams, generate
from vehicletelemetry.logio import Log
from vehicletelemetry.params import Params

SAMPLES_PER_DAY = 3750  # about, for the synthetic days


def timed(fn: Callable[[], object], repeat: int) -> float:
    runs = []
    for _ in range(repeat):
        t0 = time.perf_counter()
        fn()
        runs.append(time.perf_counter() - t0)
    return statistics.median(runs)


def log_of(samples: int, seed: int) -> Log:
    days = max(2, int(np.ceil(samples / SAMPLES_PER_DAY * 1.3)))
    log, _ = generate(GenParams(days=days, seed=seed))
    if len(log) < samples:  # unlucky weekend-heavy draw: one more try with more days
        log, _ = generate(GenParams(days=days * 2, seed=seed))
    return log.head(samples)


def sweep(seeds: int, days: int) -> dict[str, Any]:
    """Generate logs with seeds 1..seeds, analyse them and add up how the analysis did against each one's truth."""
    kinds = ("harsh_accel", "harsh_brake", "spike", "out_of_range", "dropout", "overheat", "flatline")
    ev: dict[str, dict[str, Any]] = {k: {"tp": 0, "fp": 0, "fn": 0, "missed_in_hole": 0} for k in kinds}
    trips = {"true": 0, "found": 0, "matched": 0}
    dist: list[float] = []
    cons: list[float] = []
    dur: list[float] = []
    km = 0.0
    for seed in range(1, seeds + 1):
        log, truth = generate(GenParams(days=days, seed=seed))
        sc = score.score(pipeline.analyze(log), truth)
        for k in trips:
            trips[k] += sc["trips"][k]
        for k in kinds:
            for f in ("tp", "fp", "fn"):
                ev[k][f] += sc["events"][k][f]
            ev[k]["missed_in_hole"] += sc["events"][k].get("missed_in_hole", 0)
        for r in sc["trips"]["per_trip"]:
            dist.append(abs(r["distance_error"]))
            dur.append(abs(r["duration_error_s"]))
            if r["consumption_error"] is not None:
                cons.append(abs(r["consumption_error"]))
            km += r["distance_true_km"]
    for r in ev.values():
        tp, fp, fn = r["tp"], r["fp"], r["fn"]
        r["true"], r["found"] = tp + fn, tp + fp
        r["precision"] = tp / (tp + fp) if tp + fp else None
        r["recall"] = tp / (tp + fn) if tp + fn else None
    return {
        "seeds": seeds,
        "days": days,
        "trips": trips,
        "true_km": km,
        "distance_error_median": statistics.median(dist),
        "distance_error_p95": float(np.percentile(dist, 95)),
        "consumption_error_median": statistics.median(cons),
        "consumption_error_p95": float(np.percentile(cons, 95)),
        "duration_error_median_s": statistics.median(dur),
        "duration_error_p95_s": float(np.percentile(dur, 95)),
        "events": ev,
    }


def run_bench(
    sizes: list[int],
    repeat: int,
    seed: int,
    draws: int,
    command: str,
    ref_samples: int = 20_000,
    seeds: int = 20,
    progress: Callable[[str], None] = lambda _m: None,
) -> dict[str, Any]:
    t0 = time.perf_counter()
    p = Params()
    progress("generate a log with its truth")
    gen_s = timed(lambda: generate(GenParams(days=14, seed=seed)), repeat)
    log14, _ = generate(GenParams(days=14, seed=seed))
    progress("write and parse the CSV text")
    text = logio.to_csv(log14)
    write_s = timed(lambda: logio.to_csv(log14), repeat)
    parse_s = timed(lambda: logio.parse_csv(io.StringIO(text)), repeat)
    rows = []
    for n in sizes:
        progress(f"analysis of {n:,} samples")
        log = log_of(n, seed)
        rows.append({"samples": len(log), "seconds": timed(partial(pipeline.analyze, log, p), repeat)})
        del log
    progress(f"literal implementation on {ref_samples:,} samples")
    ref_log = log_of(ref_samples, seed)
    ref_s = timed(partial(reference.analyze, ref_log, p), max(1, repeat // 2))
    progress(f"agreement with the literal implementation on {draws} random logs")
    checks = verify.verify(draws, seed)
    progress(f"accuracy against the truth of {seeds} synthetic logs of 14 days")
    accuracy = sweep(seeds, 14)
    return {
        "kind": "bench",
        "environment": {
            "vehicletelemetry": __version__,
            "python": platform.python_version(),
            "numpy": np.__version__,
            "system": f"{platform.system()} {platform.machine()}",
            "cpus": os.cpu_count(),
            "seed": seed,
            "repeat": repeat,
            "command": command,
            "seconds": round(time.perf_counter() - t0, 1),
        },
        "analysis": rows,
        "reference": {"samples": len(ref_log), "seconds": ref_s},
        "generate": {"samples": len(log14), "seconds": gen_s},
        "write": {"samples": len(log14), "seconds": write_s},
        "parse": {"samples": len(log14), "seconds": parse_s},
        "accuracy": accuracy,
        "verification": {
            "checks": len(checks),
            "numbers": sum(c.numbers for c in checks),
            "ok": all(c.ok for c in checks),
            "max_rel_error": max(c.max_rel_error for c in checks),
            "tolerance": verify.RTOL,
        },
    }
