from __future__ import annotations

from datetime import datetime
from pathlib import Path
import json
import pandas as pd

from .eeg import filter_eeg, bandpower_windows

EEG_MAP = {
    "Timestamp_LSL": "time",
    "EEG_TP9": "TP9",
    "EEG_AF7": "AF7",
    "EEG_AF8": "AF8",
    "EEG_TP10": "TP10",
}
PPG_MAP = {
    "Timestamp_LSL": "time",
    "PPG_1": "PPG1",
    "PPG_2": "PPG2",
    "PPG_3": "PPG3",
}
CH = ["TP9", "AF7", "AF8", "TP10"]


def _sid(part: str, cond: str, start_iso) -> str:
    try:
        st = datetime.fromisoformat(str(start_iso)).strftime("%Y%m%dT%H%M%S")
    except Exception:
        st = "unknown"
    return f"{part}__{cond}__{st}"


def list_samples(trials_root: Path) -> pd.DataFrame:
    rows = []
    root = Path(trials_root)
    if not root.exists():
        return pd.DataFrame()
    for part_dir in sorted(root.glob("P*")):
        if not part_dir.is_dir():
            continue
        for cond in ("experiment", "baseline"):
            folder = part_dir / cond
            eeg = folder / "EEG_raw.csv"
            ppg = folder / "PPG_raw.csv"
            if not eeg.exists() or not ppg.exists():
                continue
            meta_p = folder / "recording_metadata.json"
            if not meta_p.exists():
                meta_p = folder / "baseline_metadata.json"
            meta = {}
            if meta_p.exists():
                try:
                    meta = json.loads(meta_p.read_text())
                except Exception:
                    meta = {}
            rows.append({
                "label": f"{part_dir.name} / {cond}",
                "participant": part_dir.name,
                "condition": cond,
                "folder": str(folder),
                "start_iso": meta.get("start_iso"),
                "duration_sec": meta.get("duration_sec"),
            })
    if not rows:
        for eeg in root.rglob("EEG_raw.csv"):
            folder = eeg.parent
            if folder.name not in ("experiment", "baseline"):
                continue
            ppg = folder / "PPG_raw.csv"
            if not ppg.exists():
                continue
            part = folder.parent.name
            cond = folder.name
            if any(r["folder"] == str(folder) for r in rows):
                continue
            rows.append({
                "label": f"{part} / {cond}",
                "participant": part,
                "condition": cond,
                "folder": str(folder),
                "start_iso": None,
                "duration_sec": None,
            })
    return pd.DataFrame(rows)


def load_sample(folder: Path, processed_root: Path | None = None) -> dict:
    folder = Path(folder)
    part = folder.parent.name
    cond = folder.name
    eeg = pd.read_csv(folder / "EEG_raw.csv").rename(columns=EEG_MAP)
    ppg = pd.read_csv(folder / "PPG_raw.csv").rename(columns=PPG_MAP)
    eeg["time_s"] = eeg["time"] - eeg["time"].iloc[0]
    ppg["time_s"] = ppg["time"] - ppg["time"].iloc[0]
    eeg_f = filter_eeg(eeg)
    meta_p = folder / "recording_metadata.json"
    if not meta_p.exists():
        meta_p = folder / "baseline_metadata.json"
    meta = json.loads(meta_p.read_text()) if meta_p.exists() else {}
    sid = _sid(part, cond, meta.get("start_iso"))
    bp = None
    if processed_root is not None:
        cand = Path(processed_root) / sid / "eeg_bandpower.csv"
        if cand.exists():
            bp = pd.read_csv(cand)
    if bp is None:
        bp = bandpower_windows(eeg_f)
    return {
        "participant": part,
        "condition": cond,
        "sid": sid,
        "eeg_f": eeg_f,
        "ppg": ppg,
        "bp": bp,
        "meta": meta,
        "folder": folder,
    }
