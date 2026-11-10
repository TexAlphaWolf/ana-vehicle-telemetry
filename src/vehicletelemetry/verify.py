"""Check the NumPy analysis against the literal one, on generated logs and on logs made hostile on purpose."""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

import numpy as np

from vehicletelemetry import pipeline, reference
from vehicletelemetry.generate import GenParams, generate
from vehicletelemetry.logio import Log, make_log
from vehicletelemetry.params import CHANNELS, RANGES, Params

RTOL = 1e-9


@dataclass(frozen=True)
class Check:
    name: str
    ok: bool
    numbers: int  # how many numbers (and strings) were compared
    max_rel_error: float
    detail: str


def compare(a: Any, b: Any, path: str = "") -> tuple[int, float, str | None]:
    """(values compared, largest relative difference, the first mismatch or None); floats within RTOL, everything else equal."""
    if isinstance(a, dict) and isinstance(b, dict):
        if a.keys() != b.keys():
            return 0, math.inf, f"{path}: keys differ: {sorted(a.keys() ^ b.keys())}"
        total, worst, bad = 0, 0.0, None
        for k in a:
            n, w, m = compare(a[k], b[k], f"{path}/{k}")
            total, worst, bad = total + n, max(worst, w), bad or m
        return total, worst, bad
    if isinstance(a, list) and isinstance(b, list):
        if len(a) != len(b):
            return 0, math.inf, f"{path}: {len(a)} items against {len(b)}"
        total, worst, bad = 0, 0.0, None
        for i, (x, y) in enumerate(zip(a, b, strict=True)):
            n, w, m = compare(x, y, f"{path}[{i}]")
            total, worst, bad = total + n, max(worst, w), bad or m
        return total, worst, bad
    if isinstance(a, float) and isinstance(b, float):
        if math.isnan(a) and math.isnan(b):
            return 1, 0.0, None
        rel = abs(a - b) / max(abs(a), abs(b), 1e-12)
        if math.isclose(a, b, rel_tol=RTOL, abs_tol=1e-12):
            return 1, rel if abs(a - b) > 1e-12 else 0.0, None
        return 1, rel, f"{path}: {a!r} against {b!r}"
    if type(a) is not type(b) or a != b:
        return 1, math.inf, f"{path}: {a!r} against {b!r}"
    return 1, 0.0, None


def random_params(rng: np.random.Generator) -> Params:
    gap = float(rng.uniform(10, 120))
    return Params(
        gap_s=gap,
        max_fill_s=float(rng.uniform(1, min(gap, 20))),
        stop_kmh=float(rng.uniform(0.5, 3)),
        park_s=float(rng.uniform(30, 900)),
        bridge_s=float(rng.uniform(1, 90)),
        min_trip_m=float(rng.uniform(0.5, 1000)),
        accel_ms2=float(rng.uniform(1.5, 4)),
        brake_ms2=float(rng.uniform(1.5, 5)),
        min_event_s=float(rng.uniform(0.5, 3)),
        phys_ms2=float(rng.uniform(6, 20)),
        rpm_high=float(rng.uniform(2500, 5000)),
        coolant_max_c=float(rng.uniform(95, 115)),
        overheat_s=float(rng.uniform(3, 40)),
        flat_s=float(rng.uniform(3, 50)),
    )


def hostile(log: Log, rng: np.random.Generator) -> Log:
    """The same drive with its timing and values spoiled: irregular and missing samples, faults, stuck values, a short tail."""
    n = len(log)
    n = int(rng.integers(max(50, n // 5), n + 1))
    cols = {c: log.channel(c)[:n].copy() for c in CHANNELS}
    t = log.t[:n].copy()
    if rng.random() < 0.5:  # irregular sampling: 0.05 s to 3 s, now and then a long silence
        dt = rng.choice([0.05, 0.2, 0.5, 1.0, 1.0, 1.0, 2.0, 3.0], n - 1)
        dt[rng.random(n - 1) < 0.003] = float(rng.uniform(40, 400))
        t = np.concatenate(([0.0], np.cumsum(dt)))
    for _ in range(int(rng.integers(0, 12))):  # holes, in some channels or in all of them
        i = int(rng.integers(0, n - 1))
        j = min(n, i + int(rng.integers(1, 40)))
        for c in CHANNELS:
            if rng.random() < 0.6:
                cols[c][i:j] = np.nan
    for _ in range(int(rng.integers(0, 10))):
        c = CHANNELS[int(rng.integers(0, len(CHANNELS)))]
        lo, hi = RANGES[c]
        cols[c][int(rng.integers(0, n))] = float(rng.choice([lo - 1.0, hi + 1.0, 1e9, -1e9]))
    for _ in range(int(rng.integers(0, 10))):  # a single wild value in range
        i = int(rng.integers(1, n - 1))
        cols["speed"][i] = float(rng.uniform(0, 240))
    for _ in range(int(rng.integers(0, 5))):  # a stuck channel
        c = str(rng.choice(["rpm", "load", "coolant"]))
        i = int(rng.integers(0, n - 1))
        j = min(n, i + int(rng.integers(5, 120)))
        cols[c][i:j] = cols[c][i]
    return make_log(log.t0 + timedelta(seconds=float(rng.integers(0, 10_000_000))), t, **cols)


def verify(draws: int = 25, seed: int = 1) -> list[Check]:
    rng = np.random.default_rng(seed)
    cases: list[tuple[str, Log, Params]] = []
    log, _ = generate(GenParams(days=3, seed=seed))
    cases.append(("generated log, default parameters", log, Params()))
    for k in range(draws):
        base, _ = generate(
            GenParams(
                days=int(rng.integers(1, 3)),
                seed=int(rng.integers(0, 10**6)),
                anomaly_rate=float(rng.choice([0, 1, 3])),
            )
        )
        spoiled = hostile(base, rng) if k % 4 != 3 else base
        cases.append(
            (f"random case {k + 1}" + (" (spoiled)" if spoiled is not base else ""), spoiled, random_params(rng))
        )
    out = []
    for name, lg, p in cases:
        a, b = pipeline.analyze(lg, p), reference.analyze(lg, p)
        n, worst, bad = compare(a, b)
        out.append(Check(name, bad is None, n, worst, bad or f"{len(lg):,} samples, {a['totals']['trips']} trips"))
    return out
