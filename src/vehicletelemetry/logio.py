"""Drive logs: one CSV row per sample, one column per OBD-II channel.

Columns (header names are case-insensitive; a few common aliases are accepted)::

    time,speed_kmh,rpm,throttle_pct,load_pct,coolant_c,fuel_lph

``time`` is an ISO 8601 timestamp or a number of seconds since the epoch and must increase from row to row. Only ``time`` and
``speed_kmh`` are required. An empty cell, ``nan``, ``na`` or ``null`` is a missing sample. Fuel can also be given as a mass air
flow column ``maf_gs`` (grams per second); it is turned into litres per hour with the air-fuel ratio and fuel density.
"""

from __future__ import annotations

import csv
import math
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

import numpy as np
from numpy.typing import NDArray

from vehicletelemetry.params import CHANNELS

Array = NDArray[np.float64]

HEADER = ["time", "speed_kmh", "rpm", "throttle_pct", "load_pct", "coolant_c", "fuel_lph"]
COLUMN_OF = dict(zip(CHANNELS, HEADER[1:], strict=True))
ALIASES = {
    "timestamp": "time",
    "speed": "speed_kmh",
    "vehicle_speed": "speed_kmh",
    "engine_rpm": "rpm",
    "throttle": "throttle_pct",
    "engine_load": "load_pct",
    "coolant": "coolant_c",
    "coolant_temp": "coolant_c",
    "fuel_rate_lph": "fuel_lph",
    "maf": "maf_gs",
}
MISSING = {"", "nan", "na", "n/a", "null", "none", "-"}


class LogError(ValueError):
    """The log file cannot be read."""


@dataclass(frozen=True)
class Log:
    """The samples of a log: times in seconds since ``t0``, strictly increasing; a missing value is NaN."""

    t0: datetime
    t: Array
    speed: Array  # km/h
    rpm: Array
    throttle: Array  # %
    load: Array  # %
    coolant: Array  # degrees C
    fuel: Array  # L/h

    def __len__(self) -> int:
        return int(self.t.size)

    def channel(self, name: str) -> Array:
        return getattr(self, name)  # type: ignore[no-any-return]

    def present(self) -> dict[str, bool]:
        return {c: bool(np.isfinite(self.channel(c)).any()) for c in CHANNELS}

    def head(self, n: int) -> Log:
        return Log(self.t0, *(self.channel(c)[:n] for c in ("t", *CHANNELS)))


def make_log(t0: datetime, t: Array, **channels: Array) -> Log:
    """A log with the channels given by name; the others are all missing."""
    nan = np.full(t.size, np.nan)
    return Log(t0, t, *(channels.get(c, nan) for c in CHANNELS))


def clock(t0: datetime, t: float) -> str:
    """The wall-clock time of a sample, as written in the files (milliseconds)."""
    return (t0 + timedelta(seconds=float(t))).isoformat(timespec="milliseconds").replace(".000", "")


def _number(text: str, column: str, line: int) -> float:
    s = text.strip()
    if s.lower() in MISSING:
        return math.nan
    try:
        v = float(s)
    except ValueError:
        raise LogError(f"line {line}: cannot read {text!r} as a number in column {column}") from None
    return v if math.isfinite(v) else math.nan


def _time(text: str, line: int) -> tuple[datetime, float]:
    """The instant as (naive UTC datetime, seconds since the epoch of that instant when it was given as a number)."""
    s = text.strip()
    try:
        secs = float(s)
    except ValueError:
        try:
            d = datetime.fromisoformat(s)
        except ValueError:
            raise LogError(
                f"line {line}: cannot read {text!r} as a time (ISO 8601 or seconds since the epoch)"
            ) from None
        if d.tzinfo is not None:
            d = d.astimezone(UTC).replace(tzinfo=None)
        return d, math.nan
    if not math.isfinite(secs):
        raise LogError(f"line {line}: cannot read {text!r} as a time")
    try:
        return datetime.fromtimestamp(secs, UTC).replace(tzinfo=None), secs
    except (OverflowError, OSError, ValueError):
        raise LogError(f"line {line}: time {text!r} is out of range") from None


def parse_csv(lines: Iterable[str], afr: float = 14.7, density_g_l: float = 745.0) -> Log:
    reader = csv.reader(lines)
    try:
        header = next(reader)
    except StopIteration:
        raise LogError("the file is empty") from None
    names = []
    for h in header:
        key = h.strip().lower()
        names.append(ALIASES.get(key, key))
    if "time" not in names or "speed_kmh" not in names:
        raise LogError(f"the header needs at least time and speed_kmh, got: {', '.join(header)}")
    if len(set(names)) != len(names):
        raise LogError("the header repeats a column")
    col = {n: i for i, n in enumerate(names)}
    width = len(names)
    wanted = [(c, COLUMN_OF[c], col[COLUMN_OF[c]]) for c in CHANNELS if COLUMN_OF[c] in col]
    maf = col.get("maf_gs")

    times: list[float] = []
    values: dict[str, list[float]] = {c: [] for c in CHANNELS}
    maf_values: list[float] = []
    first: datetime | None = None
    first_secs = math.nan
    prev = -math.inf
    for row in reader:
        line = reader.line_num
        if not row or all(not x.strip() for x in row):
            continue
        if len(row) != width:
            raise LogError(f"line {line}: {len(row)} fields, the header has {width}")
        d, secs = _time(row[col["time"]], line)
        if first is None:
            first, first_secs = d, secs
        t = secs - first_secs if not math.isnan(secs) and not math.isnan(first_secs) else (d - first).total_seconds()
        if t <= prev:
            raise LogError(f"line {line}: time {row[col['time']].strip()!r} does not come after the previous row")
        prev = t
        times.append(t)
        for c, name, i in wanted:
            values[c].append(_number(row[i], name, line))
        if maf is not None:
            maf_values.append(_number(row[maf], "maf_gs", line))
    if len(times) < 2 or first is None:
        raise LogError("the log needs at least two rows")
    arr = {c: np.asarray(v, dtype=np.float64) for c, v in values.items() if v}
    if "fuel" not in arr and maf is not None:
        arr["fuel"] = np.asarray(maf_values, dtype=np.float64) * 3600.0 / (afr * density_g_l)
    return make_log(first, np.asarray(times, dtype=np.float64), **arr)


def read_csv(path: str | Path, afr: float = 14.7, density_g_l: float = 745.0) -> Log:
    try:
        with open(path, encoding="utf-8-sig", newline="") as f:
            return parse_csv(f, afr, density_g_l)
    except OSError as exc:
        raise LogError(f"cannot read {path}: {exc}") from exc
    except UnicodeDecodeError as exc:
        raise LogError(f"{path} is not a UTF-8 text file") from exc


def _cell(x: float) -> str:
    return "" if math.isnan(x) else repr(float(x))


def to_csv(log: Log) -> str:
    """The log as CSV text. Numbers are written with ``repr``, so reading the text back gives the same floats."""
    rows = [",".join(HEADER)]
    cols = [log.channel(c).tolist() for c in CHANNELS]
    for i, t in enumerate(log.t.tolist()):
        rows.append(",".join([clock(log.t0, t), *(_cell(c[i]) for c in cols)]))
    return "\n".join(rows) + "\n"


def write_csv(log: Log, path: str | Path) -> None:
    Path(path).write_text(to_csv(log), encoding="utf-8", newline="")
