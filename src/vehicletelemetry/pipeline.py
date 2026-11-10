"""The analysis, vectorised with NumPy.

Order of the steps (``reference.py`` does the same, sample by sample, in plain Python, and ``verify.py`` compares the two):

1. **Range.** A value outside the physical range of its channel is a sensor fault and becomes missing.
2. **Spikes.** A speed sample that jumps up and back down by more than ``phys_ms2`` on both sides becomes missing.
3. **Fill.** A hole of at most ``max_fill_s`` seconds (from the last good sample before it to the first one after) is
   interpolated linearly in time.
4. **Intervals.** Between two samples at most ``gap_s`` apart there is an interval. It is *valid* when the speed is known at both
   ends. It is *stopped* when both speeds are below ``stop_kmh``.
5. **Parking.** A run of stopped intervals lasting ``park_s`` or more is parking. Two runs of stopped intervals with only intervals
   of unknown speed between them, for at most ``bridge_s``, count as one run.
6. **Trips.** A trip is a run of intervals that are neither parking nor a gap, trimmed to its first and last valid interval, and
   at least ``min_trip_m`` long.
7. **Metrics** of every trip, **harsh events** inside trips, and the **overheating** and **stuck sensor** events of the log.
"""

from __future__ import annotations

from typing import Any

import numpy as np
from numpy.typing import NDArray

from vehicletelemetry.logio import Array, Log, clock
from vehicletelemetry.params import CHANNELS, RANGES, Params

Bool = NDArray[np.bool_]
Idx = NDArray[np.intp]


def runs(mask: Bool) -> tuple[Idx, Idx]:
    """First and last index (both included) of every run of True."""
    d = np.diff(np.concatenate(([False], mask, [False])).astype(np.int8))
    return np.flatnonzero(d == 1), np.flatnonzero(d == -1) - 1


def fill(t: Array, x: Array, max_fill_s: float) -> Array:
    """Linear interpolation over the holes that are at most ``max_fill_s`` long (measured between the good samples around)."""
    finite = np.isfinite(x)
    if finite.all() or not finite.any():
        return x.copy()
    n = x.size
    pos = np.arange(n)
    prev = np.maximum.accumulate(np.where(finite, pos, -1))
    nxt = np.minimum.accumulate(np.where(finite, pos, n)[::-1])[::-1]
    hole = ~finite & (prev >= 0) & (nxt < n)
    span = t[np.minimum(nxt, n - 1)] - t[np.maximum(prev, 0)]
    use = hole & (span <= max_fill_s)
    out = x.copy()
    out[use] = np.interp(t[use], t[finite], x[finite])
    return out


def clean(log: Log, p: Params) -> tuple[dict[str, Array], dict[str, Any]]:
    """The channels after steps 1-3 (speed still in km/h) and what was found on the way."""
    t = log.t
    n = t.size
    data = {c: log.channel(c).copy() for c in CHANNELS}
    found: dict[str, Any] = {"out_of_range": [], "oor_counts": {}, "spikes": [], "dropouts": []}
    raw_missing = ~np.isfinite(data["speed"])
    s, e = runs(raw_missing)
    found["dropout_runs"] = list(zip(s.tolist(), e.tolist(), strict=True))

    for c in CHANNELS:
        lo, hi = RANGES[c]
        x = data[c]
        bad = np.isfinite(x) & ((x < lo) | (x > hi))
        for i in np.flatnonzero(bad).tolist():
            found["out_of_range"].append({"channel": c, "t": float(t[i]), "value": float(x[i])})
        found["oor_counts"][c] = int(bad.sum())
        x[bad] = np.nan

    if n >= 3:
        v = data["speed"] / 3.6
        dt = np.diff(t)
        covered = dt <= p.gap_s
        ok = np.isfinite(v[:-2]) & np.isfinite(v[1:-1]) & np.isfinite(v[2:]) & covered[:-1] & covered[1:]
        a1 = (v[1:-1] - v[:-2]) / dt[:-1]
        a2 = (v[2:] - v[1:-1]) / dt[1:]
        spike = ok & (np.abs(a1) > p.phys_ms2) & (np.abs(a2) > p.phys_ms2) & (a1 * a2 < 0)
        idx = np.flatnonzero(spike) + 1
        found["spikes"] = [float(t[i]) for i in idx.tolist()]
        data["speed"][idx] = np.nan

    before = {c: int(np.isfinite(data[c]).sum()) for c in CHANNELS}
    for c in CHANNELS:
        data[c] = fill(t, data[c], p.max_fill_s)
    found["filled"] = {c: int(np.isfinite(data[c]).sum()) - before[c] for c in CHANNELS}
    found["missing_after"] = {c: int((~np.isfinite(data[c])).sum()) for c in CHANNELS}
    found["dropouts"] = [
        {
            "t0": float(t[a]),
            "t1": float(t[b]),
            "samples": b - a + 1,
            "filled": bool(np.isfinite(data["speed"][a : b + 1]).all()),
        }
        for a, b in found["dropout_runs"]
    ]
    return data, found


