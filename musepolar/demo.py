"""Demo sessions for trying the dashboard and the CASS explorer without devices (--demo).

Writes a few synthetic recordings in the normal recording format: 60 s of rest (R0) followed
by a different condition, so the CASS explorer shows a visible shift between R0 and R1.
The signals are synthetic and carry no physiological meaning.
"""

from __future__ import annotations

import csv
import json
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np

from .streams import STREAMS

DURATION_S = 240.0
MARKER_S = 60.0

# per condition after the 60 s rest: EEG alpha/beta amplitude (uV), mean RR (s), RSA amplitude (s), breathing (Hz)
REST = {"alpha": 14.0, "beta": 3.0, "rr": 0.86, "rsa": 0.050, "breath": 0.25}
PROFILES = [
    ("DEMO_P01", "Tugas mental (aritmetika)", {"alpha": 12.0, "beta": 3.6, "rr": 0.78, "rsa": 0.036, "breath": 0.30}),
    ("DEMO_P02", "Napas lambat 6/menit", {"alpha": 16.5, "beta": 2.7, "rr": 0.90, "rsa": 0.120, "breath": 0.10}),
    ("DEMO_P03", "Pemulihan setelah latihan", None),  # recovery: starts aroused, drifts back to rest
]


def _level(t: np.ndarray, key: str, after: dict | None) -> np.ndarray:
    """Parameter over time: rest until MARKER_S, then a 10 s ramp to the condition."""
    rest = REST[key]
    if after is None:  # recovery profile
        start = {"alpha": 10.0, "beta": 4.0, "rr": 0.62, "rsa": 0.022, "breath": 0.35}[key]
        k = np.clip((t - MARKER_S) / (DURATION_S - MARKER_S), 0, 1)
        return np.where(t < MARKER_S, rest, start + (rest - start) * (1 - np.exp(-3 * k)))
    ramp = np.clip((t - MARKER_S) / 10.0, 0, 1)
    return rest + (after[key] - rest) * ramp


def _wander(t, rng, amount=0.2):
    """Slow random fluctuation around 1 so that R0 is not perfectly steady."""
    f = rng.uniform(1 / 40, 1 / 8, 3)
    ph = rng.uniform(0, 2 * np.pi, 3)
    return 1 + amount * sum(np.sin(2 * np.pi * fi * t + p) for fi, p in zip(f, ph)) / 2


def _beats(after, rng) -> np.ndarray:
    beats, t, phase = [], 0.3, 0.0
    grid = np.arange(0, DURATION_S + 2, 0.5)
    wander = _wander(grid, rng, 0.35)
    while t < DURATION_S:
        beats.append(t)
        tt = np.array([t])
        mean, rsa, br = (_level(tt, k, after)[0] for k in ("rr", "rsa", "breath"))
        rsa *= np.interp(t, grid, wander)
        phase += 2 * np.pi * br * (beats[-1] - (beats[-2] if len(beats) > 1 else 0))
        t += mean + rsa * np.sin(phase) + rng.normal(0, 0.008)
    return np.array(beats)


def _eeg(t, after, rng):
    alpha = _level(t, "alpha", after) * _wander(t, rng, 0.35)
    beta = _level(t, "beta", after) * _wander(t, rng, 0.35)
    rows = []
    for ch in range(4):
        ph = rng.uniform(0, 2 * np.pi, 3)
        v = (alpha * (1 + 0.25 * np.sin(2 * np.pi * t / 17 + ch)) * np.sin(2 * np.pi * 10 * t + ph[0])
             + beta * np.sin(2 * np.pi * 21 * t + ph[1]) + beta * 0.6 * np.sin(2 * np.pi * 16 * t + ph[2])
             + 5 * np.sin(2 * np.pi * 6 * t + ch) + 3 * np.sin(2 * np.pi * 50 * t) + rng.normal(0, 4, t.size))
        if ch in (1, 2):  # occasional blinks on the frontal channels
            for b in np.arange(4.0, DURATION_S, 9.0):
                v -= 120 * np.exp(-((t - b) ** 2) / 0.004)
        rows.append(800 + v)
    return np.column_stack(rows)


def _ecg(t, beats):
    v = np.zeros_like(t)
    for b in beats:
        m = (t > b - 0.3) & (t < b + 0.45)
        d = t[m] - b
        v[m] += (150 * np.exp(-((d + 0.16) ** 2) / 0.0008) - 120 * np.exp(-((d + 0.03) ** 2) / 0.00005)
                 + 1400 * np.exp(-(d ** 2) / 0.00007) - 250 * np.exp(-((d - 0.03) ** 2) / 0.00006)
                 + 300 * np.exp(-((d - 0.25) ** 2) / 0.003))
    return v


