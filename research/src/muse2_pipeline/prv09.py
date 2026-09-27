from __future__ import annotations

import numpy as np
from scipy.signal import find_peaks

FS_PPG = 64.0


def detect_ppg_peaks_168r4(sig, fs=FS_PPG):
    x = np.asarray(sig, float)
    if len(x) < 3:
        return np.array([], dtype=int)
    med = np.median(x)
    mad = np.median(np.abs(x - med))
    prom = mad if mad > 0 else np.finfo(float).eps
    pk, _ = find_peaks(x, distance=max(1, int(round(0.30 * fs))), prominence=prom)
    return pk.astype(int)


def prv_from_ibi(nn):
    nn = np.asarray(nn, float)
    nn = nn[(nn >= 60 / 180) & (nn <= 60 / 40)]
    if len(nn) < 8:
        return {"n": int(len(nn)), "hr": np.nan, "prv_sdnn": np.nan,
                "prv_rmssd": np.nan, "ok": False}
    return {
        "n": int(len(nn)),
        "hr": float(60.0 / np.median(nn)),
        "prv_sdnn": float(nn.std(ddof=1) * 1000),
        "prv_rmssd": float(np.sqrt(np.mean(np.diff(nn) ** 2)) * 1000),
        "ok": True,
    }


def compute_prv_09(ppg2, time_s, t0=None, t1=None):
    time_s = np.asarray(time_s, float)
    if len(time_s) == 0:  # session recorded without PPG (--no-ppg)
        out = prv_from_ibi([])
        out.update({"t0": np.nan if t0 is None else float(t0),
                    "t1": np.nan if t1 is None else float(t1), "tp": np.array([])})
        return out
    pk = detect_ppg_peaks_168r4(ppg2)
    tp = time_s[pk]
    ibi = np.diff(tp) if len(pk) >= 2 else np.array([])
    t0 = float(time_s[0]) if t0 is None else float(t0)
    t1 = float(time_s[-1]) if t1 is None else float(t1)
    m = (tp[:-1] >= t0) & (tp[:-1] < t1) if len(ibi) else np.array([], dtype=bool)
    out = prv_from_ibi(ibi[m] if len(ibi) else [])
    out.update({"t0": t0, "t1": t1, "tp": tp})
    return out
