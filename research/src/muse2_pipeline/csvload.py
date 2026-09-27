"""EEG recordings stored as CSV text files (other than musepolar session folders).

Recognised layouts (all handled by one reader that looks at the header):

- Mind Monitor (Muse app): ``TimeStamp`` date-time, ``RAW_TP9 … RAW_TP10``, markers in ``Elements``
- muselsl / Muse LSL: ``timestamps, TP9, AF7, AF8, TP10``
- the earlier research app: ``EEG_raw.csv`` (``Timestamp_LSL, EEG_TP9 …``) + optional ``PPG_raw.csv``
- OpenBCI GUI: ``%`` comment header with ``Sample Rate = 250 Hz``, ``EXG Channel 0..15``
- any CSV with a time column and channels named after 10-20 / 10-10 electrodes, plus optional
  ECG/EKG, PPG and marker/event columns

Values are taken as microvolts. The sample rate comes from the header comment when present,
otherwise from the median step of the time column; samples are placed on an even grid at that
rate (as the musepolar recorder does). The browser version (web/engine.js) implements the same rules.
"""

from __future__ import annotations

import io
import json
import re
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

from .eeg import filter_eeg
from .montage import canonical

TIME_NAMES = ["timestamp", "timestamps", "timestamp_lsl", "time", "time_s", "time (s)", "t", "timestamp (s)"]
MARKER_NAMES = ["marker", "markers", "label", "event", "events", "annotation", "annotations", "elements"]
IGNORED_ELEMENTS = ("/muse/elements/blink", "/muse/elements/jaw_clench", "/muse/elements/touching_forehead",
                    "/muse/elements/horseshoe", "/muse/elements/is_good")
MIN_FS = 100.0
DEFAULT_FS = 256.0


def _eeg_name(col: str) -> str | None:
    c = col.strip()
    c = re.sub(r"^(RAW|EEG)[_ ]", "", c, flags=re.I)
    return canonical(c)


def _raw_channel(col: str) -> bool:
    return bool(re.match(r"^(EXG\s*Channel\s*\d+|CH(ANNEL)?[\s_]*\d+|EEG[\s_]*\d+)$", col.strip(), flags=re.I))


def split_header(text: str) -> tuple[list[str], str]:
    """Leading comment lines ('%' or '#') and the remaining CSV text."""
    lines = text.splitlines()
    i = 0
    while i < len(lines) and (lines[i].startswith("%") or lines[i].startswith("#") or not lines[i].strip()):
        i += 1
    return lines[:i], "\n".join(lines[i:])


def header_rate(comments: list[str]) -> float | None:
    for ln in comments:
        m = re.search(r"sample\s*rate\s*[=:]\s*([\d.]+)", ln, flags=re.I)
        if m:
            return float(m.group(1))
    return None


STANDARD_RATES = (128, 200, 250, 256, 500, 512, 1000, 1024, 2048)


def estimate_rate(t: np.ndarray) -> float:
    """Average rate over the whole time span, snapped to a standard rate when within 3 %.

    (Timestamps rounded to milliseconds or a few dropped samples would otherwise give 250 instead of 256.)
    """
    r = (len(t) - 1) / (t[-1] - t[0])
    near = min(STANDARD_RATES, key=lambda s: abs(s - r))
    return float(near) if abs(near - r) <= 0.03 * near else float(round(r))


def detect_sep(line: str) -> str:
    return max([",", ";", "\t"], key=line.count)


def numeric_unit(name: str, t: np.ndarray) -> float:
    """Divisor that turns a numeric time column into seconds (1 or 1000).

    Order: the column name ('ms' / '(s)', '_s', 'sec'), then epoch size (13-digit = ms,
    10-digit = s), then whichever reading gives a plausible EEG rate (100-5000 Hz).
    """
    n = name.lower()
    if re.search(r"(^|[^a-z])ms([^a-z]|$)|millis", n):
        return 1000.0
    if re.search(r"\(s\)|_s$|\bsec", n):
        return 1.0
    f = t[np.isfinite(t)]
    if len(f) < 2:
        return 1.0
    big = np.nanmax(np.abs(f))
    if big > 1e11:
        return 1000.0
    if big > 1e8:
        return 1.0
    span = f[-1] - f[0]
    if span <= 0:
        return 1.0
    rate_s = (len(f) - 1) / span
    return 1000.0 if rate_s < 50 and 100 <= rate_s * 1000 <= 5000 else 1.0


