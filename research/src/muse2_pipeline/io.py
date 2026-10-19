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
RR_FILE = "polar_rr.csv"

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
            "has_polar": (folder / RR_FILE).exists(),
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
    return ", ".join(dict.fromkeys(f"{t:.0f}" for t in m["time_s"] if t > 0))  # same second once


def sync_offset(meta: dict) -> float | None:
    """Muse − Polar offset (s) from the first successful movement sync, if any."""
    good = [s for s in meta.get("sync") or [] if s.get("ok") and s.get("muse_minus_polar_s") is not None]
    return float(good[0]["muse_minus_polar_s"]) if good else None


def load_sample(folder: Path, legacy_bp: bool = True) -> dict:
    """Load one session. ``legacy_bp`` also computes the old per-window band power table ``bp``."""
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

    # Polar RR on the Muse time base: t_polar + (muse − polar offset), see musepolar README.
    rr_p = folder / RR_FILE
    rr = pd.read_csv(rr_p).dropna() if rr_p.exists() else pd.DataFrame(columns=["timestamp", "rr_ms"])
    offset = sync_offset(meta)
    rr["time_s"] = rr["timestamp"].astype(float) + (offset or 0.0) - t_origin

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
        "bp": bandpower_windows(eeg_f) if legacy_bp else None,
        "markers": markers,
        "rr": rr,
        "sync_offset": offset,
        "t_origin": t_origin,
        "meta": meta,
        "folder": folder,
    }


# --- any recording: musepolar session folder or EDF / EDF+ / BDF file -------------------

EDF_SUFFIXES = (".edf", ".bdf")


def _edf_files(root: Path) -> list[Path]:
    if root.is_file():
        return [root] if root.suffix.lower() in EDF_SUFFIXES else []
    return sorted(p for p in root.rglob("*") if p.suffix.lower() in EDF_SUFFIXES and p.is_file())


def list_recordings(root: Path) -> list[dict]:
    """musepolar session folders and EDF/BDF files under ``root`` (or ``root`` itself)."""
    from .edf import read_header
    from .montage import canonical

    root = Path(root)
    if not root.exists():
        return []
    out = []
    if root.is_dir():
        for r in list_samples(root).to_dict("records"):
            out.append({"kind": "musepolar", "path": r["folder"], "label": r["label"], "name": r["participant"],
                        "note": r["condition"], "start": r["start_iso"], "duration": r["duration_sec"],
                        "has_ppg": bool(r["has_ppg"]), "has_heart": bool(r["has_polar"]), "n_channels": 4})
    out += _csv_recordings(root)
    for p in _edf_files(root):
        try:
            h = read_header(p)
        except (OSError, ValueError):
            continue
        labels = h["labels"]
        n_eeg = len({c for c in (canonical(l) for l in labels) if c})
        up = [l.upper() for l in labels]
        out.append({
            "kind": "edf", "path": str(p), "label": p.name, "name": _edf_patient(h["patient"]) or p.stem,
            "note": h["recording"] if h["recording"] and not h["recording"].startswith("Startdate") else "",
            "start": h["start"].isoformat(timespec="seconds") if h["start"] else None,
            "duration": h["n_records"] * h["record_s"] if h["n_records"] > 0 else None,
            "has_ppg": any("PPG" in l or "PLETH" in l for l in up),
            "has_heart": any("ECG" in l or "EKG" in l for l in up),
            "n_channels": n_eeg,
        })
    return out


