"""CorVa Space v0.2 engine: one recorded session → labels per window and per protocol phase.

Pipeline (corva/MODEL.md, corva/DECISIONS.md):

1. ``cass_polar.engine.window_state`` gives per 5 s window (2.5 s step) the per-channel log(beta/alpha),
   log(theta/beta) and log(beta/(alpha+theta)) from Muse EEG (NB06 artifact rule, D-13) and RMSSD from
   Polar RR over a 20 s span.
2. Phases come from the "CorVa: <phase>" markers the dashboard writes (corva/protocol.py). Any CorVa
   marker, including "CorVa: selesai" / "CorVa: dihentikan", closes the phase before it.
3. R0 = the baseline phase after its settling minute. Every axis is a robust z (median, 1.4826 × MAD)
   against the R0 windows: X = mean channel z of log(beta/alpha) (D-09), Y = z of lnRMSSD (D-10),
   theta/beta z = mean channel z of log(theta/beta) (D-12).
4. Each window gets a label (descriptive trajectory). Each phase gets a label from the medians of its
   analysed windows (after settling), only when the data condition holds (D-11): >= 60 s valid RR and
   >= 40 s clean EEG; otherwise NO_DATA with the reason. R0 must meet the same condition.
5. The phase label is compared with the protocol expectation.

Every rule is tied to corva/references.json in EVIDENCE below, or declared an assumption.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from cass_polar.engine import CH, MIN_RR, RR_SPAN_S, CASSInputError, _robust_location_scale, window_state
from cass_polar.polar_adapter import RR_MAX_MS, RR_MIN_MS, hrv_window, read_rr

from . import conclusions, labels, protocol

MIN_EEG_S = 40.0  # D-11: clean EEG per analysed segment (gudmundsson2007)
MIN_RR_S = labels.MIN_RR_S  # D-11: valid RR per analysed segment (esco2014)
PROTOCOL_PHASE = "rest"  # every protocol block is seated rest -> resting reading (laborde2018)
BASELINE_ID = next(p["id"] for p in protocol.PROTOCOL if p["reference"])
RAW_KEYS = ("log_beta_alpha", "ln_rmssd")  # natural-unit axes for change from R0 and between sessions

EVIDENCE = {
    "r0_after_settle": {"refs": ["taskforce1996", "bourdillon2017"],
                        "basis": "R0 = fase baseline setelah menit stabilisasi (4 menit analisis), seperti rekaman HRV "
                                 "jangka pendek standar"},
    "min_eeg": {"refs": ["gudmundsson2007"],
                "basis": "label per fase hanya bila ruas analisis memiliki ≥ 40 s EEG bersih (D-11); EEG istirahat "
                         "stabil dengan epoch ≥ 40 s"},
    "window_rr_span": {"refs": ["munoz2015"],
                       "basis": "RMSSD per jendela dari rentang RR 20 s seperti CASS; RMSSD 10 s sudah r ≈ 0,85 terhadap "
                                "rekaman 5 menit, jadi titik per jendela dipakai untuk lintasan deskriptif"},
    "theta_band": {"refs": ["klimesch1999", "crabbe2004"],
                   "basis": "pita theta 4–8 Hz untuk penanda log(θ/β) Q3 (D-12); dipakai rasio, bukan theta absolut, "
                            "karena daya semua pita naik saat dan sesudah latihan"},
    "protocol_rest_reading": {"refs": ["laborde2018"],
                              "basis": "semua blok protokol adalah istirahat duduk, jadi bacaan kuadran memakai fase "
                                       "'istirahat' Vagal Tank Theory"},
    "phase_label_median": {"refs": [], "assumption": True,
                           "basis": "label per fase dari median z jendela yang dianalisis, okupansi sel sebagai keterangan; "
                                    "asumsi, diuji di validasi v0.5"},
    "eeg_artifact": {"refs": [], "assumption": True,
                     "basis": "artefak EEG seperti CASS/NB06: window 4 s ditolak bila > 20 % sampel melebihi 80 µV (D-13); "
                              "asumsi, diuji banding dengan potongan 2 s Research View di v0.5"},
}


def _num(v, nd: int = 4):
    return None if v is None or not np.isfinite(v) else round(float(v), nd)


def read_markers(folder: Path, eeg_start_unix: float) -> pd.DataFrame:
    """CorVa markers of the last protocol run, on the EEG time base: columns time_s, label, phase_id.

    phase_id is None for end markers ("CorVa: selesai", "CorVa: dihentikan"). A protocol restarted in the
    same recording starts at its last baseline marker.
    """
    path = Path(folder) / "marker.csv"
    empty = pd.DataFrame(columns=["time_s", "label", "phase_id"])
    if not path.is_file():
        return empty
    mk = pd.read_csv(path)
    if not {"timestamp", "label"} <= set(mk.columns):
        return empty
    mk = mk.dropna(subset=["timestamp", "label"])
    mk = mk[mk["label"].astype(str).str.startswith(protocol.MARKER_PREFIX)].copy()
    if mk.empty:
        return empty
    mk["time_s"] = pd.to_numeric(mk["timestamp"], errors="coerce") - eeg_start_unix
    mk["label"] = mk["label"].astype(str)
    mk["phase_id"] = [protocol.phase_from_marker(x) for x in mk["label"]]
    mk = mk.dropna(subset=["time_s"]).sort_values("time_s").reset_index(drop=True)
    starts = mk.index[mk["phase_id"] == BASELINE_ID]
    if len(starts):
        mk = mk.loc[starts[-1]:].reset_index(drop=True)
    mk["phase_id"] = mk["phase_id"].astype(object).where(mk["phase_id"].notna(), None)
    return mk[["time_s", "label", "phase_id"]]


def read_ratings(folder: Path, eeg_start_unix: float, run_start_s: float) -> dict:
    """Subjective ratings after each phase of the run that starts at run_start_s (D-22):
    {phase id: {"KSS": 7, "rileks": 6}} ({} = skipped). The last rating of a phase wins."""
    path = Path(folder) / "marker.csv"
    if not path.is_file():
        return {}
    mk = pd.read_csv(path)
    if not {"timestamp", "label"} <= set(mk.columns):
        return {}
    out = {}
    for t, label in zip(pd.to_numeric(mk["timestamp"], errors="coerce") - eeg_start_unix, mk["label"].astype(str)):
        parsed = protocol.parse_scale(label)
        if parsed and np.isfinite(t) and t >= run_start_s:
            out[parsed[0]] = parsed[1]
    return out


def phase_spans(markers: pd.DataFrame, duration: float) -> dict:
    """phase id -> {start, end, analysis_start, analysis_end, complete} from markers.

    A phase ends at the next CorVa marker, its planned length or the end of the recording, whichever
    comes first. The settling period (settle_s) is excluded from analysis.
    """
    spec = {p["id"]: p for p in protocol.PROTOCOL}
    spans = {}
    rows = markers.to_dict("records")
    for i, m in enumerate(rows):
        pid = m["phase_id"] if isinstance(m["phase_id"], str) else None  # None/NaN = end marker
        if pid is None or pid in spans:
            continue
        p = spec[pid]
        start = float(m["time_s"])
        nxt = float(rows[i + 1]["time_s"]) if i + 1 < len(rows) else np.inf
        end = min(start + p["seconds"], nxt, duration)
        spans[pid] = {"start": start, "end": end, "analysis_start": start + p["settle_s"],
                      "analysis_end": end, "complete": end >= start + p["seconds"] - 1.0}
    return spans


def valid_rr_seconds(rr: pd.DataFrame, start: float, end: float) -> float:
    """Seconds covered by valid NN intervals in [start, end): 300–2000 ms and <= 20 % change from the
    previous interval (same rule as cass_polar.polar_adapter.hrv_window)."""
    r = rr[(rr.time_s >= start) & (rr.time_s < end)]
    v = r.rr_ms.to_numpy(dtype=float)
    if not len(v):
        return 0.0
    ok = (v >= RR_MIN_MS) & (v <= RR_MAX_MS)
    ok[1:] &= ok[:-1] & (np.abs(np.diff(v)) <= 0.20 * v[:-1])
    return float(v[ok].sum() / 1000.0)


def clean_eeg_seconds(intervals, start: float, end: float) -> float:
    """Length of the union of clean NB06 EEG windows clipped to [start, end)."""
    clipped = sorted((max(a, start), min(b, end)) for a, b in intervals if b > start and a < end)
    total, cur_a, cur_b = 0.0, None, None
    for a, b in clipped:
        if cur_b is None or a > cur_b:
            if cur_b is not None:
                total += cur_b - cur_a
            cur_a, cur_b = a, b
        else:
            cur_b = max(cur_b, b)
    if cur_b is not None:
        total += cur_b - cur_a
    return float(total)


def _robust_z(values: pd.Series, ref: pd.Series) -> pd.Series:
    loc, scale = _robust_location_scale(ref)
    if not np.isfinite(loc):
        return pd.Series(np.nan, index=values.index)
    return (values - loc) / scale


def _channel_mean_z(state: pd.DataFrame, suffix: str, ref: pd.Series) -> pd.Series:
    zs = pd.concat([_robust_z(state[f"{ch}_{suffix}"], state.loc[ref, f"{ch}_{suffix}"]) for ch in CH], axis=1)
    return zs.mean(axis=1, skipna=True)


def _data_check(rr_s: float, eeg_s: float) -> list[str]:
    reasons = []
    if rr_s < MIN_RR_S:
        reasons.append(f"RR valid {rr_s:.0f} s < {MIN_RR_S:.0f} s")
    if eeg_s < MIN_EEG_S:
        reasons.append(f"EEG bersih {eeg_s:.0f} s < {MIN_EEG_S:.0f} s")
    return reasons


def analyze_session(folder: str | Path, rr_span_s: float = RR_SPAN_S) -> dict:
    """CorVa labels for one musepolar session folder recorded with the standard protocol."""
    folder = Path(folder)
    state, duration, warnings = window_state(folder, None, rr_span_s)
    eeg_start = state.attrs["eeg_start_unix"]
    eeg_windows = state.attrs["eeg_clean_windows"]
    markers = read_markers(folder, eeg_start)
    spans = phase_spans(markers, duration)
    if BASELINE_ID not in spans:
        raise CASSInputError(f"Penanda '{protocol.marker_label(BASELINE_ID)}' tidak ditemukan; "
                             "rekam sesi dengan panel Protokol CorVa.")
    rr = read_rr(folder / "polar_rr.csv", eeg_start)
    ratings = read_ratings(folder, eeg_start, float(markers["time_s"].iloc[0]))

    # phase membership of each window: fully inside the phase; analysed = after settling with its RR span
    # inside the phase as well, so the 20 s RR span does not reach into the next phase
    state["corva_phase"] = None
    state["analysed"] = False
    for pid, sp in spans.items():
        inside = (state.window_start >= sp["start"]) & (state.window_end <= sp["end"])
        state.loc[inside, "corva_phase"] = pid
        state.loc[inside & (state.window_start >= sp["analysis_start"]) & (state.polar_t0 >= sp["start"])
                  & (state.polar_t1 <= sp["end"]), "analysed"] = True
    ref = state["analysed"] & state["corva_phase"].eq(BASELINE_ID)

    state["ln_rmssd"] = np.log(state["polar_rr_rmssd"].where(state["polar_rr_rmssd"] > 0))
    state["x_z"] = _channel_mean_z(state, "cortical_raw", ref)
    state["y_z"] = _robust_z(state["ln_rmssd"], state.loc[ref, "ln_rmssd"])
    state["theta_beta_z"] = _channel_mean_z(state, "theta_beta_raw", ref)
    state["engagement_z"] = _channel_mean_z(state, "engagement_raw", ref)
    # raw log(beta/alpha), channel mean: phase change from R0 in natural units, comparable between sessions (D-19)
    state["log_beta_alpha"] = state[[f"{ch}_cortical_raw" for ch in CH]].mean(axis=1, skipna=True)

    windows = []
    for _, w in state.iterrows():
        pid = w["corva_phase"]
        lab = labels.classify(w["x_z"], w["y_z"], PROTOCOL_PHASE if pid else None, w["theta_beta_z"])
        windows.append({"t0": _num(w.window_start, 3), "t1": _num(w.window_end, 3), "tm": _num(w.window_mid, 3),
                        "phase_id": pid, "analysed": bool(w["analysed"]),
                        "x_z": _num(w["x_z"]), "y_z": _num(w["y_z"]),
                        "theta_beta_z": _num(w["theta_beta_z"]), "engagement_z": _num(w["engagement_z"]),
                        "rmssd_ms": _num(w["polar_rr_rmssd"], 2), "ln_rmssd": _num(w["ln_rmssd"]),
                        "n_ibi": int(w["polar_n_ibi"]), "code": lab["code"], "label": lab["label"]})

    sp0 = spans[BASELINE_ID]
    r0_rr = valid_rr_seconds(rr, sp0["analysis_start"], sp0["analysis_end"])
    r0_eeg = clean_eeg_seconds(eeg_windows, sp0["analysis_start"], sp0["analysis_end"])
    r0_reasons = _data_check(r0_rr, r0_eeg)
    r0 = {"phase_id": BASELINE_ID, "start": _num(sp0["analysis_start"], 2), "end": _num(sp0["analysis_end"], 2),
          "n_windows": int(ref.sum()), "rr_valid_s": round(r0_rr, 1), "eeg_clean_s": round(r0_eeg, 1),
          "adequate": not r0_reasons, "reasons": r0_reasons,
          "ln_rmssd_median": _num(state.loc[ref, "ln_rmssd"].median()),
          "raw": {k: _num(state.loc[ref, k].median()) for k in RAW_KEYS},
          "raw_scale": {k: _num(_robust_location_scale(state.loc[ref, k])[1]) for k in RAW_KEYS}}
    if r0_reasons:
        warnings.append("R0 tidak memenuhi syarat data (" + "; ".join(r0_reasons) + "); semua label fase = Data kurang.")

    phases = []
    for p in protocol.PROTOCOL:
        pid = p["id"]
        entry = {"id": pid, "name": p["name"], "expected": p["expected"], "reference": p["reference"],
                 "expected_refs": protocol.EXPECTATION_REFS[pid], "recorded": pid in spans,
                 "subjective": ratings.get(pid)}
        if pid not in spans:
            lab = labels.classify(None, None)
            entry.update({"label": lab, "comparison": None, "reasons": ["fase tidak direkam"], "adequate": False})
            phases.append(entry)
            continue
        sp = spans[pid]
        sel = state["analysed"] & state["corva_phase"].eq(pid)
        rr_s = valid_rr_seconds(rr, sp["analysis_start"], sp["analysis_end"])
        eeg_s = clean_eeg_seconds(eeg_windows, sp["analysis_start"], sp["analysis_end"])
        reasons = _data_check(rr_s, eeg_s) + (["R0 tidak memenuhi syarat"] if r0_reasons else [])
        med = {k: float(state.loc[sel, k].median()) if sel.any() else np.nan
               for k in ("x_z", "y_z", "theta_beta_z", "engagement_z")}
        if reasons:
            lab = labels.classify(None, None)
        else:
            lab = labels.classify(med["x_z"], med["y_z"], PROTOCOL_PHASE, med["theta_beta_z"])
        codes = [w["code"] for w, s in zip(windows, sel) if s]
        valid_codes = [c for c in codes if c != labels.NO_DATA[0]]
        occupancy = {c: round(valid_codes.count(c) / len(valid_codes), 3) for c in sorted(set(valid_codes))}
        seg_rmssd = hrv_window(rr, sp["analysis_start"], sp["analysis_end"], min_ibi=MIN_RR)[0]
        raw = {k: float(state.loc[sel, k].median()) if sel.any() else np.nan for k in RAW_KEYS}
        delta = {k: raw[k] - r0["raw"][k] if r0["raw"][k] is not None and not reasons else np.nan for k in RAW_KEYS}
        if p["reference"]:
            comparison = "acuan (R0)"
        else:
            comparison = protocol.compare(pid, lab["code"])
        entry.update({
            "start": _num(sp["start"], 2), "end": _num(sp["end"], 2),
            "analysis_start": _num(sp["analysis_start"], 2), "analysis_end": _num(sp["analysis_end"], 2),
            "complete": sp["complete"],
            "medians": {k: _num(v) for k, v in med.items()},
            "raw": {k: _num(v) for k, v in raw.items()}, "delta": {k: _num(v) for k, v in delta.items()},
            "label": lab, "comparison": comparison, "adequate": not reasons, "reasons": reasons,
            "data": {"n_windows": len(codes), "n_valid": len(valid_codes),
                     "valid_fraction": round(len(valid_codes) / len(codes), 3) if codes else 0.0,
                     "rr_valid_s": round(rr_s, 1), "eeg_clean_s": round(eeg_s, 1),
                     "analysis_s": round(max(0.0, sp["analysis_end"] - sp["analysis_start"]), 1)},
            "occupancy": occupancy,
            "segment_rmssd_ms": _num(seg_rmssd, 2),
            "segment_ln_rmssd": _num(np.log(seg_rmssd)) if np.isfinite(seg_rmssd) and seg_rmssd > 0 else None,
        })
        if not sp["complete"]:
            warnings.append(f"Fase '{p['name']}' lebih pendek dari rencana ({sp['end'] - sp['start']:.0f} s).")
        phases.append(entry)

    compared = [ph for ph in phases if ph["comparison"] in ("sesuai harapan", "berbeda dari harapan")]
    result = {
        "session_id": folder.name, "version": "0.4.1",
        "method": {"x": "z log(beta/alpha), mean of TP9/AF7/AF8/TP10 (D-09)",
                   "y": "z lnRMSSD Polar RR (D-10)", "q3_marker": "z log(theta/beta) >= threshold (D-12)",
                   "comparison_x": "z log(beta/(alpha+theta)), not used for labels (D-09)",
                   "threshold_z": labels.THRESHOLD_Z, "min_rr_s": MIN_RR_S, "min_eeg_s": MIN_EEG_S,
                   "rr_span_s": rr_span_s, "window_s": float(state.window_end.iloc[0] - state.window_start.iloc[0]),
                   "normalization": "robust median / 1.4826 MAD against R0 (baseline after settling)",
                   "eeg_artifact": "NB06: 4 s window rejected when > 20 % samples exceed 80 µV (D-13)",
                   "protocol_phase_reading": PROTOCOL_PHASE},
        "duration_s": _num(duration, 2),
        "markers": [{"time_s": _num(m["time_s"], 2), "label": m["label"],
                     "phase_id": m["phase_id"] if isinstance(m["phase_id"], str) else None}
                    for m in markers.to_dict("records")],
        "r0": r0, "phases": phases, "windows": windows,
        "summary": {"n_compared": len(compared),
                    "n_as_expected": sum(ph["comparison"] == "sesuai harapan" for ph in compared)},
        "warnings": warnings,
    }
    result["conclusions"] = conclusions.conclude(result)
    return result


PHASE_COLUMNS = ["id", "name", "recorded", "start", "end", "analysis_start", "analysis_end", "complete",
                 "code", "label", "phase_reading", "qualifier", "expected", "comparison", "adequate", "reasons",
                 "x_z", "y_z", "theta_beta_z", "engagement_z", "x_magnitude", "y_magnitude",
                 "n_windows", "n_valid", "valid_fraction", "rr_valid_s", "eeg_clean_s", "analysis_s",
                 "segment_rmssd_ms", "segment_ln_rmssd", "occupancy", "kss", "rileks", "refs"]
WINDOW_COLUMNS = ["t0", "t1", "tm", "phase_id", "analysed", "x_z", "y_z", "theta_beta_z", "engagement_z",
                  "rmssd_ms", "ln_rmssd", "n_ibi", "code", "label"]


def _csv(rows, columns) -> str:
    import csv
    import io

    f = io.StringIO()
    w = csv.writer(f)
    w.writerow(columns)
    for r in rows:
        w.writerow(["" if r.get(c) is None else r.get(c) for c in columns])
    return f.getvalue()


def phases_csv(result: dict) -> str:
    """One row per protocol phase: label, comparison, medians and data coverage."""
    rows = []
    for p in result["phases"]:
        lab, data, med = p["label"], p.get("data", {}), p.get("medians", {})
        rows.append({**{k: p.get(k) for k in ("id", "name", "recorded", "start", "end", "analysis_start",
                                              "analysis_end", "complete", "comparison", "adequate")},
                     "code": lab["code"], "label": lab["label"], "phase_reading": lab["phase_reading"],
                     "qualifier": lab["qualifier"], "x_magnitude": lab["x_magnitude"], "y_magnitude": lab["y_magnitude"],
                     "expected": " | ".join(p["expected"]), "reasons": " | ".join(p["reasons"]),
                     **med, **data,
                     "segment_rmssd_ms": p.get("segment_rmssd_ms"), "segment_ln_rmssd": p.get("segment_ln_rmssd"),
                     "occupancy": " ".join(f"{c}={v}" for c, v in p.get("occupancy", {}).items()),
                     "kss": (p.get("subjective") or {}).get("KSS"), "rileks": (p.get("subjective") or {}).get("rileks"),
                     "refs": " ".join(lab["refs"])})
    return _csv(rows, PHASE_COLUMNS)


def windows_csv(result: dict) -> str:
    """One row per 5 s window (all windows, settling included, see 'analysed')."""
    return _csv(result["windows"], WINDOW_COLUMNS)


def main() -> None:
    import argparse
    import json

    ap = argparse.ArgumentParser(description="CorVa Space labels for a session recorded with the standard protocol")
    ap.add_argument("folder")
    ap.add_argument("--windows", action="store_true", help="include per-window labels in the output")
    args = ap.parse_args()
    out = analyze_session(args.folder)
    if not args.windows:
        out.pop("windows")
    print(json.dumps(out, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
