from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.signal import butter, iirnotch, sosfiltfilt, tf2sos, welch

FS_EEG = 256.0
CH = ["TP9", "AF7", "AF8", "TP10"]
BANDS = {"delta": (1, 4), "theta": (4, 8), "alpha": (8, 13), "beta": (13, 30)}


def filter_eeg(eeg: pd.DataFrame) -> pd.DataFrame:
    x = eeg[CH].to_numpy(float)
    b, a = iirnotch(50.0, 30.0, FS_EEG)
    x = sosfiltfilt(tf2sos(b, a), x, axis=0)
    x = sosfiltfilt(butter(4, [1, 40], btype="bandpass", fs=FS_EEG, output="sos"), x, axis=0)
    out = eeg.copy()
    out[CH] = x
    out["artifact_amp"] = np.abs(x).max(axis=1) > 80
    return out


def bandpower_windows(eeg_f: pd.DataFrame, win_s: float = 4.0, step_s: float = 2.0) -> pd.DataFrame:
    arr = eeg_f[CH].to_numpy(float)
    t = eeg_f["time_s"].to_numpy(float)
    fs = FS_EEG
    win = int(win_s * fs)
    step = int(step_s * fs)
    rows = []
    if len(arr) < win:
        return pd.DataFrame()
    for start in range(0, len(arr) - win + 1, step):
        sl = slice(start, start + win)
        row = {"t_start": float(t[start]), "t_end": float(t[start + win - 1])}
        for i, c in enumerate(CH):
            f, pxx = welch(arr[sl, i], fs=fs, nperseg=win)
            for name, (lo, hi) in BANDS.items():
                m = (f >= lo) & (f < hi)
                if m.sum() < 2:
                    row[f"{c}_{name}"] = np.nan
                else:
                    row[f"{c}_{name}"] = float(np.trapezoid(pxx[m], f[m]))
        rows.append(row)
    return pd.DataFrame(rows)


# --- Research View v2 -------------------------------------------------------
#
# Spectra are estimated on short sub-segments (2 s Hann, 0.25 s hop). A 4 s analysis window
# averages only its artifact-free sub-segments, so a single eye blink removes ~2 s of data
# instead of the whole window.

PSD_FMAX = 40.0
SUB_S, HOP_S = 2.0, 0.25


def subsegment_spectra(eeg_f: pd.DataFrame, seg_s: float = SUB_S, hop_s: float = HOP_S) -> dict:
    """Periodograms of overlapping sub-segments of the filtered EEG.

    Returns ``t0`` (n,), ``psd`` (n, 4, nf) in µV²/Hz for 1–40 Hz, ``freqs`` (nf,),
    ``power[band]`` and ``total`` (n, 4) in µV², ``max_abs`` and ``std`` (n, 4).
    """
    from numpy.lib.stride_tricks import sliding_window_view

    x = eeg_f[CH].to_numpy(float)
    t = eeg_f["time_s"].to_numpy(float)
    L, hop = int(seg_s * FS_EEG), int(hop_s * FS_EEG)
    f = np.fft.rfftfreq(L, 1 / FS_EEG)
    keep = (f >= 1) & (f <= PSD_FMAX)
    nf = int(keep.sum())
    if len(x) < L:
        z = np.zeros((0, len(CH)))
        return {"t0": np.zeros(0), "psd": np.zeros((0, len(CH), nf), np.float32), "freqs": f[keep],
                "power": {b: z for b in BANDS}, "total": z, "max_abs": z, "std": z, "seg_s": seg_s, "hop_s": hop_s}
    view = sliding_window_view(x, L, axis=0)[::hop]  # (n, 4, L), no copy
    n = view.shape[0]
    win = np.hanning(L)
    scale = 1.0 / (FS_EEG * (win ** 2).sum())
    df = f[1] - f[0]
    psd = np.empty((n, len(CH), nf), np.float32)
    power = {b: np.empty((n, len(CH))) for b in BANDS}
    total = np.empty((n, len(CH)))
    band_masks = {b: (f >= lo) & (f < hi) for b, (lo, hi) in BANDS.items()}
    tot_mask = (f >= 1) & (f < PSD_FMAX)
    for a in range(0, n, 1024):
        seg = view[a:a + 1024]
        seg = seg - seg.mean(axis=-1, keepdims=True)
        p = np.abs(np.fft.rfft(seg * win, axis=-1)) ** 2 * scale
        p[..., 1:-1] *= 2
        psd[a:a + 1024] = p[..., keep]
        for b, m in band_masks.items():
            power[b][a:a + 1024] = p[..., m].sum(axis=-1) * df
        total[a:a + 1024] = p[..., tot_mask].sum(axis=-1) * df
    return {
        "t0": t[np.arange(n) * hop],
        "psd": psd, "freqs": f[keep], "power": power, "total": total,
        "max_abs": np.abs(view).max(axis=-1), "std": view.std(axis=-1),
        "seg_s": seg_s, "hop_s": hop_s,
    }


def window_spectra(sub: dict, art_uv: float = 100.0, flat_uv: float = 0.5,
                   win_s: float = 4.0, step_s: float = 2.0) -> dict:
    """Band power per analysis window from the clean sub-segments inside it.

    Returns ``t_start``, ``t_mid`` (n,), ``power[band]``, ``total`` (n, 4) in µV²,
    ``n_clean`` (n, 4) clean sub-segments per window, ``bad`` (n, 4) True when a channel
    window has no clean sub-segment, ``clean`` (nsub, 4) the sub-segment mask.
    """
    clean = (sub["max_abs"] <= art_uv) & (sub["std"] >= flat_uv)
    nsub = len(sub["t0"])
    per_win = int(round((win_s - sub["seg_s"]) / sub["hop_s"])) + 1
    stride = int(round(step_s / sub["hop_s"]))
    nwin = (nsub - per_win) // stride + 1 if nsub >= per_win else 0
    i0 = np.arange(nwin) * stride
    i1 = i0 + per_win

    def wsum(a):
        c = np.concatenate([np.zeros((1,) + a.shape[1:]), np.cumsum(a, axis=0)])
        return c[i1] - c[i0]

    cnt = wsum(clean.astype(float))
    with np.errstate(invalid="ignore", divide="ignore"):
        power = {b: wsum(np.where(clean, v, 0.0)) / cnt for b, v in sub["power"].items()}
        total = wsum(np.where(clean, sub["total"], 0.0)) / cnt
    t_start = sub["t0"][i0] if nwin else np.zeros(0)
    return {
        "t_start": t_start, "t_mid": t_start + win_s / 2, "power": power, "total": total,
        "n_clean": cnt.astype(int), "bad": cnt < 1, "clean": clean, "win_s": win_s, "step_s": step_s,
    }
