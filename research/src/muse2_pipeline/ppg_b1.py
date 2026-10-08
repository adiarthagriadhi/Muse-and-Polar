"""Reference PPG pipeline of manuscript B1 (Muse 2 forehead PPG vs Polar H10).

This is the single PPG pipeline used for every claim about forehead-PPG quality in the
B-cluster manuscripts. The functions are copied unchanged in behaviour from the B1
analysis script (``muse_polar_analysis.py``, which reproduced the published B1 tables
exactly); only names and docstrings were adapted. Do not change the defaults here: any
deviation must be reported as a different pipeline.

Pre-specified B1 settings:

* channel PPG_2 (infrared; ``ir`` in musepolar recordings, ``PPG2`` in the research app),
  positive polarity, assumed uniformly sampled at 64 Hz; zero samples linearly interpolated;
* Butterworth 3rd-order band-pass 0.6-3.5 Hz, zero-phase (``filtfilt``);
* peaks: minimum distance 60/160 s (160 bpm), prominence 1.4826 x MAD of the filtered signal;
* interval rule, identical for Muse and Polar: 300-2000 ms and change > 20 % from the
  preceding interval rejected ("malik"); the B1 sensitivity rule "median" rejects
  intervals > 25 % from the local median of 7 intervals;
* RMSSD from successive valid intervals only (no differences across removed intervals).

Forehead-PPG intervals are pulse-rate variability (PRV), not heart-rate variability (HRV).
In B1, Muse 2 agreed with Polar H10 for heart rate, but ultra-short (60 s) RMSSD from the
forehead PPG was overestimated. Report PPG RMSSD/SDNN as PRV and do not treat them as
interchangeable with ECG-based HRV.
"""

from __future__ import annotations

import numpy as np
from scipy.ndimage import median_filter
from scipy.signal import butter, filtfilt, find_peaks

FS = 64.0
BAND = (0.6, 3.5)


def preprocess(sig, band=BAND, fs: float = FS) -> np.ndarray:
    """Zero samples interpolated, then 3rd-order Butterworth band-pass, zero-phase."""
    s = np.asarray(sig, float).copy()
    z = s == 0
    if z.any() and (~z).any():
        i = np.arange(len(s))
        s[z] = np.interp(i[z], i[~z], s[~z])
    b, a = butter(3, [band[0] / (fs / 2), band[1] / (fs / 2)], btype="band")
    return filtfilt(b, a, s)


def detect_peaks(t, x, k: float = 1.0, refine: bool = False, fs: float = FS) -> np.ndarray:
    """Pulse-peak times (s) in a filtered PPG ``x`` sampled at times ``t``.

    Prominence = ``k`` x 1.4826 x MAD (B1 primary: k = 1). ``refine`` = parabolic sub-sample
    interpolation (B1 sensitivity analysis S8 only).
    """
    t = np.asarray(t, float)
    x = np.asarray(x, float)
    mad = np.median(np.abs(x - np.median(x)))
    pk, _ = find_peaks(x, distance=int(round(fs * 60 / 160)), prominence=k * 1.4826 * mad)
    pk = pk[(pk > 0) & (pk < len(x) - 1)]
    tp = t[pk].copy()
    if refine:
        y0, y1, y2 = x[pk - 1], x[pk], x[pk + 1]
        den = y0 - 2 * y1 + y2
        tp = tp + np.where(den != 0, 0.5 * (y0 - y2) / np.where(den != 0, den, 1.0), 0.0) / fs
    return tp


def ppg_beats(sig, time_s, k: float = 1.0, refine: bool = False, fs: float = FS) -> np.ndarray:
    """Pulse times (s) from a raw PPG_2 channel with the B1 settings (B1: fs = 64 Hz)."""
    if len(sig) < 22:  # filtfilt needs more samples than its padding
        return np.array([])
    return detect_peaks(time_s, preprocess(sig, fs=fs), k, refine, fs=fs)


def valid_intervals(ibi_ms, rule: str = "malik") -> np.ndarray:
    """Validity mask for intervals in ms (same rule for Muse pulses and Polar RR)."""
    ibi = np.asarray(ibi_ms, float)
    ok = (ibi >= 300) & (ibi <= 2000)
    if rule == "malik":  # > 20 % change relative to the preceding interval
        c = np.ones(len(ibi), bool)
        c[1:] = np.abs(ibi[1:] - ibi[:-1]) / ibi[:-1] <= 0.20
        return ok & c
    if rule == "median":  # > 25 % from the local median of 7 intervals
        med = median_filter(ibi, size=7, mode="nearest")
        return ok & (np.abs(ibi - med) / med <= 0.25)
    raise ValueError(rule)


def window_metrics(tbeats, lo: float, hi: float, rule: str = "malik", gap_spanning: bool = False) -> dict:
    """HR (bpm), SDNN and RMSSD (ms) and artefact fraction of the intervals ending in [lo, hi).

    ``tbeats`` are beat or pulse times (s). For PPG the SDNN/RMSSD values are PRV.
    """
    tbeats = np.asarray(tbeats, float)
    ibi = np.diff(tbeats) * 1000.0
    te = tbeats[1:]
    ok = valid_intervals(ibi, rule)
    m = (te >= lo) & (te < hi)
    ib, o = ibi[m], ok[m]
    nn = ib[o]
    idx = np.where(o)[0]
    cons = idx[1:] == idx[:-1] + 1
    d = np.diff(nn) if gap_spanning else np.diff(nn)[cons]
    nan = float("nan")
    return dict(
        hr=60000.0 / nn.mean() if len(nn) else nan,
        sdnn=nn.std(ddof=1) if len(nn) > 1 else nan,
        rmssd=float(np.sqrt(np.mean(d ** 2))) if len(d) else nan,
        art=1 - o.mean() if len(o) else nan,
        n=int(len(nn)),
    )


def interval_series(t_beats, ibi_s=None, rule: str = "malik") -> dict:
    """Intervals with the B1 validity mask, as used by the Research View.

    ``t_beats``: beat times (s). If ``ibi_s`` is given (Polar RR), ``t_beats`` are the times at which
    those intervals ended. Returns ``t`` (end of interval, s), ``ibi`` (s) and ``valid``.
    """
    t_beats = np.asarray(t_beats, float)
    if ibi_s is None:
        ibi, t = np.diff(t_beats), t_beats[1:]
    else:
        ibi, t = np.asarray(ibi_s, float), t_beats
    return {"t": t, "ibi": ibi, "valid": valid_intervals(ibi * 1000.0, rule) if len(ibi) else np.array([], bool)}


def polar_beats(rr_ms) -> np.ndarray:
    """Polar beat times (s) = cumulative RR from the start of the file (B1 convention)."""
    rr = np.asarray(rr_ms, float)
    return np.concatenate([[0.0], np.cumsum(rr) / 1000.0])
