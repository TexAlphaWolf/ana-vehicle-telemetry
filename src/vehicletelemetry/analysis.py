"""A report: the analysis of a log, the comparison with the truth when there is one, and a trace to draw."""

from __future__ import annotations

from typing import Any

import numpy as np

from vehicletelemetry import pipeline, score
from vehicletelemetry.generate import Truth
from vehicletelemetry.logio import Log
from vehicletelemetry.params import Params

TRACE_POINTS = 600


def showcase(log: Log, p: Params, analysis: dict[str, Any]) -> dict[str, Any] | None:
    """The trip with the most harsh events (the longest on a tie), as a speed trace to draw."""
    trips = analysis["trips"]
    if not trips:
        return None
    best = max(trips, key=lambda x: (x["harsh_accel"] + x["harsh_brake"], x["duration_s"]))
    data, _ = pipeline.clean(log, p)
    m = (log.t >= best["start_s"]) & (log.t <= best["end_s"])
    t, v = log.t[m] - best["start_s"], data["speed"][m]
    step = max(1, int(np.ceil(t.size / TRACE_POINTS)))
    keep = np.isfinite(v[::step])
    return {
        "trip": best["index"],
        "t_s": [round(float(x), 1) for x in t[::step][keep]],
        "speed_kmh": [round(float(x), 1) for x in v[::step][keep]],
    }


def build_report(log: Log, p: Params | None = None, truth: Truth | None = None, source: str = "demo") -> dict[str, Any]:
    p = p or Params()
    analysis = pipeline.analyze(log, p)
    return {
        "kind": "report",
        "source": source,
        "analysis": analysis,
        "accuracy": score.score(analysis, truth) if truth is not None else None,
        "showcase": showcase(log, p, analysis),
    }
