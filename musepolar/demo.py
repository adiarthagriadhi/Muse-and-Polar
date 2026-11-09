"""Demo sessions for trying the dashboard, the CASS explorer and CorVa Space without devices (--demo).

Writes synthetic recordings in the normal recording format:
- DEMO_P01–P03 (4 min): 60 s of rest (R0) followed by a different condition, so the CASS explorer
  shows a visible shift between R0 and R1;
- DEMO_P04–P05 (17 min): the CorVa standard protocol with its "CorVa: …" phase markers, for the
  CorVa Space page. P04 behaves as the protocol expects; in P05 the participant gets drowsy with the
  eyes closed (theta up, vagal down), so one phase differs from its expectation.
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
REST = {"alpha": 14.0, "beta": 3.0, "theta": 5.0, "rr": 0.86, "rsa": 0.050, "breath": 0.25}
PROFILES = [
    ("DEMO_P01", "Tugas mental (aritmetika)", {"alpha": 12.0, "beta": 3.6, "rr": 0.78, "rsa": 0.036, "breath": 0.30}),
    ("DEMO_P02", "Napas lambat 6/menit", {"alpha": 16.5, "beta": 2.7, "rr": 0.90, "rsa": 0.120, "breath": 0.10}),
    ("DEMO_P03", "Pemulihan setelah latihan", None),  # recovery: starts aroused, drifts back to rest
]


# CorVa standard protocol demos: phase id -> condition (missing keys = REST)
SLOW = {"rr": 0.90, "rsa": 0.14, "breath": 0.10}
CORVA_PROFILES = [
    ("DEMO_P04", "Protokol CorVa standar", {
        "eo_deep": {"alpha": 15.0, **SLOW},
        "ec_reg": {"alpha": 24.0, "beta": 2.8},
        "ec_deep": {"alpha": 25.0, "beta": 2.7, **SLOW},
    }),
    ("DEMO_P05", "Protokol CorVa · mengantuk saat mata tertutup", {
        "eo_deep": {"alpha": 15.0, **SLOW},
        "ec_reg": {"alpha": 19.0, "beta": 2.6, "theta": 15.0, "rr": 0.95, "rsa": 0.032},
        "ec_deep": {"alpha": 24.0, "beta": 2.7, "theta": 9.0, **SLOW},
    }),
]


def _level(t: np.ndarray, key: str, after: dict | None) -> np.ndarray:
    """Parameter over time: rest until MARKER_S, then a 10 s ramp to the condition."""
    rest = REST[key]
    if after is None:  # recovery profile
        start = {"alpha": 10.0, "beta": 4.0, "theta": 5.0, "rr": 0.62, "rsa": 0.022, "breath": 0.35}[key]
        k = np.clip((t - MARKER_S) / (DURATION_S - MARKER_S), 0, 1)
        return np.where(t < MARKER_S, rest, start + (rest - start) * (1 - np.exp(-3 * k)))
    ramp = np.clip((t - MARKER_S) / 10.0, 0, 1)
    return rest + (after.get(key, rest) - rest) * ramp


def protocol_schedule() -> list[tuple[str, float]]:
    """(phase id, start s) of the CorVa standard protocol, and its total length."""
    from corva import protocol

    out, t = [], 0.0
    for ph in protocol.PROTOCOL:
        out.append((ph["id"], t))
        t += ph["seconds"]
    return out, t


def _phase_level(conditions: dict):
    """Parameter over time for a protocol demo: each phase's condition, 8 s ramp at every phase start."""
    schedule, _total = protocol_schedule()
    starts = np.array([s for _, s in schedule])

    def level(t: np.ndarray, key: str) -> np.ndarray:
        vals = np.array([conditions.get(pid, {}).get(key, REST[key]) for pid, _ in schedule])
        i = np.clip(np.searchsorted(starts, t, side="right") - 1, 0, len(starts) - 1)
        prev = vals[np.maximum(i - 1, 0)]
        ramp = np.clip((t - starts[i]) / 8.0, 0, 1)
        return prev + (vals[i] - prev) * ramp
    return level


def _wander(t, rng, amount=0.2):
    """Slow random fluctuation around 1 so that R0 is not perfectly steady."""
    f = rng.uniform(1 / 40, 1 / 8, 3)
    ph = rng.uniform(0, 2 * np.pi, 3)
    return 1 + amount * sum(np.sin(2 * np.pi * fi * t + p) for fi, p in zip(f, ph)) / 2


def _beats(level, duration, rng) -> np.ndarray:
    beats, t, phase = [], 0.3, 0.0
    grid = np.arange(0, duration + 2, 0.5)
    wander = _wander(grid, rng, 0.35)
    while t < duration:
        beats.append(t)
        tt = np.array([t])
        mean, rsa, br = (level(tt, k)[0] for k in ("rr", "rsa", "breath"))
        rsa *= np.interp(t, grid, wander)
        phase += 2 * np.pi * br * (beats[-1] - (beats[-2] if len(beats) > 1 else 0))
        t += mean + rsa * np.sin(phase) + rng.normal(0, 0.008)
    return np.array(beats)