def to_seconds(values: pd.Series, name: str = "") -> np.ndarray | None:
    """Time column as seconds (numbers in s or ms, or date-time strings); None if unusable."""
    num = pd.to_numeric(values, errors="coerce")
    if num.notna().mean() > 0.9:
        t = num.to_numpy(float)
        return t / numeric_unit(name, t)
    dt = pd.to_datetime(values.astype(str).str.strip().replace({"": None}), errors="coerce")
    if dt.notna().mean() > 0.9:
        return (dt - dt.dropna().iloc[0]).dt.total_seconds().to_numpy(float)
    return None


def describe(path: Path) -> dict | None:
    """Cheap look at a CSV file: None if it has no EEG columns."""
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            head = "".join(f.readline() for _ in range(60))
    except OSError:
        return None
    comments, rest = split_header(head)
    first = rest.splitlines()[0] if rest else ""
    cols = [c.strip().strip('"') for c in first.split(detect_sep(first))]
    eeg = [c for c in cols if _eeg_name(c)]
    raw = [c for c in cols if _raw_channel(c)]
    if not eeg and not raw:
        return None
    up = [c.upper() for c in cols]
    return {"n_channels": len({_eeg_name(c) for c in eeg}) if eeg else len(raw),
            "has_ppg": any("PPG" in c or "PLETH" in c for c in up),
            "has_heart": any("ECG" in c or "EKG" in c for c in up)}


def read_csv_recording(path: Path) -> dict:
    """Load one EEG CSV file into the common recording structure (see io.load_recording)."""
    path = Path(path)
    text = path.read_text(encoding="utf-8", errors="replace")
    comments, body = split_header(text)
    if not body.strip():
        raise ValueError("file CSV kosong")
    sep = detect_sep(body.splitlines()[0])
    df = pd.read_csv(io.StringIO(body), sep=sep, low_memory=False)
    df.columns = [str(c).strip() for c in df.columns]
    return from_table(df, path.name, path.stem, header_rate(comments))


