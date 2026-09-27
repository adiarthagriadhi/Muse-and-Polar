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