def analyze(log: Log, p: Params | None = None) -> dict[str, Any]:
    p = p or Params()
    with np.errstate(all="ignore"):
        return _analyze(log, p)


def _analyze(log: Log, p: Params) -> dict[str, Any]:
    t = log.t
    n = t.size
    data, found = clean(log, p)
    v = data["speed"] / 3.6
    rpm, coolant, fuel = data["rpm"], data["coolant"], data["fuel"]
    dt = np.diff(t)
    covered = dt <= p.gap_s
    fin = np.isfinite(v)
    valid = covered & fin[:-1] & fin[1:]
    vs = p.stop_kmh / 3.6
    stopped = valid & (v[:-1] < vs) & (v[1:] < vs)

    park = np.zeros(n - 1, dtype=bool)
    unknown = covered & ~valid
    stops: list[tuple[int, int]] = []
    for a, b in zip(*runs(stopped), strict=True):
        if stops and unknown[stops[-1][1] + 1 : a].all() and t[a] - t[stops[-1][1] + 1] <= p.bridge_s:
            stops[-1] = (stops[-1][0], int(b))  # a short hole of unknown speed between two stops: still the same stop
        else:
            stops.append((int(a), int(b)))
    for a, b in stops:
        if t[b + 1] - t[a] >= p.park_s:
            park[a : b + 1] = True

    dist_k = np.where(valid, (v[:-1] + v[1:]) / 2 * dt, 0.0)
    acc = np.where(valid, (v[1:] - v[:-1]) / dt, np.nan)
    ff = np.isfinite(fuel)
    joint = valid & ff[:-1] & ff[1:]
    fuel_k = np.where(joint, (fuel[:-1] + fuel[1:]) / 2 * dt / 3600.0, 0.0)
    high = covered & (rpm[:-1] >= p.rpm_high) & (rpm[1:] >= p.rpm_high)

    trips: list[dict[str, Any]] = []
    in_trip = np.zeros(n - 1, dtype=bool)
    spans: list[tuple[int, int]] = []
    dropped = 0
    for a, b in zip(*runs(covered & ~park), strict=True):
        vi = np.flatnonzero(valid[a : b + 1])
        if vi.size == 0:
            continue
        ka, kb = a + int(vi[0]), a + int(vi[-1])
        sl = slice(ka, kb + 1)
        dist = float(dist_k[sl].sum())
        if dist < p.min_trip_m:
            dropped += 1
            continue
        in_trip[sl] = True
        spans.append((ka, kb))
        d, ok, st = dt[sl], valid[sl], stopped[sl]
        valid_s = float(d[ok].sum())
        stopped_s = float(d[st].sum())
        j = joint[sl]
        fuel_l = float(fuel_k[sl].sum()) if j.any() else None
        fdist = float(dist_k[sl][j].sum())
        speeds = v[ka : kb + 2]
        temps = coolant[ka : kb + 2]
        fin_t = np.isfinite(temps)
        trips.append(
            {
                "index": len(trips),
                "start": clock(log.t0, t[ka]),
                "end": clock(log.t0, t[kb + 1]),
                "start_s": float(t[ka]),
                "end_s": float(t[kb + 1]),
                "duration_s": float(t[kb + 1] - t[ka]),
                "valid_s": valid_s,
                "covered_share": valid_s / float(t[kb + 1] - t[ka]),
                "distance_km": dist / 1000.0,
                "moving_s": valid_s - stopped_s,
                "idle_s": stopped_s,
                "idle_share": stopped_s / valid_s,
                "avg_speed_kmh": dist / 1000.0 / (valid_s / 3600.0),
                "max_speed_kmh": float(np.nanmax(speeds) * 3.6),
                "fuel_l": fuel_l,
                "fuel_distance_km": fdist / 1000.0 if fuel_l is not None else None,
                "fuel_share": float(d[j].sum()) / valid_s if fuel_l is not None else None,
                "l_per_100km": fuel_l / (fdist / 1000.0) * 100.0 if fuel_l is not None and fdist > 0 else None,
                "high_rpm_s": float(d[high[sl]].sum()),
                "max_coolant_c": float(np.max(temps[fin_t])) if fin_t.any() else None,
                "harsh_accel": 0,
                "harsh_brake": 0,
            }
        )

    starts = np.array([s for s, _ in spans], dtype=np.intp)
    events: dict[str, list[dict[str, Any]]] = {"harsh_accel": [], "harsh_brake": []}
    for kind, mask in (("harsh_accel", acc >= p.accel_ms2), ("harsh_brake", acc <= -p.brake_ms2)):
        for a, b in zip(*runs(mask & valid & in_trip), strict=True):
            dur = float(t[b + 1] - t[a])
            if dur < p.min_event_s:
                continue
            k = int(np.searchsorted(starts, a, side="right")) - 1
            seg = acc[a : b + 1]
            events[kind].append(
                {
                    "trip": k,
                    "t0": float(t[a]),
                    "t1": float(t[b + 1]),
                    "start": clock(log.t0, t[a]),
                    "duration_s": dur,
                    "peak_ms2": float(seg.max() if kind == "harsh_accel" else -seg.min()),
                }
            )
            trips[k][kind] += 1

    hot = covered & (coolant[:-1] > p.coolant_max_c) & (coolant[1:] > p.coolant_max_c)
    overheat = []
    for a, b in zip(*runs(hot), strict=True):
        dur = float(t[b + 1] - t[a])
        if dur >= p.overheat_s:
            overheat.append(
                {
                    "t0": float(t[a]),
                    "t1": float(t[b + 1]),
                    "start": clock(log.t0, t[a]),
                    "duration_s": dur,
                    "peak_c": float(np.max(coolant[a : b + 2])),
                }
            )
    flat = []
    for c in ("rpm", "load"):
        x = data[c]
        same = covered & np.isfinite(x[:-1]) & np.isfinite(x[1:]) & (x[:-1] == x[1:])
        for a, b in zip(*runs(same), strict=True):
            dur = float(t[b + 1] - t[a])
            if dur >= p.flat_s:
                flat.append(
                    {
                        "channel": c,
                        "t0": float(t[a]),
                        "t1": float(t[b + 1]),
                        "start": clock(log.t0, t[a]),
                        "duration_s": dur,
                        "value": float(x[a]),
                    }
                )

    return assemble(log, p, found, trips, events, overheat, flat, dropped, dt, covered)