def _csv_recordings(root: Path) -> list[dict]:
    """Earlier-app folders (EEG_raw.csv) and stand-alone EEG CSV files (Mind Monitor, muselsl, OpenBCI, ...)."""
    from .csvload import describe

    out = []
    files = [root] if root.is_file() else sorted([*root.rglob("*.csv"), *root.rglob("*.txt")])
    session_dirs = {p.parent for p in files if p.name in (EEG_FILE, "EEG_raw.csv")}
    for p in files:
        if p.suffix.lower() not in (".csv", ".txt"):
            continue
        if p.name == "EEG_raw.csv":
            meta = {}
            for name in ("recording_metadata.json", "baseline_metadata.json"):
                if (p.parent / name).exists():
                    try:
                        meta = json.loads((p.parent / name).read_text())
                    except ValueError:
                        meta = {}
                    break
            out.append({"kind": "lsl", "path": str(p.parent), "label": f"{p.parent.parent.name} / {p.parent.name}",
                        "name": p.parent.parent.name, "note": p.parent.name, "start": meta.get("start_iso"),
                        "duration": meta.get("duration_sec"), "has_ppg": (p.parent / "PPG_raw.csv").exists(),
                        "has_heart": False, "n_channels": 4})
            continue
        if p.parent in session_dirs and not root.is_file():
            continue  # part of a musepolar / earlier-app session folder
        d = describe(p)
        if d:
            out.append({"kind": "csv", "path": str(p), "label": p.name, "name": p.stem, "note": "", "start": None,
                        "duration": None, "has_ppg": d["has_ppg"], "has_heart": d["has_heart"],
                        "n_channels": d["n_channels"]})
    return out


def _edf_patient(field: str) -> str:
    # EDF+: "code sex birthdate name" with X for unknown subfields
    parts = field.split()
    if len(parts) >= 4 and parts[1] in ("M", "F", "X"):
        name = " ".join(parts[3:]).replace("_", " ")
        return "" if name == "X" else name
    return field if field not in ("X", "") else ""


def load_recording(path: Path) -> dict:
    """Load a recording (see _load_any) and join Polar Sensor Logger files found next to it."""
    rec = _load_any(Path(path))
    rec.setdefault("abs_start", None)
    rec["polar_info"] = None
    if rec["kind"] != "musepolar":  # musepolar sessions carry their own Polar RR
        attach_polar(rec, Path(path).parent if Path(path).is_file() else Path(path))
    return rec


def attach_polar(rec: dict, folder: Path, sets: list[dict] | None = None) -> None:
    """Use the Polar recording that overlaps this EEG recording in clock time as its heart data.

    Without a clock time on the EEG side, a single Polar recording in the folder is aligned at the start.
    """
    from .polar import best_match, polar_sets_in

    sets = polar_sets_in(folder) if sets is None else sets
    if not sets:
        return
    dur = float(rec["eeg_f"]["time_s"].iloc[-1])
    s, aligned = best_match(sets, rec["abs_start"], dur), "clock"
    if s is None and rec["abs_start"] is None and len(sets) == 1:
        s, aligned = sets[0], "start"
    if s is None:
        return
    origin = rec["abs_start"] if aligned == "clock" else s["t_first"]
    rec["rr"] = pd.DataFrame({"time_s": s["t"] - origin, "rr_ms": s["rr_ms"]})
    rec["heart_name"] = "Polar H10"
    extra = pd.DataFrame([(t - origin, f"Polar: {lab}") for t, lab in s["markers"]], columns=["time_s", "label"])
    if len(extra):
        rec["markers"] = pd.concat([rec["markers"], extra], ignore_index=True).sort_values("time_s", ignore_index=True)
    rec["polar_info"] = {"name": s["name"], "source": s["source"], "aligned": aligned,
                         "start_diff_s": round(float(s["t_first"] - origin), 3)}


def _load_any(path: Path) -> dict:
    """Load a musepolar folder or an EDF/BDF file into one common structure.

    Keys: kind, participant, condition, channels, fs, eeg_f (time_s + filtered channels),
    ppg (time_s, PPG2), ppg_fs, rr (time_s, rr_ms), heart_name, markers (time_s, label),
    sync_offset, meta (incl. eeg_validation / ppg_validation), label.
    """
    path = Path(path)
    if path.is_dir() and not (path / EEG_FILE).exists() and (path / "EEG_raw.csv").exists():
        from .csvload import load_lsl_folder

        return {**load_lsl_folder(path), "folder": path}
    if path.is_file() and path.suffix.lower() in (".csv", ".txt"):
        from .csvload import read_csv_recording

        return {**read_csv_recording(path), "folder": path}
    if path.is_dir():
        s = load_sample(path, legacy_bp=False)
        return {**s, "kind": "musepolar", "channels": list(CH), "fs": FS_EEG, "ppg_fs": FS_PPG,
                "heart_name": "Polar RR", "label": path.name, "abs_start": s["t_origin"]}
    return _load_edf(path)


