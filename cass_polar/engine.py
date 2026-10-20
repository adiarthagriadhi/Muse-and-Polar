"""CASS–Polar direct session analysis.

Cortical implementation follows the uploaded CASS NB06 feeder and NB10 state
definitions (notch 50 Hz, 1–40 Hz, Welch 4s/2s, robust R0 z).
Autonomic Y is *explicitly changed*: Polar H10 ECG-derived RR RMSSD.
Research/teaching only; exploratory ultra-short HRV, not diagnosis.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.signal import butter, iirnotch, sosfiltfilt, tf2sos, welch
from scipy.integrate import trapezoid

from .polar_adapter import hrv_window, read_rr

FS_EEG = 256.0
CH = ("TP9", "AF7", "AF8", "TP10")
BANDS = {"alpha": (8.0, 13.0), "beta": (13.0, 30.0)}
WINDOW_S = 5.0
STEP_S = 2.5
RR_SPAN_S = 20.0
MIN_RR = 8


class CASSInputError(ValueError):
    pass


def _robust_location_scale(x):
    x = np.asarray(x, dtype=float)
    x = x[np.isfinite(x)]
    if not len(x):
        return np.nan, 1.0
    median = float(np.median(x))
    scale = float(1.4826 * np.median(np.abs(x - median)))
    if not np.isfinite(scale) or scale < 1e-12:
        scale = float(np.std(x))
    if not np.isfinite(scale) or scale < 1e-12:
        scale = 1.0
    return median, scale


def _bandpower(eeg):
    required = {"timestamp", *CH}
    if not required.issubset(eeg.columns):
        raise CASSInputError("EEG Muse harus memiliki timestamp, TP9, AF7, AF8, TP10")
    eeg = eeg[["timestamp", *CH]].apply(pd.to_numeric, errors="coerce")
    eeg = eeg.replace([np.inf, -np.inf], np.nan).dropna()
    eeg = eeg.sort_values("timestamp").drop_duplicates("timestamp")
    if len(eeg) < int(FS_EEG * 4):
        raise CASSInputError("EEG kurang dari 4 detik atau tidak lengkap")
    t = eeg["timestamp"].to_numpy(dtype=float)
    data = eeg[list(CH)].to_numpy(dtype=float)
    elapsed = t - t[0]
    # NB06 operates on 256-Hz sample index. Flag deviations; never resample silently.
    dt = np.diff(t)
    warnings = []
    if np.any((dt < 0.5 / FS_EEG) | (dt > 1.5 / FS_EEG)):
        warnings.append("EEG memiliki timestamp tidak teratur/packet loss; bandpower NB06 memakai grid sampel 256 Hz tanpa interpolasi.")
    if np.quantile(np.abs(dt - 1.0 / FS_EEG), 0.95) > 0.001:
        warnings.append("Jitter timestamp EEG terdeteksi; periksa sinkronisasi dan data hilang.")
    notch_b, notch_a = iirnotch(50.0, 30.0, FS_EEG)
    filtered = sosfiltfilt(tf2sos(notch_b, notch_a), data, axis=0)
    filtered = sosfiltfilt(
        butter(4, [1, 40], btype="bandpass", fs=FS_EEG, output="sos"),
        filtered, axis=0)
    artifact = np.max(np.abs(filtered), axis=1) > 80.0
    win, hop = int(4 * FS_EEG), int(2 * FS_EEG)
    rows = []
    for start in range(0, len(data) - win + 1, hop):
        stop = start + win
        if artifact[start:stop].mean() > 0.2:
            continue
        # Reject time-discontinuous windows rather than pretending samples are contiguous.
        slice_dt = dt[start:stop - 1]
        if np.any(slice_dt > 1.5 / FS_EEG):
            continue
        row = {"t_start": float(elapsed[start]), "t_end": float(elapsed[stop - 1])}
        for i, channel in enumerate(CH):
            f, pxx = welch(filtered[start:stop, i], fs=FS_EEG, nperseg=win)
            for band, (low, high) in BANDS.items():
                keep = (f >= low) & (f < high)
                row[f"{channel}_{band}"] = float(trapezoid(pxx[keep], f[keep]))
        rows.append(row)
    if not rows:
        raise CASSInputError("Tidak ada window EEG yang lolos penolakan artefak NB06.")
    return pd.DataFrame(rows), t[0], float(elapsed[-1]), warnings


def _windows(r0_end, duration):
    records = []
    for phase, low, high in (("PRE", 0.0, r0_end), ("POST", r0_end, duration)):
        t = low
        while t + WINDOW_S <= high + 1e-9:
            records.append({"window_id": len(records), "window_start": t,
                            "window_end": t + WINDOW_S, "window_mid": t + WINDOW_S / 2,
                            "phase": phase})
            t += STEP_S
    return records


def _num(x):
    x = float(x)
    return None if not np.isfinite(x) else round(x, 6)


def window_state(folder: Path, r0_end: float | None, rr_span_s: float = RR_SPAN_S):
    """Per-window EEG log(beta/alpha) per channel and Polar RR RMSSD, before normalisation.

    r0_end None = no marker, every window belongs to R0. Returns (state, duration_s, warnings).
    """
    folder = Path(folder)
    eeg_path, rr_path = folder / "muse_eeg.csv", folder / "polar_rr.csv"
    if not eeg_path.is_file() or not rr_path.is_file():
        raise CASSInputError("Dibutuhkan muse_eeg.csv dan polar_rr.csv pada sesi yang sama.")
    bp, eeg_start, duration, warnings = _bandpower(pd.read_csv(eeg_path))
    if r0_end is None:
        r0_end = duration  # no marker: the whole recording is R0
    elif r0_end + 5 > duration:
        raise CASSInputError(f"Rekaman {duration:.1f} s; R0 harus menyisakan >=5 s fase POST.")
    rr = read_rr(rr_path, eeg_start)
    if rr.empty:
        raise CASSInputError("polar_rr.csv tidak memiliki data RR.")
    rr_min = float(rr.time_s.min())
    rr_max = float(rr.time_s.max())
    session_meta = folder / "session.json"
    if session_meta.is_file():
        try:
            meta = json.loads(session_meta.read_text())
            if any(s.get("ok") for s in meta.get("sync", [])):
                warnings.append("Sinkronisasi akselerometer tersedia. Timestamp analisis memakai host clock bersama (offset 0); tinjau residual offset pada session.json.")
        except (OSError, ValueError, TypeError):
            warnings.append("Metadata session.json tidak dapat dibaca.")
    rows = []
    for w in _windows(float(r0_end), duration):
        overlap = bp[(bp.t_end > w["window_start"]) & (bp.t_start < w["window_end"])]
        if overlap.empty:
            continue
        row = dict(w)
        row["nb06_rows"] = int(len(overlap))
        for channel in CH:
            a = float(overlap[f"{channel}_alpha"].median())
            b = float(overlap[f"{channel}_beta"].median())
            row[f"{channel}_cortical_raw"] = np.log(b / a) if a > 0 and b > 0 else np.nan
        half = rr_span_s / 2
        lo, hi = w["window_mid"] - half, w["window_mid"] + half
        # CASS PRV-span patch clamps the window to available range.
        if lo < rr_min:
            lo, hi = rr_min, min(rr_max, rr_min + rr_span_s)
        if hi > rr_max:
            lo, hi = max(rr_min, rr_max - rr_span_s), rr_max
        rmssd, n_ibi, hr = hrv_window(rr, lo, hi, min_ibi=MIN_RR)
        row.update({"polar_t0": lo, "polar_t1": hi,
                    "polar_rr_rmssd": rmssd, "polar_n_ibi": n_ibi, "polar_hr": hr})
        rows.append(row)
    if not rows:
        raise CASSInputError("Tidak ada window CASS yang memiliki bandpower EEG.")
    return pd.DataFrame(rows), duration, warnings


def analyze(folder: str | Path, r0_end: float, rr_span_s: float = RR_SPAN_S) -> dict:
    folder = Path(folder)
    if not np.isfinite(r0_end) or r0_end < 10:
        raise CASSInputError("Akhir baseline R0 harus minimal 10 detik.")
    if rr_span_s <= 0 or rr_span_s > 300:
        raise CASSInputError("Rentang RR harus antara 0 dan 300 detik.")
    state, duration, warnings = window_state(folder, r0_end, rr_span_s)
    baseline = state.phase.eq("PRE")
    if not baseline.any():
        raise CASSInputError("Fase R0 tidak memiliki window EEG valid.")
    for ch in CH:
        column = f"{ch}_cortical_raw"
        loc, scale = _robust_location_scale(state.loc[baseline, column])
        state[f"{ch}_cortical_raw_z"] = (state[column] - loc) / scale
    zcols = [f"{ch}_cortical_raw_z" for ch in CH]
    state["cortical_state"] = state[zcols].mean(axis=1, skipna=True)
    # R0 reference for Y matches NB10's normalize_columns, with new Polar RR metric.
    loc, scale = _robust_location_scale(state.loc[baseline, "polar_rr_rmssd"])
    state["autonomic_state"] = (state.polar_rr_rmssd - loc) / scale if np.isfinite(loc) else np.nan
    state["autonomic_valid"] = np.isfinite(state.autonomic_state)
    state["distance_reference"] = np.hypot(state.cortical_state, state.autonomic_state)
    for ch in CH:
        state[f"{ch}_deviation"] = state[f"{ch}_cortical_raw_z"] - state.cortical_state
    state["channel_dispersion"] = state[zcols].std(axis=1, ddof=0)
    finite = np.isfinite(state.cortical_state) & np.isfinite(state.autonomic_state)
    state["quadrant"] = np.select(
        [finite & (state.cortical_state >= 0) & (state.autonomic_state >= 0),
         finite & (state.cortical_state < 0) & (state.autonomic_state >= 0),
         finite & (state.cortical_state < 0) & (state.autonomic_state < 0),
         finite & (state.cortical_state >= 0) & (state.autonomic_state < 0)],
        ["Q1", "Q2", "Q3", "Q4"], default="INVALID")
    valid_rows = state[finite]
    occupancy = {q: int((valid_rows.quadrant == q).sum()) for q in ("Q1", "Q2", "Q3", "Q4")}
    if state.polar_rr_rmssd.notna().sum() == 0:
        warnings.append("Tidak ada RMSSD Polar valid (minimal 8 RR pada rentang 20 s); sumbu Y dan kuadran tidak tersedia.")
    if not np.isfinite(loc):
        warnings.append("RMSSD Polar pada baseline R0 tidak valid; semua Y ditetapkan kosong, bukan nol.")
    windows = []
    for _, row in state.iterrows():
        windows.append({"t0": _num(row.window_start), "t1": _num(row.window_end),
                        "tm": _num(row.window_mid), "phase": row.phase,
                        "cortical": _num(row.cortical_state),
                        "autonomic": _num(row.autonomic_state),
                        "quadrant": row.quadrant,
                        "rmssd": _num(row.polar_rr_rmssd),
                        "n_ibi": int(row.polar_n_ibi),
                        "channels": {ch: _num(row[f"{ch}_cortical_raw_z"]) for ch in CH}})
    return {"session_id": folder.name,
            "autonomic_scalar": "polar_rr_rmssd", "cortical_metric": "log_beta_alpha",
            "method": {"eeg_fs_hz": FS_EEG, "eeg_filter": "notch50 Q30, 1-40 Hz Butterworth order4",
                       "eeg_bandpower": "Welch 4s / 2s, alpha 8-13, beta 13-30",
                       "cortical_window_s": WINDOW_S, "cortical_step_s": STEP_S,
                       "autonomic_span_s": rr_span_s, "min_rr_intervals": 8,
                       "rr_validity": "300–2000ms, consecutive plausible RR changes <=20%",
                       "normalization": "robust median/MAD R0 reference independently for EEG channels and Polar RMSSD",
                       "r0_end_s": float(r0_end), "rr_sync_offset_s": 0.0},
            "duration_s": _num(duration), "n_windows": len(windows),
            "n_valid": len(valid_rows), "occupancy": occupancy, "windows": windows,
            "warnings": warnings}


def state_csv(payload):
    """CSV for the exact current R0 parameter, not a different cached analysis."""
    import io
    f = io.StringIO()
    columns = ["tm", "phase", "cortical", "autonomic", "quadrant", "rmssd", "n_ibi", *CH]
    writer = __import__("csv").writer(f)
    writer.writerow(columns)
    for row in payload["windows"]:
        writer.writerow([row["tm"], row["phase"], row["cortical"], row["autonomic"],
                         row["quadrant"], row["rmssd"], row["n_ibi"],
                         *[row["channels"][ch] for ch in CH]])
    return f.getvalue()
