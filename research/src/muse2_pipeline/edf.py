"""Minimal EDF / EDF+ / BDF reader (no external dependency).

Reads every signal as physical values, the EDF+ annotations (used as markers), the
patient/recording fields and the start time. EDF+D (discontinuous) files are read as if
contiguous; the header says so in ``meta['discontinuous']``.
"""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

import numpy as np

UNIT_TO_UV = {"UV": 1.0, "µV": 1.0, "ΜV": 1.0, "MICROV": 1.0, "MV": 1000.0, "V": 1e6, "NV": 1e-3}


def _txt(b: bytes) -> str:
    return b.decode("latin-1").strip()


def _num(b: bytes, default=0.0) -> float:
    try:
        return float(_txt(b))
    except ValueError:
        return default


def read_header(path: Path) -> dict:
    with open(path, "rb") as f:
        h = f.read(256)
        if len(h) < 256:
            raise ValueError("bukan file EDF (header terlalu pendek)")
        bdf = h[0:1] == b"\xff"
        ns = int(_num(h[252:256]))
        if ns <= 0 or ns > 1024:
            raise ValueError("bukan file EDF (jumlah sinyal tidak wajar)")
        sh = f.read(ns * 256)

    def field(offset, width):
        start = offset * ns
        return [sh[start + i * width:start + (i + 1) * width] for i in range(ns)]

    labels = [_txt(x) for x in field(0, 16)]
    o = 16 + 80
    dims = [_txt(x) for x in field(o, 8)]
    pmin = [_num(x) for x in field(o + 8, 8)]
    pmax = [_num(x) for x in field(o + 16, 8)]
    dmin = [_num(x) for x in field(o + 24, 8)]
    dmax = [_num(x) for x in field(o + 32, 8)]
    nsamp = [int(_num(x)) for x in field(o + 40 + 80, 8)]
    reserved = _txt(h[192:236])
    start = None
    try:
        d, t = _txt(h[168:176]), _txt(h[176:184])
        dd, mm, yy = (int(x) for x in d.split("."))
        start = datetime(2000 + yy if yy < 85 else 1900 + yy, mm, dd, *(int(x) for x in t.split(".")))
    except (ValueError, TypeError):
        pass
    return {
        "bdf": bdf, "ns": ns, "labels": labels, "dims": dims, "pmin": pmin, "pmax": pmax,
        "dmin": dmin, "dmax": dmax, "nsamp": nsamp, "n_records": int(_num(h[236:244], -1)),
        "record_s": _num(h[244:252], 1.0) or 1.0, "header_bytes": int(_num(h[184:192])),
        "patient": _txt(h[8:88]), "recording": _txt(h[88:168]), "start": start,
        "edfplus": reserved.startswith("EDF+"), "discontinuous": reserved.startswith("EDF+D"),
    }


def _parse_tal(raw: bytes) -> list[tuple[float, str]]:
    out = []
    for tal in raw.split(b"\x00"):
        if not tal or tal[:1] not in (b"+", b"-"):
            continue
        parts = tal.split(b"\x14")
        onset = parts[0].split(b"\x15")[0]
        try:
            t = float(onset.decode("latin-1"))
        except ValueError:
            continue
        for txt in parts[1:]:
            s = txt.decode("utf-8", "replace").strip()
            if s:
                out.append((t, s))
    return out


def read_edf(path: Path) -> dict:
    """Returns header fields plus ``signals`` {label: (fs, physical values)} and ``annotations``."""
    path = Path(path)
    hd = read_header(path)
    bps = 3 if hd["bdf"] else 2
    rec_samples = sum(hd["nsamp"])
    rec_bytes = rec_samples * bps
    size = path.stat().st_size - hd["header_bytes"]
    n_rec = size // rec_bytes if rec_bytes else 0
    if hd["n_records"] > 0:
        n_rec = min(n_rec, hd["n_records"])
    with open(path, "rb") as f:
        f.seek(hd["header_bytes"])
        raw = f.read(n_rec * rec_bytes)
    if hd["bdf"]:
        b = np.frombuffer(raw, np.uint8).reshape(-1, 3).astype(np.int32)
        dig = b[:, 0] | (b[:, 1] << 8) | (b[:, 2] << 16)
        dig = np.where(dig >= 1 << 23, dig - (1 << 24), dig).reshape(n_rec, rec_samples)
    else:
        dig = np.frombuffer(raw, "<i2").reshape(n_rec, rec_samples)
    signals, annotations = {}, []
    off = 0
    for i, lab in enumerate(hd["labels"]):
        n = hd["nsamp"][i]
        block = dig[:, off:off + n]
        off += n
        if lab.upper().replace("+", "").startswith("EDF ANNOTATION") or lab.upper().startswith("BDF ANNOTATION"):
            raw_ann = _bdf_bytes(block) if hd["bdf"] else np.ascontiguousarray(block).astype("<i2").tobytes()
            annotations += _parse_tal(raw_ann)
            continue
        span_d = hd["dmax"][i] - hd["dmin"][i] or 1.0
        gain = (hd["pmax"][i] - hd["pmin"][i]) / span_d
        phys = (block.reshape(-1).astype(float) - hd["dmin"][i]) * gain + hd["pmin"][i]
        signals[lab] = (n / hd["record_s"], phys)
    # the first annotation of each record is its time stamp (empty text) - already skipped
    return {**hd, "signals": signals, "annotations": sorted(set(annotations)), "n_rec": n_rec}


