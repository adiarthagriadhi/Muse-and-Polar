"""Interval statistics and ECG R-peak detection.

Forehead-PPG pulses and their validity mask come from ``ppg_b1`` (the B1 pipeline); the same
B1 interval rule is applied to Polar RR and ECG intervals. PRV (forehead pulse) and HRV (chest
ECG) are reported separately: they are related but not interchangeable.
"""

from __future__ import annotations

import numpy as np
from scipy.signal import butter, find_peaks, sosfiltfilt

IBI_MIN = 60 / 180  # s: shortest R-R interval searched for (180 bpm)


def hrv_stats(series: dict, t0: float | None = None, t1: float | None = None) -> dict:
    """HR and time-domain variability of the valid intervals ending in [t0, t1)."""
    t, ibi, valid = series["t"], series["ibi"], series["valid"]
    m = np.ones(len(t), bool)
    if t0 is not None:
        m &= t >= t0
    if t1 is not None:
        m &= t < t1
    n_all = int(m.sum())
    good = m & valid
    x = ibi[good]
    # successive differences only between two consecutive valid intervals
    pair = good[1:] & good[:-1]
    d = np.diff(ibi)[pair]
    out = {"n": int(good.sum()), "n_total": n_all,
           "valid_frac": float(good.sum() / n_all) if n_all else None,
           "hr": None, "sdnn": None, "rmssd": None, "pnn50": None, "ok": False}
    if len(x) >= 8:
        out.update({
            "hr": float(60.0 / x.mean()),
            "sdnn": float(x.std(ddof=1) * 1000),
            "rmssd": float(np.sqrt(np.mean(d ** 2)) * 1000) if len(d) >= 5 else None,
            "pnn50": float(np.mean(np.abs(d) > 0.05) * 100) if len(d) >= 5 else None,
            "ok": True,
        })
    return out


def ecg_beats(sig, time_s, fs: float) -> np.ndarray:
    """Times (s) of R peaks in an ECG channel (e.g. from an EDF file)."""
    x = np.asarray(sig, float)
    t = np.asarray(time_s, float)
    if len(x) < int(4 * fs) or fs < 50:
        return np.array([])
    hi = min(25.0, 0.45 * fs)
    y = sosfiltfilt(butter(2, [5.0, hi], btype="bandpass", fs=fs, output="sos"), x - np.median(x))
    e = np.convolve(y ** 2, np.ones(max(1, int(0.08 * fs))) / max(1, int(0.08 * fs)), mode="same")
    blk = int(10 * fs)
    lv = [np.percentile(e[i:i + blk], 98) for i in range(0, len(e) - blk + 1, blk)] or [np.percentile(e, 98)]
    pk, _ = find_peaks(e, distance=max(1, int(IBI_MIN * fs)), height=0.3 * float(np.median(lv)))
    # refine to the largest deflection of the filtered ECG near each energy peak
    w = max(1, int(0.06 * fs))
    ref = [max(0, p - w) + int(np.argmax(np.abs(y[max(0, p - w):p + w + 1]))) for p in pk]
    return t[np.unique(ref)] if len(ref) else np.array([])