def from_table(df: pd.DataFrame, label: str, stem: str, rate: float | None = None, ppg_df: pd.DataFrame | None = None,
               meta: dict | None = None) -> dict:
    cols = list(df.columns)
    low = {c.lower(): c for c in cols}
    tcol = next((low[n] for n in TIME_NAMES if n in low), None) or \
        next((c for c in cols if "timestamp" in c.lower() or c.lower().startswith("time")), None)
    eeg_cols = {}
    for c in cols:
        name = _eeg_name(c)
        if name and name not in eeg_cols:
            eeg_cols[name] = c
    if not eeg_cols:
        eeg_cols = {c: c for c in cols if _raw_channel(c)}
    if not eeg_cols:
        raise ValueError("tidak ada kolom EEG (nama 10-20 seperti TP9/AF7/Fp1, RAW_TP9, EEG_TP9 atau EXG Channel)")
    mcol = next((low[n] for n in MARKER_NAMES if n in low), None)
    ecg_col = next((c for c in cols if re.search(r"ECG|EKG", c, flags=re.I)), None)
    ppg_col = next((c for c in cols if re.search(r"PPG|PLETH", c, flags=re.I)), None)

    t_all = to_seconds(df[tcol], tcol) if tcol else None
    start_dt = None
    if tcol is not None and pd.to_numeric(df[tcol], errors="coerce").notna().mean() <= 0.9:
        first = pd.to_datetime(df[tcol].astype(str).str.strip(), errors="coerce").dropna()
        start_dt = first.iloc[0].isoformat(timespec="seconds") if len(first) else None
    markers = []
    if mcol is not None and t_all is not None:
        for t, lab in zip(t_all, df[mcol]):
            s = str(lab).strip()
            if s and s.lower() != "nan" and np.isfinite(t) and not s.lower().startswith(IGNORED_ELEMENTS):
                markers.append((float(t), s))

    x = df[list(eeg_cols.values())].apply(pd.to_numeric, errors="coerce")
    keep = x.notna().all(axis=1).to_numpy()
    x = x[keep].to_numpy(float)
    if len(x) < 10:
        raise ValueError("terlalu sedikit baris EEG")
    t = t_all[keep] if t_all is not None else None
    note = ""
    if rate:
        fs = float(rate)
    elif t is not None and len(t) > 2 and t[-1] > t[0]:
        fs = estimate_rate(t)
    else:
        fs, note = DEFAULT_FS, f"frekuensi sampel tidak diketahui, dianggap {DEFAULT_FS:.0f} Hz"
    if fs < MIN_FS:
        raise ValueError(f"frekuensi sampel {fs:g} Hz terlalu rendah untuk analisis EEG (minimal {MIN_FS:.0f} Hz); "
                         "rekam dengan data mentah (mis. Mind Monitor: Recording Interval = Constant)")
    t0 = float(t[0]) if t is not None else 0.0
    channels = list(eeg_cols)
    n = len(x)
    eeg = pd.DataFrame({"time_s": np.arange(n) / fs, **{c: x[:, k] for k, c in enumerate(channels)}})
    eeg_f = filter_eeg(eeg, fs, channels)
    quality = {"status": "VALID", "rate_hz": fs}
    if t is not None and n > 2 and t[-1] > t[0]:
        ratio = (n - 1) / (t[-1] - t[0]) / fs
        quality = {"status": "VALID" if ratio >= 0.9 else "WARNING" if ratio >= 0.5 else "INVALID",
                   "rate_hz": round((n - 1) / (t[-1] - t[0]), 2)}

    ppg = pd.DataFrame({"time_s": [], "PPG2": []})
    pfs = 64.0
    if ppg_df is not None:
        ppg, pfs = ppg_df
    elif ppg_col is not None:
        v = pd.to_numeric(df.loc[keep, ppg_col], errors="coerce").to_numpy(float)
        ok = np.isfinite(v)
        ppg, pfs = pd.DataFrame({"time_s": np.arange(n)[ok] / fs, "PPG2": v[ok]}), fs
    rr = pd.DataFrame({"time_s": [], "rr_ms": []})
    if ecg_col is not None:
        from .hrv import ecg_beats

        v = pd.to_numeric(df.loc[keep, ecg_col], errors="coerce").to_numpy(float)
        v = np.nan_to_num(v, nan=np.nanmedian(v) if np.isfinite(v).any() else 0.0)
        tb = ecg_beats(v, np.arange(n) / fs, fs)
        if len(tb) > 1:
            rr = pd.DataFrame({"time_s": tb[1:], "rr_ms": np.diff(tb) * 1000})
    meta = dict(meta or {})
    start = meta.get("start_iso") or start_dt
    meta.update({"name": meta.get("name") or stem, "start_local": start, "start_iso": start, "duration_sec": n / fs,
                 "eeg_validation": quality, "csv_note": note,
                 "ppg_validation": {"status": "VALID" if len(ppg) else "-", "rate_hz": pfs if len(ppg) else None}})
    return {
        "kind": "csv", "label": label, "participant": meta["name"], "condition": meta.get("note", ""),
        "channels": channels, "fs": fs, "eeg_f": eeg_f, "ppg": ppg, "ppg_fs": pfs, "rr": rr, "heart_name": "EKG (CSV)",
        "markers": pd.DataFrame([(tt - t0, s) for tt, s in markers], columns=["time_s", "label"]) if markers
        else pd.DataFrame({"time_s": [], "label": []}),
        "sync_offset": None, "meta": meta, "folder": None,
    }


def load_lsl_folder(folder: Path) -> dict:
    """The earlier research app layout: EEG_raw.csv (+ PPG_raw.csv, recording_metadata.json)."""
    folder = Path(folder)
    df = pd.read_csv(folder / "EEG_raw.csv")
    df.columns = [str(c).strip() for c in df.columns]
    meta = {}
    for name in ("recording_metadata.json", "baseline_metadata.json"):
        if (folder / name).exists():
            try:
                meta = json.loads((folder / name).read_text())
            except ValueError:
                meta = {}
            break
    ppg = None
    if (folder / "PPG_raw.csv").exists():
        p = pd.read_csv(folder / "PPG_raw.csv")
        te = to_seconds(df["Timestamp_LSL"], "Timestamp_LSL") if "Timestamp_LSL" in df else None
        tp = to_seconds(p["Timestamp_LSL"], "Timestamp_LSL") if "Timestamp_LSL" in p else None
        if tp is not None and "PPG_2" in p:
            origin = te[0] if te is not None else tp[0]
            ppg = (pd.DataFrame({"time_s": tp - origin, "PPG2": p["PPG_2"].to_numpy(float)}), 64.0)
    label = f"{folder.parent.name} / {folder.name}"
    rec = from_table(df, label, folder.parent.name, ppg_df=ppg,
                     meta={"name": folder.parent.name, "note": folder.name, "start_iso": meta.get("start_iso")})
    rec["kind"] = "lsl"
    return rec

