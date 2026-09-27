"""Read sessions recorded by the musepolar dashboard.

A session is one folder ``recordings/<YYYYMMDD_HHMMSS>_<name>/`` containing
``muse_eeg.csv`` (timestamp, TP9, AF7, AF8, TP10), optionally ``muse_ppg.csv``
(timestamp, ambient, ir, red), ``marker.csv`` (timestamp, label) and
``session.json``.  All timestamps are Unix seconds on the same host clock.
"""

from __future__ import annotations

import json
import os
import tempfile
import zipfile
from io import BytesIO
from pathlib import Path

import numpy as np
import pandas as pd

from .eeg import filter_eeg, bandpower_windows, FS_EEG

CH = ["TP9", "AF7", "AF8", "TP10"]
FS_PPG = 64.0
# Muse PPG channels as named by musepolar -> names used by the analysis (PPG2 = infrared).
PPG_MAP = {"ambient": "PPG1", "ir": "PPG2", "red": "PPG3"}
EEG_FILE = "muse_eeg.csv"
PPG_FILE = "muse_ppg.csv"

# research/src/muse2_pipeline/io.py -> repository root / recordings
DEFAULT_RECORDINGS = Path(
    os.environ.get("MUSE2_RECORDINGS") or Path(__file__).resolve().parents[3] / "recordings"
)


def _read_meta(folder: Path) -> dict:
    p = folder / "session.json"
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _session_folders(root: Path) -> list[Path]:
    if (root / EEG_FILE).exists():
        return [root]
    hits = sorted(p.parent for p in root.glob(f"*/{EEG_FILE}"))
    if not hits:
        hits = sorted({p.parent for p in root.rglob(EEG_FILE)})
    return hits


def list_samples(root: Path) -> pd.DataFrame:
    """One row per session folder under ``root`` (or ``root`` itself if it is a session)."""
    root = Path(root)
    if not root.exists():
        return pd.DataFrame()
    rows = []
    for folder in _session_folders(root):
        meta = _read_meta(folder)
        rows.append({
            "label": folder.name,
            "participant": meta.get("name") or folder.name,
            "condition": meta.get("note") or "",
            "folder": str(folder),
            "start_iso": meta.get("start_local"),
            "duration_sec": meta.get("duration_sec"),
            "has_ppg": (folder / PPG_FILE).exists(),
        })
    return pd.DataFrame(rows)


def unpack_zip(data: bytes) -> Path:
    """Extract an uploaded ZIP of one or more session folders; returns a root for list_samples."""
    dest = Path(tempfile.mkdtemp(prefix="muse2_zip_")) / "unzip"
    dest.mkdir()
    with zipfile.ZipFile(BytesIO(data)) as zf:
        zf.extractall(dest)
    return dest


def _quality(ts: np.ndarray, nominal: float) -> dict:
    """VALID / WARNING / INVALID from the effective sample rate of a stream."""
    if len(ts) < 2 or ts[-1] <= ts[0]:
        return {"status": "-", "rate_hz": None}
    rate = (len(ts) - 1) / (ts[-1] - ts[0])
    ratio = rate / nominal
    status = "VALID" if ratio >= 0.9 else "WARNING" if ratio >= 0.5 else "INVALID"
    return {"status": status, "rate_hz": round(float(rate), 2)}


def marker_titik(markers: pd.DataFrame, skip_prefix: str = "SYNC") -> str:
    """Marker times (s from session start) as a 'Titik' string, ignoring sync markers."""
    if markers is None or not len(markers):
        return ""
    m = markers[~markers["label"].astype(str).str.startswith(skip_prefix)]
    return ", ".join(f"{t:.0f}" for t in m["time_s"] if t > 0)


def load_sample(folder: Path) -> dict:
    folder = Path(folder)
    meta = _read_meta(folder)

    eeg = pd.read_csv(folder / EEG_FILE).dropna(subset=CH).reset_index(drop=True)
    t_origin = float(eeg["timestamp"].iloc[0])
    eeg["time_s"] = eeg["timestamp"] - t_origin

    ppg_p = folder / PPG_FILE
    ppg = pd.read_csv(ppg_p) if ppg_p.exists() else pd.DataFrame(columns=["timestamp", *PPG_MAP])
    ppg = ppg.dropna(subset=list(PPG_MAP)).reset_index(drop=True)
    for src, dst in PPG_MAP.items():
        ppg[dst] = ppg[src].astype(float)
    # Same clock for both streams: PPG time is relative to the first EEG sample.
    ppg["time_s"] = ppg["timestamp"].astype(float) - t_origin

    mk_p = folder / "marker.csv"
    markers = pd.read_csv(mk_p) if mk_p.exists() else pd.DataFrame(columns=["timestamp", "label"])
    markers["time_s"] = markers["timestamp"].astype(float) - t_origin

    meta["eeg_validation"] = _quality(eeg["timestamp"].to_numpy(float), FS_EEG)
    meta["ppg_validation"] = _quality(ppg["timestamp"].to_numpy(float), FS_PPG)
    if not meta.get("start_iso"):
        meta["start_iso"] = meta.get("start_local")

    eeg_f = filter_eeg(eeg)
    return {
        "participant": meta.get("name") or folder.name,
        "condition": meta.get("note") or "",
        "sid": folder.name,
        "eeg_f": eeg_f,
        "ppg": ppg,
        "bp": bandpower_windows(eeg_f),
        "markers": markers,
        "meta": meta,
        "folder": folder,
    }
