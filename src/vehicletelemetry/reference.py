"""The same analysis as ``pipeline.py``, written as plainly as possible: one sample at a time, in pure Python.

Nothing here is vectorised and nothing is shared with the NumPy code except the definitions in the module docstring of
``pipeline`` and the ``assemble`` function that builds the totals from the trips. It is slow on purpose: it is the answer key the
fast code is checked against.
"""

from __future__ import annotations

import math
import statistics
from typing import Any

import numpy as np

from vehicletelemetry.logio import Log, clock
from vehicletelemetry.params import CHANNELS, RANGES, Params
from vehicletelemetry.pipeline import assemble

NAN = math.nan


def _finite(x: float) -> bool:
    return not math.isnan(x)


def _runs(flags: list[bool]) -> list[tuple[int, int]]:
    out = []
    start = -1
    for i, f in enumerate(flags):
        if f and start < 0:
            start = i
        if not f and start >= 0:
            out.append((start, i - 1))
            start = -1
    if start >= 0:
        out.append((start, len(flags) - 1))
    return out


def _fill(t: list[float], x: list[float], max_fill_s: float) -> list[float]:
    out = list(x)
    n = len(x)
    i = 0
    while i < n:
        if _finite(x[i]):
            i += 1
            continue
        j = i
        while j < n and not _finite(x[j]):
            j += 1
        # the hole is i..j-1; the good samples around it are i-1 and j
        if i > 0 and j < n and t[j] - t[i - 1] <= max_fill_s:
            slope = (x[j] - x[i - 1]) / (t[j] - t[i - 1])
            for k in range(i, j):
                out[k] = slope * (t[k] - t[i - 1]) + x[i - 1]
        i = j
    return out