def _load_edf(path: Path) -> dict:
    from scipy.signal import resample_poly

    from .edf import read_edf, to_microvolt
    from .hrv import ecg_beats
    from .montage import canonical

    d = read_edf(path)
    eeg_sig, ecg, ppg = {}, None, None
    for lab, (fs, v) in d["signals"].items():
        c = canonical(lab)
        dim = d["dims"][d["labels"].index(lab)]
        up = lab.upper()
        if c and c not in eeg_sig:
            eeg_sig[c] = (fs, v * to_microvolt(dim))
        elif ecg is None and ("ECG" in up or "EKG" in up):
            ecg = (fs, v)
        elif ppg is None and ("PPG" in up or "PLETH" in up):
            ppg = (fs, v)
    if not eeg_sig:  # no 10-20 names: use every signal measured in (micro)volts
        for lab, (fs, v) in d["signals"].items():
            dim = d["dims"][d["labels"].index(lab)].upper()
            if dim in ("UV", "µV", "ΜV", "MV", "V") and lab not in eeg_sig:
                eeg_sig[lab.strip()] = (fs, v * to_microvolt(dim))
    if not eeg_sig:
        raise ValueError("tidak ada kanal EEG di file EDF ini")
    rates = [fs for fs, _ in eeg_sig.values()]
    fs = max(set(rates), key=rates.count)
    channels = list(eeg_sig)
    n = min(len(v) if f == fs else int(len(v) * fs / f) for f, v in eeg_sig.values())
    cols = {}
    for c, (f, v) in eeg_sig.items():
        if f != fs:
            up_, down = int(round(fs * 1000)), int(round(f * 1000))
            g = np.gcd(up_, down)
            v = resample_poly(v, up_ // g, down // g)
        cols[c] = v[:n]
    eeg = pd.DataFrame({"time_s": np.arange(n) / fs, **cols})
    eeg_f = filter_eeg(eeg, fs, channels)

    if ppg is not None:
        pfs, pv = ppg
        ppg_df = pd.DataFrame({"time_s": np.arange(len(pv)) / pfs, "PPG2": pv})
    else:
        pfs, ppg_df = FS_PPG, pd.DataFrame({"time_s": [], "PPG2": []})
    rr = pd.DataFrame({"time_s": [], "rr_ms": []})
    if ecg is not None:
        efs, ev = ecg
        tb = ecg_beats(ev, np.arange(len(ev)) / efs, efs)
        if len(tb) > 1:
            rr = pd.DataFrame({"time_s": tb[1:], "rr_ms": np.diff(tb) * 1000})
    markers = pd.DataFrame(d["annotations"], columns=["time_s", "label"]) if d["annotations"] \
        else pd.DataFrame({"time_s": [], "label": []})
    start = d["start"].isoformat(timespec="seconds") if d["start"] else None
    meta = {
        "name": _edf_patient(d["patient"]) or path.stem, "note": "", "start_local": start, "start_iso": start,
        "duration_sec": n / fs, "eeg_validation": {"status": "VALID", "rate_hz": fs},
        "ppg_validation": {"status": "VALID" if ppg is not None else "-", "rate_hz": pfs if ppg is not None else None},
        "edf": {"labels": d["labels"], "edfplus": d["edfplus"], "discontinuous": d["discontinuous"]},
    }
    return {
        "kind": "edf", "label": path.name, "participant": meta["name"], "condition": "",
        "channels": channels, "fs": fs, "eeg_f": eeg_f, "ppg": ppg_df, "ppg_fs": pfs, "rr": rr,
        "heart_name": "EKG (EDF)", "markers": markers, "sync_offset": None, "meta": meta, "folder": path,
        "abs_start": d["start"].timestamp() if d["start"] else None,  # EDF start is local clock time
    }
