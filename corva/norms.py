"""Reference-group norms for CorVa responses (D-19c, D-24).

Norms are percentiles of each phase's change from R0 in natural units (Δ log(β/α), Δ lnRMSSD), computed by
``python -m corva.validate --norms-out`` from a reference group and kept in the private research repository.
The dashboard reads them with ``python -m musepolar --corva-norms <file>``; this public repository holds only
the code. A person's response is then placed as a percentile of the reference group, i.e. in magnitude, not
only in direction.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

KEYS = ("log_beta_alpha", "ln_rmssd")
PERCENTILES = (5, 10, 25, 50, 75, 90, 95)
MIN_N = 20  # below this the norms are flagged as provisional (assumption, D-24)
FORMAT = "corva-norms/1"


def build(rows: list[dict]) -> dict:
    """Norms from rows {"participant", "phase_id", "log_beta_alpha", "ln_rmssd"} (one session per participant)."""
    phases: dict = {}
    for pid in sorted({r["phase_id"] for r in rows}):
        entry = {}
        for k in KEYS:
            vals = np.array([r[k] for r in rows if r["phase_id"] == pid and r.get(k) is not None], dtype=float)
            vals = vals[np.isfinite(vals)]
            if len(vals):
                entry[k] = {"n": int(len(vals)),
                            "percentiles": {str(q): round(float(np.percentile(vals, q)), 5) for q in PERCENTILES}}
        if entry:
            phases[pid] = entry
    n = len({r["participant"] for r in rows})
    return {"format": FORMAT, "n_participants": n, "provisional": n < MIN_N, "keys": list(KEYS),
            "description": "Persentil perubahan dari R0 per fase (satuan asli), satu sesi per peserta.", "phases": phases}


def load(path: str | Path) -> dict:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if data.get("format") != FORMAT:
        raise ValueError(f"{path}: bukan berkas norma CorVa ({FORMAT})")
    return data


def percentile_of(value: float, entry: dict) -> float | None:
    """Approximate percentile of value within a norm entry, by linear interpolation between the stored
    percentiles (clamped to 1–99 outside the stored range)."""
    if value is None or not np.isfinite(value):
        return None
    qs = np.array(PERCENTILES, dtype=float)
    vs = np.array([entry["percentiles"][str(q)] for q in PERCENTILES], dtype=float)
    if value <= vs[0]:
        return 1.0 if value < vs[0] else float(qs[0])
    if value >= vs[-1]:
        return 99.0 if value > vs[-1] else float(qs[-1])
    return round(float(np.interp(value, vs, qs)), 1)


def annotate(result: dict, norms: dict | None) -> dict:
    """Add p["norms"] = {key: {"percentile", "n"}} to every phase with a change from R0, and result["norms"]."""
    if not norms:
        return result
    for p in result["phases"]:
        entry = norms["phases"].get(p["id"])
        if not entry or not p.get("delta"):
            continue
        p["norms"] = {k: {"percentile": percentile_of(p["delta"].get(k), entry[k]), "n": entry[k]["n"]}
                      for k in KEYS if k in entry}
    result["norms"] = {"n_participants": norms["n_participants"], "provisional": norms["provisional"]}
    return result


EVIDENCE = {
    "norms_percentiles": {"refs": [], "assumption": True,
                          "basis": "norma = persentil empiris perubahan dari R0 per fase, satu sesi per peserta, dari kelompok "
                                   "acuan; posisi seseorang = persentil hasil interpolasi; N < 20 ditandai sementara (D-24)"},
}
