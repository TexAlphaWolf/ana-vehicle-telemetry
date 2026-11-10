"""A synthetic drive log with a known truth.

Real logs come with no answer key, so the project makes its own: a vehicle drives trips built from a speed profile (a chain of
ramps and holds), a simple physical model turns speed and acceleration into rpm, throttle, engine load, fuel flow and coolant
temperature, a sensor adds noise and quantisation, and faults are injected at known times. The truth records what the analysis
should find: the distance and fuel of every trip, every harsh ramp, and every injected fault.

The numbers (mass, drag, gear ratios, fuel per kWh) are those of an ordinary petrol hatchback and are illustrative, not the
data of a real vehicle.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

import numpy as np

from vehicletelemetry.logio import Array, Log, make_log

# --- the vehicle (illustrative) -------------------------------------------------------------------------------------------
MASS_KG = 1400.0
CRR = 0.012
CDA = 0.65  # drag coefficient times frontal area, m^2
AIR = 1.2
WHEEL_M = 0.31
GEARS = np.array([13.0, 7.4, 5.1, 3.9, 3.1, 2.6])  # total ratio, engine turns per wheel turn
UPSHIFT_KMH = np.array([18.0, 35.0, 55.0, 80.0, 105.0])
IDLE_RPM = 800.0
IDLE_LPH = 0.8
EFFICIENCY = 0.28
KWH_PER_L = 8.9
PMAX_KW = 70.0
FUEL_CUT_LPH = 0.25
T_TARGET = 90.0
TAU_WARM_S = 240.0
TAU_COOL_S = 1800.0

START_DEFAULT = datetime(2026, 3, 2, 7, 12, 0)  # a Monday


def physics(v_kmh: Array, a_ms2: Array) -> tuple[Array, Array, Array, Array]:
    """rpm, throttle %, engine load % and fuel flow L/h for a speed and an acceleration."""
    v = v_kmh / 3.6
    gear = np.searchsorted(UPSHIFT_KMH, v_kmh, side="right")
    wheel_rpm = v * 60.0 / (2.0 * np.pi * WHEEL_M)
    rpm = np.maximum(IDLE_RPM, wheel_rpm * GEARS[gear])
    force = MASS_KG * a_ms2 + CRR * MASS_KG * 9.81 + 0.5 * AIR * CDA * v * v
    power_kw = np.maximum(force * v / 1000.0, 0.0)
    load = np.clip(15.0 + 85.0 * power_kw / PMAX_KW, 0.0, 100.0)
    throttle = np.clip(100.0 * power_kw / PMAX_KW, 0.0, 100.0) * 0.9 + 2.0
    fuel = np.maximum(IDLE_LPH, power_kw / (EFFICIENCY * KWH_PER_L))
    cut = (a_ms2 < -0.2) & (v_kmh > 20.0)
    fuel = np.where(cut, FUEL_CUT_LPH, fuel)
    return rpm, throttle, load, fuel


# --- speed profiles -------------------------------------------------------------------------------------------------------
@dataclass
class Profile:
    """Knots of a piecewise-linear speed (km/h), the harsh ramps in it, and the time the driving ends."""

    t: list[float] = field(default_factory=lambda: [0.0])
    v: list[float] = field(default_factory=lambda: [0.0])
    harsh: list[tuple[str, float, float, float]] = field(default_factory=list)  # kind, t0, t1, ms2
    drive_end: float = 0.0  # when the driving, including the last stop, ends
    idle_tail: float = 0.0  # engine running while parked, after the driving
    arrive: float = 0.0  # when the vehicle came to its last stop

    @property
    def trip_end(self) -> float:
        """The end of the trip as the analysis defines it: arrival when the vehicle then sits long enough to be parked, else the
        moment the engine is switched off."""
        return self.arrive if self.idle_tail > 0 else self.drive_end

    def hold(self, seconds: float) -> None:
        self.t.append(self.t[-1] + seconds)
        self.v.append(self.v[-1])

    def ramp(self, v1: float, a: float, kind: str | None = None) -> None:
        dur = abs(v1 - self.v[-1]) / 3.6 / a
        if kind is not None:
            self.harsh.append((kind, self.t[-1], self.t[-1] + dur, a))
        self.t.append(self.t[-1] + dur)
        self.v.append(v1)


def _speed_change(p: Profile, v1: float, rng: np.random.Generator, harsh_p: float, firm_p: float) -> None:
    """Move to speed v1 with an ordinary, a firm (below the threshold) or a harsh ramp, whichever suits the change."""
    dv = abs(v1 - p.v[-1])
    if dv < 1.0:
        return
    up = v1 > p.v[-1]
    dv_ms = dv / 3.6
    harsh_lo, harsh_hi = (3.0, 3.6) if up else (3.8, 4.6)
    harsh_hi = min(harsh_hi, dv_ms / 3.2)  # at least 3.2 s long: two full one-second intervals fit inside
    r = rng.random()
    if r < harsh_p and harsh_hi > harsh_lo:
        p.ramp(v1, float(rng.uniform(harsh_lo, harsh_hi)), "harsh_accel" if up else "harsh_brake")
    elif r < harsh_p + firm_p:
        p.ramp(v1, float(rng.uniform(1.9, 2.3) if up else rng.uniform(2.4, 2.8)))
    else:
        p.ramp(v1, float(rng.uniform(0.8, 1.6) if up else rng.uniform(0.8, 1.8)))


def _urban(p: Profile, seconds: float, rng: np.random.Generator, harsh_p: float, firm_p: float) -> None:
    end = p.t[-1] + seconds
    while p.t[-1] < end:
        target = float(rng.uniform(25, 55))
        _speed_change(p, target, rng, harsh_p, firm_p)
        p.hold(float(rng.uniform(8, 40)))
        if rng.random() < 0.55:
            _speed_change(p, 0.0, rng, harsh_p, firm_p)
            p.hold(float(rng.uniform(5, 45)))  # a red light
        else:
            _speed_change(p, float(rng.uniform(12, target - 8)), rng, harsh_p, firm_p)


def _highway(p: Profile, seconds: float, rng: np.random.Generator, harsh_p: float, firm_p: float) -> None:
    cruise = float(rng.uniform(95, 125))
    _speed_change(p, cruise, rng, harsh_p * 0.5, firm_p)
    end = p.t[-1] + seconds
    while p.t[-1] < end:
        p.hold(float(rng.uniform(60, 240)))
        cruise = float(np.clip(cruise + rng.uniform(-14, 14), 85, 130))
        p.ramp(cruise, float(rng.uniform(0.3, 0.7)))
    _speed_change(p, float(rng.uniform(25, 45)), rng, harsh_p, firm_p)


def build_profile(kind: str, rng: np.random.Generator, harsh_p: float, firm_p: float, idle_tail_p: float) -> Profile:
    p = Profile()
    p.hold(float(rng.uniform(15, 60)))  # engine on, standing
    if kind == "commute":
        _urban(p, float(rng.uniform(360, 720)), rng, harsh_p, firm_p)
        _highway(p, float(rng.uniform(480, 1200)), rng, harsh_p, firm_p)
        _urban(p, float(rng.uniform(240, 600)), rng, harsh_p, firm_p)
    elif kind == "leisure":
        _urban(p, float(rng.uniform(180, 420)), rng, harsh_p, firm_p)
        _highway(p, float(rng.uniform(1200, 3300)), rng, harsh_p, firm_p)
        _urban(p, float(rng.uniform(180, 420)), rng, harsh_p, firm_p)
    else:
        _urban(p, float(rng.uniform(300, 720)), rng, harsh_p, firm_p)
    _speed_change(p, 0.0, rng, harsh_p, firm_p)
    p.hold(float(rng.uniform(8, 20)))
    p.drive_end = p.t[-1]
    m = len(p.v) - 1
    while m > 0 and p.v[m - 1] == 0.0:
        m -= 1
    p.arrive = p.t[m]
    if rng.random() < idle_tail_p:  # parked with the engine still running
        p.idle_tail = float(rng.uniform(660, 900))
        p.hold(p.idle_tail)
    return p


# --- truth ----------------------------------------------------------------------------------------------------------------
@dataclass
class Truth:
    trips: list[dict[str, Any]] = field(default_factory=list)
    harsh: list[dict[str, Any]] = field(default_factory=list)
    anomalies: dict[str, list[dict[str, Any]]] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {"kind": "truth", "trips": self.trips, "harsh": self.harsh, "anomalies": self.anomalies}

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Truth:
        if not isinstance(d, dict) or d.get("kind") != "truth":
            raise ValueError("not a truth file")
        return cls(d["trips"], d["harsh"], d["anomalies"])


@dataclass(frozen=True)
class GenParams:
    days: int = 14
    seed: int = 1
    start: datetime = START_DEFAULT
    harsh_p: float = 0.08  # share of speed changes done harshly, where the change is big enough
    firm_p: float = 0.12  # share done firmly (just below the thresholds)
    idle_tail_p: float = 0.3
    jitter_s: float = 0.12
    anomaly_rate: float = 1.0  # multiplies the rates of injected faults; 0 for a clean log
    speed_noise_kmh: float = 0.25


def _plan(g: GenParams, rng: np.random.Generator) -> list[tuple[str, float, float]]:
    """(kind, start in seconds since the first day's midnight, ambient temperature) of every trip."""
    plan = []
    for d in range(g.days):
        wd = (g.start.weekday() + d) % 7
        amb = float(rng.uniform(4, 22))
        day = d * 86400.0
        if wd < 5:
            plan.append(("commute", day + float(rng.uniform(6.5, 8.5)) * 3600, amb))
            if rng.random() < 0.3:
                plan.append(("errand", day + float(rng.uniform(12, 14)) * 3600, amb))
            plan.append(("commute", day + float(rng.uniform(17, 19)) * 3600, amb))
        else:
            if rng.random() < 0.7:
                plan.append(("leisure", day + float(rng.uniform(9, 16)) * 3600, amb))
            if rng.random() < 0.5:
                plan.append(("errand", day + float(rng.uniform(9, 19)) * 3600, amb))
    plan = [(k, round(st, 3), amb) for k, st, amb in plan]  # whole milliseconds, like the timestamps in the file
    plan.sort(key=lambda x: x[1])
    return plan


def generate(g: GenParams | None = None) -> tuple[Log, Truth]:
    g = g or GenParams()
    rng = np.random.default_rng(g.seed)
    plan = _plan(g, rng)
    if not plan:
        raise ValueError("no trips: use more days")
    day0 = datetime(g.start.year, g.start.month, g.start.day)
    base = plan[0][1]
    parts: dict[str, list[Array]] = {k: [] for k in ("t", "speed", "rpm", "throttle", "load", "coolant", "fuel")}
    truth = Truth()
    sessions: list[tuple[int, int, int]] = []  # first sample, last sample, first sample after the driving
    n_done = 0
    temp_prev, end_prev = 0.0, -1e9
    for kind, planned, amb in plan:
        start = max(
            planned, end_prev + 1800.0
        )  # trips never overlap: the engine is off for at least half an hour in between
        prof = build_profile(kind, rng, g.harsh_p, g.firm_p, g.idle_tail_p)
        kt, kv = np.array(prof.t), np.array(prof.v)
        phase = float(rng.uniform(0, 2 * np.pi))

        def speed_fn(t: Array, kt: Array = kt, kv: Array = kv, phase: float = phase) -> Array:
            v = np.interp(t, kt, kv)
            ripple = 0.8 * np.sin(2 * np.pi * t / 37.0 + phase) * np.minimum(1.0, v / 20.0)
            return np.maximum(v + ripple, 0.0)

        def accel_fn(t: Array, speed_fn: Callable[[Array], Array] = speed_fn) -> Array:
            h = 0.05
            return (speed_fn(t + h) - speed_fn(t - h)) / (2 * h) / 3.6

        total = prof.t[-1]
        jitter = np.round(rng.uniform(-g.jitter_s, g.jitter_s, int(total) + 2), 3)
        ts = np.round(np.arange(int(total) + 1, dtype=np.float64) + jitter[: int(total) + 1], 3)
        ts[0] = 0.0
        ts = ts[ts <= total]
        v_true = speed_fn(ts)
        a_true = accel_fn(ts)
        rpm, thr, load, fuel = physics(v_true, a_true)
        warm_from = amb + (temp_prev - amb) * np.exp(-(start - end_prev) / TAU_COOL_S) if end_prev > -1e8 else amb
        t_start = float(warm_from)
        coolant = T_TARGET - (T_TARGET - t_start) * np.exp(-ts / TAU_WARM_S)

        # the truth of this trip: a fine grid, so the answer does not depend on the sampling
        fine = np.arange(0.0, prof.trip_end + 1e-9, 0.1)
        fv, fa = speed_fn(fine), accel_fn(fine)
        _, _, _, ffuel = physics(fv, fa)
        dist_m = float(np.sum((fv[:-1] + fv[1:]) / 2 / 3.6 * 0.1))
        fuel_l = float(np.sum((ffuel[:-1] + ffuel[1:]) / 2 * 0.1 / 3600.0))
        off = start - base
        truth.trips.append(
            {
                "kind": kind,
                "start_s": off,
                "end_s": off + prof.trip_end,
                "distance_km": dist_m / 1000.0,
                "fuel_l": fuel_l,
                "l_per_100km": fuel_l / (dist_m / 1000.0) * 100.0,
            }
        )
        for hk, h0, h1, ha in prof.harsh:
            truth.harsh.append({"kind": hk, "t0": off + h0, "t1": off + h1, "ms2": ha})
        temp_prev = float(T_TARGET - (T_TARGET - t_start) * np.exp(-prof.drive_end / TAU_WARM_S))
        end_prev = start + total

        noise = rng.normal
        parts["t"].append(ts + off)
        parts["speed"].append(v_true + noise(0, g.speed_noise_kmh, ts.size))
        parts["rpm"].append(rpm + noise(0, 9.0, ts.size))
        parts["throttle"].append(thr + noise(0, 0.6, ts.size))
        parts["load"].append(load + noise(0, 0.8, ts.size))
        parts["coolant"].append(coolant + noise(0, 0.15, ts.size))
        parts["fuel"].append(fuel + noise(0, 0.05, ts.size))
        i_end = n_done + int(np.searchsorted(ts, prof.drive_end, side="right"))
        sessions.append((n_done, n_done + ts.size - 1, i_end))
        n_done += ts.size

    t = np.round(np.concatenate(parts["t"]), 3)
    cols = {c: np.concatenate(parts[c]) for c in ("speed", "rpm", "throttle", "load", "coolant", "fuel")}
    for c, hi in (("throttle", 100.0), ("load", 100.0), ("rpm", 8000.0), ("fuel", 100.0)):
        cols[c] = np.clip(cols[c], 0.0, hi)  # a sensor does not report more than its range
    truth.anomalies = _inject(cols, t, sessions, rng, g.anomaly_rate)
    for c, dp in (("speed", 1), ("rpm", 0), ("throttle", 1), ("load", 1), ("coolant", 1), ("fuel", 2)):
        # the values injected as faults are written exactly as they are; the others are rounded like a sensor does
        mask = np.ones(t.size, dtype=bool)
        for rec in truth.anomalies["out_of_range"]:
            if rec["channel"] == c:
                mask[rec["i"]] = False
        cols[c][mask] = np.round(cols[c][mask], dp)
    cols["speed"] = np.maximum(cols["speed"], 0.0)
    _restore_faults(cols, truth, t)
    for recs in truth.anomalies.values():
        for rec in recs:
            rec.pop("i", None)
            rec.pop("j", None)
    return make_log(day0 + timedelta(seconds=base), t, **cols), truth


# --- faults ---------------------------------------------------------------------------------------------------------------
OOR_CODES = {"speed": 255.0, "rpm": 16383.75, "coolant": -40.0}  # what OBD adapters report for a failed sensor


def _inject(
    cols: dict[str, Array],
    t: np.ndarray[Any, Any],
    sessions: list[tuple[int, int, int]],
    rng: np.random.Generator,
    rate: float,
) -> dict[str, list[dict[str, Any]]]:
    out: dict[str, list[dict[str, Any]]] = {k: [] for k in ("dropout", "spike", "out_of_range", "overheat", "flatline")}
    if rate <= 0:
        return out
    n = t.size
    sess_of = np.empty(n, dtype=np.int64)
    for k, (i0, i1, _) in enumerate(sessions):
        sess_of[i0 : i1 + 1] = k
    busy = np.zeros(n, dtype=bool)

    def pick(width: int, tries: int = 60) -> int | None:
        for _ in range(tries):
            i = int(rng.integers(4, n - width - 4))
            if sess_of[i - 3] == sess_of[i + width + 3] and not busy[i - 3 : i + width + 4].any():
                busy[i - 3 : i + width + 4] = True
                return i
        return None

    # overheating and stuck sensors: a few trips each
    for k, (i0, i1, ie) in enumerate(sessions):
        if ie - i0 < 900:
            continue
        if rng.random() < 0.10 * rate:
            ws = float(t[i0] + rng.uniform(300, (t[ie - 1] - t[i0]) - 300))
            dur = float(rng.uniform(70, 120))
            we = ws + dur
            peak = float(rng.uniform(113, 119))
            sl = slice(i0, i1 + 1)
            ramp = np.clip(np.minimum((t[sl] - ws) / 15.0, (we - t[sl]) / 15.0), 0.0, 1.0)
            cols["coolant"][sl] = (
                cols["coolant"][sl] * (1.0 - ramp) + peak * ramp
            )  # the engine runs hot, whatever it was doing
            out["overheat"].append({"t0": ws, "t1": we, "peak_c": peak})
        if rng.random() < 0.10 * rate:
            ch = str(rng.choice(["rpm", "load"]))
            ws = float(t[i0] + rng.uniform(300, (t[ie - 1] - t[i0]) - 300))
            dur = float(rng.uniform(40, 90))
            idx = np.flatnonzero((t >= ws) & (t <= ws + dur) & (sess_of == k))
            if idx.size:
                out["flatline"].append(
                    {"channel": ch, "t0": float(t[idx[0]]), "t1": float(t[idx[-1]]), "i": idx, "ch": ch}
                )
    # rounding happens after this, so remember the value to hold: set it on the rounded data in _restore_faults
    for rec in out["flatline"]:
        rec["value"] = float(np.round(cols[rec["ch"]][rec["i"][0]], 0 if rec["ch"] == "rpm" else 1))

    def count(per_10k: float) -> int:
        return int(rng.poisson(per_10k * rate * n / 10_000))

    for _ in range(count(3.0)):  # short dropouts, the kind that gets interpolated
        dur = float(rng.uniform(2, 8))
        i = int(rng.integers(4, n - 40))
        j = int(np.searchsorted(t, t[i] + dur))
        if sess_of[i - 3] == sess_of[min(j + 3, n - 1)] and not busy[i - 3 : j + 4].any():
            busy[i - 3 : j + 4] = True
            out["dropout"].append({"t0": float(t[i]), "t1": float(t[j - 1]), "i": i, "j": j, "long": False})
    for _ in range(count(0.6)):  # long ones, which stay holes
        dur = float(rng.uniform(12, 25))
        i = int(rng.integers(4, n - 60))
        j = int(np.searchsorted(t, t[i] + dur))
        if sess_of[i - 3] == sess_of[min(j + 3, n - 1)] and not busy[i - 3 : j + 4].any():
            busy[i - 3 : j + 4] = True
            out["dropout"].append({"t0": float(t[i]), "t1": float(t[j - 1]), "i": i, "j": j, "long": True})
    for _ in range(count(2.0)):
        at = pick(1)
        if at is not None and cols["speed"][at] > 20:
            delta = float(rng.uniform(50, 90))
            if cols["speed"][at] + delta < 240:
                out["spike"].append({"t": float(t[at]), "i": at, "delta_kmh": delta})
    for _ in range(count(2.0)):
        ch = str(rng.choice(list(OOR_CODES)))
        at = pick(1)
        if at is not None:
            out["out_of_range"].append({"channel": ch, "t": float(t[at]), "value": OOR_CODES[ch], "i": at})
    return out


def _restore_faults(cols: dict[str, Array], truth: Truth, t: Array) -> None:
    """Write the injected faults into the rounded data."""
    a = truth.anomalies
    for rec in a["flatline"]:
        cols[rec["channel"]][rec["i"]] = rec["value"]
    for rec in a["dropout"]:
        for c in cols:
            cols[c][rec["i"] : rec["j"]] = np.nan
    for rec in a["spike"]:
        cols["speed"][rec["i"]] = np.round(cols["speed"][rec["i"]] + rec["delta_kmh"], 1)
    for rec in a["out_of_range"]:
        cols[rec["channel"]][rec["i"]] = rec["value"]
    for rec in a["flatline"]:
        rec.pop("i", None)
        rec.pop("ch", None)
