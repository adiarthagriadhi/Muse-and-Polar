"""Beat-to-beat intervals from the Muse forehead PPG and the Polar H10 RR stream.

The forehead pulse (PRV) is detected on a band-passed infrared PPG with an adaptive
prominence, and every interval is checked against its neighbours so that missed or
extra beats do not inflate RMSSD. Polar RR intervals go through the same checks.
PRV (forehead pulse) and HRV (chest ECG) are reported separately: they are related
but not interchangeable.
"""

from __future__ import annotations

import numpy as np
from scipy.ndimage import median_filter
from scipy.signal import butter, find_peaks, sosfiltfilt

FS_PPG = 64.0
IBI_MIN, IBI_MAX = 60 / 180, 60 / 35  # s: 35–180 bpm
MAX_DEV = 0.25  # an interval may differ at most 25 % from the local median


def ppg_beats(sig, time_s, fs: float = FS_PPG) -> np.ndarray:
    """Times (s) of pulse peaks in a raw PPG channel."""
    x = np.asarray(sig, float)
    t = np.asarray(time_s, float)
    if len(x) < int(4 * fs):
        return np.array([])
    x = sosfiltfilt(butter(2, [0.5, 3.5], btype="bandpass", fs=fs, output="sos"), x - np.median(x))
    # Adaptive prominence: typical pulse amplitude in 10 s blocks (robust to motion bursts).
    blk = int(10 * fs)
    amps = [np.percentile(x[i:i + blk], 95) - np.percentile(x[i:i + blk], 5)
            for i in range(0, len(x) - blk + 1, blk)] or [np.percentile(x, 95) - np.percentile(x, 5)]
    prom = 0.3 * float(np.median(amps))
    if prom <= 0:
        return np.array([])
    pk, _ = find_peaks(x, distance=max(1, int(IBI_MIN * fs)), prominence=prom)
    return t[pk]


def clean_ibi(t_beats, ibi=None) -> dict:
    """Intervals between beats with a validity mask.

    ``t_beats``: beat times (s). If ``ibi`` (s) is given, ``t_beats`` are the times at
    which those intervals ended (as for Polar RR). Returns ``t`` (end of interval),
    ``ibi`` (s) and ``valid`` (physiological range and within 25 % of the local median).
    """
    t_beats = np.asarray(t_beats, float)
    if ibi is None:
        ibi = np.diff(t_beats)
        t = t_beats[1:]
    else:
        ibi = np.asarray(ibi, float)
        t = t_beats
    if len(ibi) == 0:
        return {"t": np.array([]), "ibi": np.array([]), "valid": np.array([], bool)}
    ok = (ibi >= IBI_MIN) & (ibi <= IBI_MAX)
    ref = ibi.copy()
    ref[~ok] = np.nan
    med = median_filter(np.nan_to_num(ref, nan=np.nanmedian(ref) if ok.any() else 1.0), size=7, mode="nearest")
    valid = ok & (np.abs(ibi - med) <= MAX_DEV * med)
    return {"t": t, "ibi": ibi, "valid": valid}


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


def hr_at(series: dict, t_centers, half_width: float) -> np.ndarray:
    """Mean HR (bpm) of valid intervals within ±half_width of each time; NaN if none."""
    t, ibi, valid = series["t"], series["ibi"], series["valid"]
    t, ibi = t[valid], ibi[valid]
    out = np.full(len(t_centers), np.nan)
    if not len(t):
        return out
    lo = np.searchsorted(t, np.asarray(t_centers) - half_width)
    hi = np.searchsorted(t, np.asarray(t_centers) + half_width)
    for i, (a, b) in enumerate(zip(lo, hi)):
        if b > a:
            out[i] = 60.0 / ibi[a:b].mean()
    return out