def _eeg(t, level, rng):
    alpha = level(t, "alpha") * _wander(t, rng, 0.35)
    beta = level(t, "beta") * _wander(t, rng, 0.35)
    theta = level(t, "theta")
    rows = []
    for ch in range(4):
        ph = rng.uniform(0, 2 * np.pi, 3)
        v = (alpha * (1 + 0.25 * np.sin(2 * np.pi * t / 17 + ch)) * np.sin(2 * np.pi * 10 * t + ph[0])
             + beta * np.sin(2 * np.pi * 21 * t + ph[1]) + beta * 0.6 * np.sin(2 * np.pi * 16 * t + ph[2])
             + theta * np.sin(2 * np.pi * 6 * t + ch) + 3 * np.sin(2 * np.pi * 50 * t) + rng.normal(0, 4, t.size))
        if ch in (1, 2):  # occasional blinks on the frontal channels
            for b in np.arange(4.0, t[-1], 9.0):
                v -= 120 * np.exp(-((t - b) ** 2) / 0.004)
        rows.append(800 + v)
    return np.column_stack(rows)


def _ecg(t, beats):
    v = np.zeros_like(t)
    for b in beats:
        lo, hi = np.searchsorted(t, [b - 0.3, b + 0.45])
        m = slice(lo, hi)
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
    """4 min demo: 60 s rest, then the condition `after` (None = recovery)."""
    return _make(base, name, note, lambda t, k: _level(t, k, after), DURATION_S,
                 [(1.0, "Baseline mulai"), (MARKER_S, note)], start, seed)


def make_protocol_session(base: Path, name: str, note: str, conditions: dict, start: datetime, seed: int) -> Path:
    """17 min demo of the CorVa standard protocol, with the dashboard's "CorVa: …" phase markers."""
    from corva import protocol

    schedule, total = protocol_schedule()
    markers = [(0.5, "SYNC mulai")] + [(s + 0.2, protocol.marker_label(pid)) for pid, s in schedule]
    markers.append((total - 0.5, protocol.MARKER_PREFIX + "selesai"))
    return _make(base, name, note, _phase_level(conditions), total, markers, start, seed)


def _make(base: Path, name: str, note: str, level, duration: float, markers, start: datetime, seed: int) -> Path:
    rng = np.random.default_rng(seed)
    folder = Path(base) / f"{start:%Y%m%d_%H%M%S}_{name}"
    folder.mkdir(parents=True, exist_ok=True)
    t0 = start.timestamp()
    counts = {}

    t = np.arange(0, duration, 1 / 256)
    counts["muse_eeg"] = _write(folder, "muse_eeg", t0 + t, _eeg(t, level, rng))

    beats = _beats(level, duration, rng)
    rr = np.diff(beats) * 1000
    counts["polar_rr"] = _write(folder, "polar_rr", t0 + beats[1:], [[round(x, 1)] for x in rr])
    hr_t = np.arange(1, duration, 1.0)
    hr = [[int(round(60000 / np.mean(rr[max(0, i - 4):i + 1]))), 1]
          for i in np.searchsorted(beats[1:], hr_t).clip(0, len(rr) - 1)]
    counts["polar_hr"] = _write(folder, "polar_hr", t0 + hr_t, hr)

    te = np.arange(0, duration, 1 / 130)
    ecg = _ecg(te, beats) + 40 * np.sin(2 * np.pi * 0.25 * te) + rng.normal(0, 12, te.size)
    counts["polar_ecg"] = _write(folder, "polar_ecg", t0 + te, [[round(v), int(x * 1e9)] for v, x in zip(ecg, te)])

    tp = np.arange(0, duration, 1 / 64)
    phase = np.interp(tp, beats, np.arange(beats.size)) * 2 * np.pi
    pulse = np.sin(phase) + 0.3 * np.sin(2 * phase + 1)
    ppg = np.column_stack([30000 + rng.normal(0, 30, tp.size), 250000 + 3000 * pulse, 180000 + 1800 * pulse])
    counts["muse_ppg"] = _write(folder, "muse_ppg", t0 + tp, ppg)

    ta = np.arange(0, duration, 1 / 52)
    acc = np.column_stack([0.02 * np.sin(ta), -0.05 + 0.01 * np.sin(0.7 * ta), 0.99 + rng.normal(0, 0.005, ta.size)])
    counts["muse_acc"] = _write(folder, "muse_acc", t0 + ta, acc)
    tpa = np.arange(0, duration, 1 / 200)
    pacc = [[-0.98 + rng.normal(0, 0.01), 0.05, 0.12, int(x * 1e9)] for x in tpa]
    counts["polar_acc"] = _write(folder, "polar_acc", t0 + tpa, pacc)

    counts["marker"] = _write(folder, "marker", [t0 + m for m, _ in markers], [[label] for _, label in markers])

    meta = {
        "name": name, "note": f"DEMO (sintetis): {note}",
        "start_unix": t0, "start_local": start.isoformat(timespec="seconds"),
        "end_unix": t0 + duration, "duration_sec": duration,
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
    for j, (name, note, conditions) in enumerate(CORVA_PROFILES):
        out.append(existing.get(name) or make_protocol_session(
            base, name, note, conditions, start + timedelta(minutes=40 + 20 * j), seed=10 + j))
    return out