def _bdf_bytes(block: np.ndarray) -> bytes:
    v = block.reshape(-1).astype(np.int64) & 0xFFFFFF
    out = np.empty((len(v), 3), np.uint8)
    out[:, 0], out[:, 1], out[:, 2] = v & 0xFF, (v >> 8) & 0xFF, (v >> 16) & 0xFF
    return out.tobytes()


def to_microvolt(dim: str) -> float:
    d = re.sub(r"\s", "", dim or "").upper()
    return UNIT_TO_UV.get(d, 1.0)


def write_edf(path: Path, signals: dict[str, tuple[float, np.ndarray]], annotations=(), record_s: float = 1.0,
              start: datetime | None = None, patient: str = "X", dims: dict | None = None) -> None:
    """Small EDF+C writer (used by the tests and for exporting synthetic data)."""
    start = start or datetime(2026, 9, 26, 9, 30, 0)
    labels = list(signals)
    n_rec = int(min(len(v) / (fs * record_s) for fs, v in signals.values()))
    nsamp = [int(round(signals[l][0] * record_s)) for l in labels]
    tal_bytes = 120
    ann = sorted(annotations)
    all_labels = labels + ["EDF Annotations"]
    all_n = nsamp + [tal_bytes // 2]
    pmin, pmax = [], []
    for l in labels:
        v = signals[l][1][: n_rec * nsamp[labels.index(l)]]
        lo, hi = float(np.min(v)), float(np.max(v))
        if hi - lo < 1e-9:
            hi = lo + 1
        pmin.append(lo); pmax.append(hi)
    pmin.append(-1); pmax.append(1)
    ns = len(all_labels)

    def f(s, w):
        return str(s)[:w].ljust(w).encode("latin-1")

    hdr = (f("0", 8) + f(patient, 80) + f("Startdate X X X X", 80) + f(start.strftime("%d.%m.%y"), 8)
           + f(start.strftime("%H.%M.%S"), 8) + f(256 + ns * 256, 8) + f("EDF+C", 44) + f(n_rec, 8)
           + f(record_s, 8) + f(ns, 4))
    dims = dims or {}
    hdr += b"".join(f(l, 16) for l in all_labels) + b"".join(f("", 80) for _ in all_labels)
    hdr += b"".join(f(dims.get(l, "uV") if l in signals else "", 8) for l in all_labels)
    hdr += b"".join(f(f"{v:.6g}", 8) for v in pmin) + b"".join(f(f"{v:.6g}", 8) for v in pmax)
    hdr += b"".join(f(-32768, 8) for _ in all_labels) + b"".join(f(32767, 8) for _ in all_labels)
    hdr += b"".join(f("", 80) for _ in all_labels) + b"".join(f(n, 8) for n in all_n)
    hdr += b"".join(f("", 32) for _ in all_labels)
    body = bytearray()
    for r in range(n_rec):
        for j, l in enumerate(labels):
            v = signals[l][1][r * nsamp[j]:(r + 1) * nsamp[j]]
            d = np.round((v - pmin[j]) / (pmax[j] - pmin[j]) * 65535 - 32768).clip(-32768, 32767).astype("<i2")
            body += d.tobytes()
        t0 = r * record_s
        tal = f"+{t0:g}\x14\x14\x00".encode()
        for t, txt in ann:
            if t0 <= t < t0 + record_s:
                tal += f"+{t:g}\x14{txt}\x14\x00".encode()
        body += tal[:tal_bytes].ljust(tal_bytes, b"\x00")
    Path(path).write_bytes(hdr + bytes(body))
