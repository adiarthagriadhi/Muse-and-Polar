"""Polar Sensor Logger (Android app) text files, joined to an EEG recording by clock time.

The app writes one ``;``-separated file per stream, e.g.
``Polar_H10_ABCD1234_20260920_081500_RR.txt`` with ``Phone timestamp;RR-interval [ms]``,
``..._ECG.txt`` with ``Phone timestamp;sensor timestamp [ns];timestamp [ms];ecg [uV]``,
``..._HR.txt`` and ``..._ACC.txt`` (ignored) and ``..._MARKER.txt``. Phone timestamps are local
ISO date-times. RR intervals are used directly (H10 beat timing); ECG is used only when there is
no RR file (R peaks are then detected). The browser version (web/engine.js) uses the same rules.
"""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

import numpy as np

TYPES = ("RR", "ECG", "HR", "ACC", "PPI", "MARKER")


def is_polar_file(path: Path) -> bool:
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            head = f.readline()
    except OSError:
        return False
    return "phone timestamp" in head.lower()


def stream_type(name: str, header: str) -> str | None:
    m = re.search(r"_(RR|ECG|HR|ACC|PPI|MARKER)\.txt$", name, flags=re.I)
    if m:
        return m.group(1).upper()
    h = header.lower()
    if "rr-interval" in h or re.search(r"\brr\b", h):
        return "RR"
    if "ecg" in h:
        return "ECG"
    if "marker" in h:
        return "MARKER"
    return None


def set_key(name: str) -> str:
    """Files of one recording share the name up to the stream suffix."""
    return re.sub(r"_(RR|ECG|HR|ACC|PPI|MARKER)\.txt$", "", name, flags=re.I)


def local_epoch(s: str) -> float:
    """Local ISO date-time ('2026-09-20T08:15:00.123' or with a space) -> Unix seconds (local time zone)."""
    return datetime.fromisoformat(s.strip().replace(" ", "T")).timestamp()


def _rows(text: str):
    lines = [ln for ln in text.splitlines() if ln.strip()]
    sep = ";" if lines[0].count(";") >= lines[0].count(",") else ","
    head = [c.strip().lower() for c in lines[0].split(sep)]
    return head, [ln.split(sep) for ln in lines[1:]]


def parse_rr(text: str) -> dict:
    """Beat times (Unix s, end of each interval) and RR (ms)."""
    head, rows = _rows(text)
    ti = head.index("phone timestamp")
    ri = next(i for i, c in enumerate(head) if "rr" in c)
    ts, rr = [], []
    for r in rows:
        try:
            ts.append(local_epoch(r[ti]))
            rr.append(float(r[ri]))
        except (ValueError, IndexError):
            continue
    ts, rr = np.array(ts), np.array(rr)
    # several intervals arrive in one packet with the same phone time: that time is the last beat
    t = ts.copy()
    for i in range(len(t) - 2, -1, -1):
        if ts[i] == ts[i + 1]:
            t[i] = t[i + 1] - rr[i + 1] / 1000.0
    return {"t": t, "rr_ms": rr}


def parse_ecg(text: str) -> dict:
    """ECG samples (µV) with Unix times from the sensor clock anchored to the first phone time."""
    head, rows = _rows(text)
    ti = head.index("phone timestamp")
    si = next((i for i, c in enumerate(head) if "sensor timestamp" in c), None)
    vi = next(i for i, c in enumerate(head) if "ecg" in c)
    t0, sens, v = None, [], []
    for r in rows:
        try:
            if t0 is None:
                t0 = local_epoch(r[ti])
            sens.append(float(r[si]) if si is not None else np.nan)
            v.append(float(r[vi]))
        except (ValueError, IndexError):
            continue
    v = np.array(v)
    sens = np.array(sens)
    if si is not None and np.isfinite(sens).all() and len(sens) > 1:
        t = t0 + (sens - sens[0]) / 1e9
        fs = (len(t) - 1) / (t[-1] - t[0]) if t[-1] > t[0] else 130.0
    else:
        fs = 130.0
        t = t0 + np.arange(len(v)) / fs
    return {"t": t, "v": v, "fs": float(fs)}


def parse_markers(text: str) -> list[tuple[float, str]]:
    head, rows = _rows(text)
    ti = head.index("phone timestamp")
    out = []
    for r in rows:
        try:
            out.append((local_epoch(r[ti]), ";".join(x for j, x in enumerate(r) if j != ti).strip() or "marker"))
        except (ValueError, IndexError):
            continue
    return out


def load_polar_set(files: dict[str, str]) -> dict | None:
    """{stream type: file text} -> {'t': beat times (Unix s), 'rr_ms', 'markers', 'source', 't_first', 't_last'}."""
    from .hrv import ecg_beats

    if "RR" in files:
        rr = parse_rr(files["RR"])
        source = "RR"
    elif "ECG" in files:
        e = parse_ecg(files["ECG"])
        tb = ecg_beats(e["v"], e["t"], e["fs"])
        if len(tb) < 2:
            return None
        rr = {"t": tb[1:], "rr_ms": np.diff(tb) * 1000}
        source = "ECG"
    else:
        return None
    if len(rr["t"]) < 2:
        return None
    return {"t": rr["t"], "rr_ms": rr["rr_ms"], "source": source,
            "markers": parse_markers(files["MARKER"]) if "MARKER" in files else [],
            "t_first": float(rr["t"][0] - rr["rr_ms"][0] / 1000), "t_last": float(rr["t"][-1])}


def polar_sets_in(folder: Path) -> list[dict]:
    """All Polar Sensor Logger recordings (grouped by file prefix) in a folder and below."""
    groups: dict[str, dict[str, str]] = {}
    for p in sorted(Path(folder).rglob("*.txt")) if Path(folder).is_dir() else []:
        if not is_polar_file(p):
            continue
        text = p.read_text(encoding="utf-8", errors="replace")
        typ = stream_type(p.name, text.splitlines()[0])
        if typ in ("RR", "ECG", "MARKER"):
            groups.setdefault(str(p.parent / set_key(p.name)), {})[typ] = text
    out = []
    for key, files in groups.items():
        s = load_polar_set(files)
        if s:
            s["name"] = Path(key).name
            out.append(s)
    return out


def best_match(sets: list[dict], abs_start: float | None, duration: float) -> dict | None:
    """The Polar recording overlapping the EEG time span the most."""
    if abs_start is None or not sets:
        return None
    best, best_ov = None, 0.0
    for s in sets:
        ov = min(abs_start + duration, s["t_last"]) - max(abs_start, s["t_first"])
        if ov > best_ov:
            best, best_ov = s, ov
    return best