def _write(folder: Path, stream: str, ts, rows) -> int:
    with open(folder / f"{stream}.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["timestamp", *STREAMS[stream]["columns"]])
        for t, row in zip(ts, rows):
            w.writerow([f"{t:.6f}", *(round(float(v), 6) if isinstance(v, (float, np.floating)) else v for v in row)])
    return len(ts)


def make_session(base: Path, name: str, note: str, after, start: datetime, seed: int) -> Path:
    rng = np.random.default_rng(seed)
    folder = Path(base) / f"{start:%Y%m%d_%H%M%S}_{name}"
    folder.mkdir(parents=True, exist_ok=True)
    t0 = start.timestamp()
    counts = {}

    t = np.arange(0, DURATION_S, 1 / 256)
    counts["muse_eeg"] = _write(folder, "muse_eeg", t0 + t, _eeg(t, after, rng))

    beats = _beats(after, rng)
    rr = np.diff(beats) * 1000
    counts["polar_rr"] = _write(folder, "polar_rr", t0 + beats[1:], [[round(x, 1)] for x in rr])
    hr_t = np.arange(1, DURATION_S, 1.0)
    hr = [[int(round(60000 / np.mean(rr[max(0, i - 4):i + 1]))), 1]
          for i in np.searchsorted(beats[1:], hr_t).clip(0, len(rr) - 1)]
    counts["polar_hr"] = _write(folder, "polar_hr", t0 + hr_t, hr)

    te = np.arange(0, DURATION_S, 1 / 130)
    ecg = _ecg(te, beats) + 40 * np.sin(2 * np.pi * 0.25 * te) + rng.normal(0, 12, te.size)
    counts["polar_ecg"] = _write(folder, "polar_ecg", t0 + te, [[round(v), int(x * 1e9)] for v, x in zip(ecg, te)])

    tp = np.arange(0, DURATION_S, 1 / 64)
    phase = np.interp(tp, beats, np.arange(beats.size)) * 2 * np.pi
    pulse = np.sin(phase) + 0.3 * np.sin(2 * phase + 1)
    ppg = np.column_stack([30000 + rng.normal(0, 30, tp.size), 250000 + 3000 * pulse, 180000 + 1800 * pulse])
    counts["muse_ppg"] = _write(folder, "muse_ppg", t0 + tp, ppg)

    ta = np.arange(0, DURATION_S, 1 / 52)
    acc = np.column_stack([0.02 * np.sin(ta), -0.05 + 0.01 * np.sin(0.7 * ta), 0.99 + rng.normal(0, 0.005, ta.size)])
    counts["muse_acc"] = _write(folder, "muse_acc", t0 + ta, acc)
    tpa = np.arange(0, DURATION_S, 1 / 200)
    pacc = [[-0.98 + rng.normal(0, 0.01), 0.05, 0.12, int(x * 1e9)] for x in tpa]
    counts["polar_acc"] = _write(folder, "polar_acc", t0 + tpa, pacc)

    counts["marker"] = _write(folder, "marker", [t0 + 1, t0 + MARKER_S], [["Baseline mulai"], [note]])

    meta = {
        "name": name, "note": f"DEMO (sintetis): {note}",
        "start_unix": t0, "start_local": start.isoformat(timespec="seconds"),
        "end_unix": t0 + DURATION_S, "duration_sec": DURATION_S,
        "devices": {"muse": {"name": "Muse-DEMO"}, "polar": {"name": "Polar H10 DEMO"}},
        "samples": counts, "sync": [], "sync_drift_ms_per_hour": None,
        "demo": "Synthetic data for trying the software; no physiological meaning.",
        "timestamp": "Unix time in seconds (host clock), per sample",
    }
    (folder / "session.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    return folder


def ensure_demo_sessions(base: Path) -> list[Path]:
    """Create the demo sessions once; keep any that already exist."""
    base = Path(base)
    existing = {p.name.split("_", 2)[-1]: p for p in base.glob("*_DEMO_P*") if p.is_dir()}
    start = (datetime.now() - timedelta(days=1)).replace(hour=9, minute=0, second=0, microsecond=0)
    out = []
    for i, (name, note, after) in enumerate(PROFILES):
        out.append(existing.get(name) or make_session(base, name, note, after, start + timedelta(minutes=10 * i), seed=i))
    return out