def assemble(
    log: Log,
    p: Params,
    found: dict[str, Any],
    trips: list[dict[str, Any]],
    events: dict[str, list[dict[str, Any]]],
    overheat: list[dict[str, Any]],
    flat: list[dict[str, Any]],
    dropped: int,
    dt: Array,
    covered: Bool,
) -> dict[str, Any]:
    """The result, in the shape both implementations return (the totals are the only part computed here, from the trips)."""
    t = log.t
    dist = sum(x["distance_km"] for x in trips)
    fuel_trips = [x for x in trips if x["fuel_l"] is not None]
    fuel = sum(x["fuel_l"] for x in fuel_trips)
    fdist = sum(x["fuel_distance_km"] for x in fuel_trips)
    valid_s = sum(x["valid_s"] for x in trips)
    idle_s = sum(x["idle_s"] for x in trips)
    ha, hb = len(events["harsh_accel"]), len(events["harsh_brake"])
    return {
        "kind": "analysis",
        "params": p.as_dict(),
        "log": {
            "samples": int(t.size),
            "start": clock(log.t0, t[0]),
            "end": clock(log.t0, t[-1]),
            "recorded_s": float(dt[covered].sum()),
            "median_dt_s": float(np.median(dt)),
            "channels": log.present(),
        },
        "quality": {
            "sessions": int((~covered).sum()) + 1,
            "longest_gap_s": float(np.max(dt)),
            "out_of_range": found["oor_counts"],
            "spikes": len(found["spikes"]),
            "dropout_runs": len(found["dropouts"]),
            "filled": found["filled"],
            "missing_after": found["missing_after"],
            "short_trips_dropped": dropped,
        },
        "trips": trips,
        "totals": {
            "trips": len(trips),
            "distance_km": dist,
            "valid_h": valid_s / 3600.0,
            "idle_share": idle_s / valid_s if valid_s > 0 else None,
            "fuel_l": fuel if fuel_trips else None,
            "l_per_100km": fuel / fdist * 100.0 if fuel_trips and fdist > 0 else None,
            "harsh_accel": ha,
            "harsh_brake": hb,
            "harsh_accel_per_100km": ha / dist * 100.0 if dist > 0 else None,
            "harsh_brake_per_100km": hb / dist * 100.0 if dist > 0 else None,
            "overheat_events": len(overheat),
            "flatline_events": len(flat),
        },
        "events": {
            "harsh_accel": events["harsh_accel"],
            "harsh_brake": events["harsh_brake"],
            "overheat": overheat,
            "flatline": flat,
        },
        "anomalies": {"spikes": found["spikes"], "out_of_range": found["out_of_range"], "dropouts": found["dropouts"]},
    }