def analyze(log: Log, p: Params | None = None) -> dict[str, Any]:
    p = p or Params()
    t = log.t.tolist()
    n = len(t)
    data = {c: log.channel(c).tolist() for c in CHANNELS}
    found: dict[str, Any] = {"out_of_range": [], "oor_counts": {}, "spikes": []}

    raw_runs = _runs([not _finite(x) for x in data["speed"]])

    # 1. range
    for c in CHANNELS:
        lo, hi = RANGES[c]
        count = 0
        for i in range(n):
            x = data[c][i]
            if _finite(x) and (x < lo or x > hi):
                found["out_of_range"].append({"channel": c, "t": t[i], "value": x})
                data[c][i] = NAN
                count += 1
        found["oor_counts"][c] = count

    # 2. spikes, all found on the data as it is now
    v = [x / 3.6 for x in data["speed"]]
    spikes = []
    for i in range(1, n - 1):
        d0, d1 = t[i] - t[i - 1], t[i + 1] - t[i]
        if not (_finite(v[i - 1]) and _finite(v[i]) and _finite(v[i + 1])) or d0 > p.gap_s or d1 > p.gap_s:
            continue
        a1 = (v[i] - v[i - 1]) / d0
        a2 = (v[i + 1] - v[i]) / d1
        if abs(a1) > p.phys_ms2 and abs(a2) > p.phys_ms2 and a1 * a2 < 0:
            spikes.append(i)
    for i in spikes:
        data["speed"][i] = NAN
        found["spikes"].append(t[i])

    # 3. fill
    before = {c: sum(1 for x in data[c] if _finite(x)) for c in CHANNELS}
    for c in CHANNELS:
        data[c] = _fill(t, data[c], p.max_fill_s)
    found["filled"] = {c: sum(1 for x in data[c] if _finite(x)) - before[c] for c in CHANNELS}
    found["missing_after"] = {c: sum(1 for x in data[c] if not _finite(x)) for c in CHANNELS}
    found["dropouts"] = [
        {
            "t0": t[a],
            "t1": t[b],
            "samples": b - a + 1,
            "filled": all(_finite(data["speed"][k]) for k in range(a, b + 1)),
        }
        for a, b in raw_runs
    ]

    # 4. intervals
    v = [x / 3.6 for x in data["speed"]]
    rpm, coolant, fuel = data["rpm"], data["coolant"], data["fuel"]
    vs = p.stop_kmh / 3.6
    dt = [t[k + 1] - t[k] for k in range(n - 1)]
    covered = [d <= p.gap_s for d in dt]
    valid = [covered[k] and _finite(v[k]) and _finite(v[k + 1]) for k in range(n - 1)]
    stopped = [valid[k] and v[k] < vs and v[k + 1] < vs for k in range(n - 1)]

    # 5. parking
    park = [False] * (n - 1)
    i = 0
    while i < n - 1:
        if not stopped[i]:
            i += 1
            continue
        a = b = i
        while True:
            while b + 1 < n - 1 and stopped[b + 1]:
                b += 1
            j = b + 1  # look past the stop: a hole of unknown speed, then another stop?
            while j < n - 1 and covered[j] and not valid[j]:
                j += 1
            if j > b + 1 and j < n - 1 and stopped[j] and t[j] - t[b + 1] <= p.bridge_s:
                b = j
                continue
            break
        if t[b + 1] - t[a] >= p.park_s:
            for k in range(a, b + 1):
                park[k] = True
        i = b + 1

    # 6. trips and their metrics
    trips: list[dict[str, Any]] = []
    spans: list[tuple[int, int]] = []
    dropped = 0
    for a, b in _runs([covered[k] and not park[k] for k in range(n - 1)]):
        good = [k for k in range(a, b + 1) if valid[k]]
        if not good:
            continue
        ka, kb = good[0], good[-1]
        dist = 0.0
        valid_s = stopped_s = fuel_s = high_s = 0.0
        fuel_l = 0.0
        fdist = 0.0
        any_fuel = False
        for k in range(ka, kb + 1):
            if valid[k]:
                seg = (v[k] + v[k + 1]) / 2 * dt[k]
                dist += seg
                valid_s += dt[k]
                if stopped[k]:
                    stopped_s += dt[k]
                if _finite(fuel[k]) and _finite(fuel[k + 1]):
                    any_fuel = True
                    fuel_l += (fuel[k] + fuel[k + 1]) / 2 * dt[k] / 3600.0
                    fdist += seg
                    fuel_s += dt[k]
            if covered[k] and rpm[k] >= p.rpm_high and rpm[k + 1] >= p.rpm_high:
                high_s += dt[k]
        if dist < p.min_trip_m:
            dropped += 1
            continue
        spans.append((ka, kb))
        speeds = [x for x in v[ka : kb + 2] if _finite(x)]
        temps = [x for x in coolant[ka : kb + 2] if _finite(x)]
        trips.append(
            {
                "index": len(trips),
                "start": clock(log.t0, t[ka]),
                "end": clock(log.t0, t[kb + 1]),
                "start_s": t[ka],
                "end_s": t[kb + 1],
                "duration_s": t[kb + 1] - t[ka],
                "valid_s": valid_s,
                "covered_share": valid_s / (t[kb + 1] - t[ka]),
                "distance_km": dist / 1000.0,
                "moving_s": valid_s - stopped_s,
                "idle_s": stopped_s,
                "idle_share": stopped_s / valid_s,
                "avg_speed_kmh": dist / 1000.0 / (valid_s / 3600.0),
                "max_speed_kmh": max(speeds) * 3.6,
                "fuel_l": fuel_l if any_fuel else None,
                "fuel_distance_km": fdist / 1000.0 if any_fuel else None,
                "fuel_share": fuel_s / valid_s if any_fuel else None,
                "l_per_100km": fuel_l / (fdist / 1000.0) * 100.0 if any_fuel and fdist > 0 else None,
                "high_rpm_s": high_s,
                "max_coolant_c": max(temps) if temps else None,
                "harsh_accel": 0,
                "harsh_brake": 0,
            }
        )

    # 7. harsh events inside trips
    events: dict[str, list[dict[str, Any]]] = {"harsh_accel": [], "harsh_brake": []}
    for kind, sign in (("harsh_accel", 1.0), ("harsh_brake", -1.0)):
        limit = p.accel_ms2 if sign > 0 else p.brake_ms2
        for idx, (ka, kb) in enumerate(spans):
            flags = []
            accs = []
            for k in range(ka, kb + 1):
                if valid[k]:
                    a_k = (v[k + 1] - v[k]) / dt[k]
                    accs.append(a_k)
                    flags.append(a_k >= limit if sign > 0 else a_k <= -limit)
                else:
                    accs.append(NAN)
                    flags.append(False)
            for a, b in _runs(flags):
                dur = t[ka + b + 1] - t[ka + a]
                if dur < p.min_event_s:
                    continue
                seg = accs[a : b + 1]
                events[kind].append(
                    {
                        "trip": idx,
                        "t0": t[ka + a],
                        "t1": t[ka + b + 1],
                        "start": clock(log.t0, t[ka + a]),
                        "duration_s": dur,
                        "peak_ms2": max(seg) if sign > 0 else -min(seg),
                    }
                )
                trips[idx][kind] += 1

    # overheating and stuck sensors
    overheat = []
    hot = [covered[k] and coolant[k] > p.coolant_max_c and coolant[k + 1] > p.coolant_max_c for k in range(n - 1)]
    for a, b in _runs(hot):
        dur = t[b + 1] - t[a]
        if dur >= p.overheat_s:
            overheat.append(
                {
                    "t0": t[a],
                    "t1": t[b + 1],
                    "start": clock(log.t0, t[a]),
                    "duration_s": dur,
                    "peak_c": max(coolant[a : b + 2]),
                }
            )
    flat = []
    for c in ("rpm", "load"):
        x = data[c]
        same = [covered[k] and _finite(x[k]) and _finite(x[k + 1]) and x[k] == x[k + 1] for k in range(n - 1)]
        for a, b in _runs(same):
            dur = t[b + 1] - t[a]
            if dur >= p.flat_s:
                flat.append(
                    {
                        "channel": c,
                        "t0": t[a],
                        "t1": t[b + 1],
                        "start": clock(log.t0, t[a]),
                        "duration_s": dur,
                        "value": x[a],
                    }
                )

    # the result; the log block needs the median of the intervals, computed here in plain Python
    out = assemble(log, p, found, trips, events, overheat, flat, dropped, np.asarray(dt), np.asarray(covered))
    out["log"]["median_dt_s"] = statistics.median(dt)
    out["log"]["recorded_s"] = sum(d for d, c in zip(dt, covered, strict=True) if c)
    out["quality"]["longest_gap_s"] = max(dt)
    out["quality"]["sessions"] = covered.count(False) + 1
    return out
