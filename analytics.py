"""Deterministic statistical analysis shared by the dashboard and PDF report."""
from __future__ import annotations

import csv
import hashlib
import io
import os
from datetime import date, datetime, timezone
from typing import Literal

os.environ.setdefault('OPENBLAS_NUM_THREADS', '1')
os.environ.setdefault('OMP_NUM_THREADS', '1')
import numpy as np
from pydantic import BaseModel, ConfigDict, Field
from scipy.stats import t
from investigation import enrich

METHODS = {"iqr": "IQR rule", "zscore": "Z-score", "moving": "Moving average", "grubbs": "Grubbs"}


class Settings(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    iqr_factor: float = Field(default=1.5, ge=0.1, le=10)
    z_threshold: float = Field(default=3, ge=0.5, le=10)
    moving_window: int = Field(default=14, ge=3, le=90)
    moving_percent: float = Field(default=40, ge=1, le=500)
    grubbs_alpha: float = Field(default=0.05, ge=0.001, le=0.2)
    grubbs_iterations: int = Field(default=1, ge=1, le=20)
    methods: list[Literal["iqr", "zscore", "moving", "grubbs"]] = Field(default_factory=lambda: list(METHODS), min_length=1, max_length=4)
    chart_type: Literal["line", "bar", "stacked"] = "line"
    trend_degree: int = Field(default=1, ge=1, le=4)


def parse_csv(text: str):
    rows = list(csv.reader(io.StringIO(text.lstrip('\ufeff'))))
    if not rows:
        raise ValueError("The Data sheet is empty.")
    headers = [v.strip() for v in rows[0]]
    if not headers or headers[0].lower() != 'date':
        raise ValueError("Data!A1 must be Date. Select the Data tab in your generator.")
    columns = [(i, v) for i, v in enumerate(headers[1:], 1) if v and v.lower() != 'total']
    names = [v for _, v in columns]
    if not 1 <= len(names) <= 12 or len(set(names)) != len(names):
        raise ValueError("Use 1..12 active mines with distinct, nonempty names.")
    dates, values = [], []
    for number, row in enumerate(rows[1:], 2):
        if not row or not row[0].strip():
            continue
        try:
            day = date.fromisoformat(row[0].strip()).isoformat()
            output = [float(row[i]) for i, _ in columns]
        except (ValueError, IndexError):
            raise ValueError(f"Invalid date or numerical output at Data row {number}; check the sheet for formula errors.") from None
        if not np.isfinite(output).all() or min(output) < 0 or max(output)>1e12:
            raise ValueError(f"Data row {number} contains negative, nonfinite, or implausibly large output (maximum 1e12 tonnes/day).")
        dates.append(day)
        values.append(output)
    if not 3 <= len(dates) <= 730:
        raise ValueError("The generator must provide 3..730 daily observations.")
    if len(set(dates)) != len(dates) or dates != sorted(dates):
        raise ValueError("Dates must be distinct and in ascending order.")
    if any((date.fromisoformat(b) - date.fromisoformat(a)).days != 1 for a, b in zip(dates, dates[1:])):
        raise ValueError("Daily observations must be continuous; missing days are not silently filled.")
    canonical = '\n'.join([','.join(names)] + [str((d, row)) for d, row in zip(dates, values)])
    return {"dates": dates, "mines": names, "values": values,
            "snapshot": hashlib.sha256(canonical.encode()).hexdigest()[:16],
            "fetched_at": datetime.now(timezone.utc).isoformat(timespec='seconds')}


def grubbs(values, alpha=0.05, iterations=1, trace=None):
    """Two-sided Grubbs: sample SD, Student-t upper alpha/(2*n), one point per pass.

    Repeated removal is explicitly exploratory; it is not generalized ESD and does
    not provide a family-wise alpha guarantee. Single-pass is the default.
    """
    remaining = list(range(len(values)))
    found = {}
    for step in range(iterations):
        n = len(remaining)
        if n < 3:
            break
        sample = np.asarray(values)[remaining]
        sd = float(np.std(sample, ddof=1))
        if sd < 1e-12:
            if trace is not None:
                trace.append({'pass': step + 1, 'n': n, 'candidate_index': None})
            break
        scores = np.abs(sample - np.mean(sample)) / sd
        pos = int(np.argmax(scores))
        critical_t = float(t.isf(alpha / (2 * n), n - 2))
        critical = (n - 1) / np.sqrt(n) * np.sqrt(critical_t ** 2 / (n - 2 + critical_t ** 2))
        if trace is not None:
            trace.append({'pass': step + 1, 'n': n, 'candidate_index': remaining[pos],
                          'score': float(scores[pos]), 'critical': float(critical),
                          'rejected': bool(scores[pos] > critical)})
        if scores[pos] <= critical:
            break
        found[remaining.pop(pos)] = {"score": float(scores[pos]), "critical": float(critical), "pass": step + 1}
    return found


def analyze_series(name, values, dates, settings: Settings):
    y = np.asarray(values, dtype=float)
    n = len(y)
    mean, sd = float(y.mean()), float(y.std(ddof=1))
    q1, median, q3 = (float(v) for v in np.quantile(y, [.25, .5, .75], method='linear'))
    iqr = q3 - q1
    lower, upper = q1 - settings.iqr_factor * iqr, q3 + settings.iqr_factor * iqr
    xs = np.linspace(-1, 1, n)
    degree = min(settings.trend_degree, n - 1)
    # Polynomial.fit scales its domain, avoiding the ill-conditioned date-index basis.
    fit = np.polynomial.Polynomial.fit(xs, y, degree)
    trend = fit(xs).tolist()
    moving = [None] * n
    percent = [None] * n
    zscores = (np.abs(y - mean) / sd).tolist() if sd > 1e-12 else [0.] * n
    passes = []
    g = grubbs(y, settings.grubbs_alpha, settings.grubbs_iterations, trace=passes)
    flags = {key: [] for key in METHODS}
    anomalies = []
    for index, value in enumerate(y):
        if index >= settings.moving_window:
            baseline = float(y[index-settings.moving_window:index].mean())
            moving[index] = baseline
            percent[index] = float(abs(value - baseline) / abs(baseline) * 100) if abs(baseline) > 1e-12 else (0. if value == 0 else None)
        hits = []
        tests = {"iqr": bool(value < lower or value > upper), "zscore": zscores[index] > settings.z_threshold,
                 "moving": moving[index] is not None and (percent[index] is not None and percent[index] > settings.moving_percent or moving[index] == 0 and value > 0),
                 "grubbs": index in g}
        for method, match in tests.items():
            if match:
                flags[method].append(index)
                if method in settings.methods:
                    hits.append(method)
        if hits:
            baseline = moving[index] if moving[index] is not None else mean
            anomalies.append({"mine": name, "date": dates[index], "index": index, "value": round(float(value), 2),
                              "direction": "Spike" if value >= baseline else "Drop", "baseline": round(baseline, 2),
                              "tests": hits, "z_score": round(zscores[index], 5),
                              "moving_percent": round(percent[index], 3) if percent[index] is not None else None,
                              "grubbs": g.get(index)})
    episodes = []
    for anomaly in anomalies:
        if episodes and episodes[-1]['direction'] == anomaly['direction'] and episodes[-1]['points'][-1]['index'] + 1 == anomaly['index']:
            episodes[-1]['points'].append(anomaly)
        else:
            episodes.append({"mine": name, "direction": anomaly['direction'], "points": [anomaly]})
    return {"name": name, "values": y.tolist(), "trend": trend, "moving_average": moving,
            "stats": {"mean": mean, "std": sd, "median": median, "q1": q1, "q3": q3, "iqr": iqr,
                      "minimum": float(y.min()), "maximum": float(y.max()), "total": float(y.sum())},
            "bounds": {"iqr_lower": lower, "iqr_upper": upper}, "flags": flags,
            "anomalies": anomalies, "episodes": episodes, "trend_degree": degree, "grubbs_passes": passes}


def analyze(snapshot, settings: Settings):
    matrix = np.asarray(snapshot['values'])
    dates = snapshot['dates']
    series = [analyze_series(name, matrix[:, index], dates, settings) for index, name in enumerate(snapshot['mines'])]
    total = analyze_series('Total', matrix.sum(axis=1), dates, settings)
    result = {"source": {key: value for key, value in snapshot.items() if key not in {'values', 'audit'}},
            "settings": settings.model_dump(), "series": [total] + series,
            "anomaly_count": sum(len(s['anomalies']) for s in series),
            "methodology": {
                "units": "tonnes/day", "std": "Sample standard deviation (n-1)",
                "quartiles": "Linear interpolation (NumPy default)",
                "moving": "Trailing complete window, excluding the tested day; no test during warm-up",
                "grubbs": "Two-sided, one outlier per pass; repeated passes are exploratory, not generalized ESD",
                "trend": f"Polynomial degree {min(settings.trend_degree,len(dates)-1)} fitted (requested {settings.trend_degree}); limited to n-1 for short series. Descriptive fit, not a forecast.",
                "caution": "Raw-output screening: trends, weekday patterns and correlation can trigger tests. Statistical flags are not proof of incidents. Grubbs assumes approximately normal independent observations.",
                "combination": "Union of enabled methods; a day is counted once per series. Total is a separately tested series, not a sum of mine flags."
            }}
    return enrich(result, snapshot)
