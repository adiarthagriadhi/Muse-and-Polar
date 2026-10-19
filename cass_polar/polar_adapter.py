"""CASS Polar H10 adapter: preserve NB06 cortical X, replace PPG-derived Y with ECG RR HRV.

Input is an existing NB10 cass_state CSV plus Muse-Polar polar_rr.csv.
No PPG-to-HRV substitution; RR timing and validity are explicitly recorded.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import numpy as np
import pandas as pd

METRIC = "polar_rr_rmssd"
RR_MIN_MS, RR_MAX_MS = 300.0, 2000.0

def robust_scale(values):
    x = np.asarray(values, dtype=float)
    x = x[np.isfinite(x)]
    if not len(x):
        return np.nan, np.nan
    center = float(np.median(x))
    mad = float(1.4826 * np.median(np.abs(x - center)))
    scale = mad if mad > 0 else float(np.std(x, ddof=1)) if len(x) > 1 else 0
    return center, scale if np.isfinite(scale) and scale > 0 else 1.0

def read_rr(path, muse_start, offset_s=0.0):
    """RR timestamps are Unix seconds on the shared host clock.
    offset_s is Muse-minus-Polar clock correction, applied ONLY if validated.
    Each timestamp labels the end of its corresponding RR interval.
    """
    rr = pd.read_csv(path)
    if not {"timestamp", "rr_ms"}.issubset(rr.columns):
        raise ValueError("polar_rr.csv needs timestamp and rr_ms")
    rr = rr[["timestamp", "rr_ms"]].apply(pd.to_numeric, errors="coerce").dropna()
    rr = rr.sort_values("timestamp").drop_duplicates("timestamp").copy()
    rr["time_s"] = rr["timestamp"] + float(offset_s) - float(muse_start)
    return rr

def hrv_window(rr, start, end, min_ibi=8):
    """RMSSD only across consecutive plausible NN intervals; no gap bridging.
    Adjacent NN must be 300..2000 ms, and change <=20% of previous NN.
    """
    r = rr[(rr.time_s >= start) & (rr.time_s < end)]
    v = r.rr_ms.to_numpy(dtype=float)
    valid = (v >= RR_MIN_MS) & (v <= RR_MAX_MS)
    if len(v) < min_ibi or valid.sum() < min_ibi:
        return np.nan, int(valid.sum()), np.nan
    pair = valid[1:] & valid[:-1]
    pair &= np.abs(np.diff(v)) <= .20 * v[:-1]
    if not pair.any():
        return np.nan, int(valid.sum()), np.nan
    diffs = np.diff(v)[pair]
    return float(np.sqrt(np.mean(diffs ** 2))), int(valid.sum()), float(60000 / np.median(v[valid]))

def convert(state_path, rr_path, eeg_path, output_path, span_s=20., min_ibi=8, offset_s=0., metadata_path=None):
    if span_s <= 0 or min_ibi < 2:
        raise ValueError("span_s must be positive and min_ibi >= 2")
    state = pd.read_csv(state_path)
    required = {"window_mid", "phase", "cortical_state"}
    if not required.issubset(state.columns):
        raise ValueError(f"cass_state lacks {sorted(required-set(state.columns))}")
    eeg = pd.read_csv(eeg_path, usecols=["timestamp"])
    if eeg.empty:
        raise ValueError("muse_eeg.csv is empty")
    muse_start = float(eeg.timestamp.iloc[0])
    rr = read_rr(rr_path, muse_start, offset_s)
    # Reference must be the initial R0/PRE interval; do not silently normalize against POST.
    baseline = state.phase.eq("PRE")
    if not baseline.any():
        raise ValueError("No PRE/R0 windows")
    t_min = 0.
    t_max = float(rr.time_s.max()) if len(rr) else 0.
    results = []
    for mid in state.window_mid.to_numpy(dtype=float):
        a, b = mid-span_s/2, mid+span_s/2
        if a < t_min:
            a, b = t_min, min(t_max, t_min+span_s)
        if b > t_max:
            a, b = max(t_min, t_max-span_s), t_max
        rmssd, count, hr = hrv_window(rr, a, b, min_ibi)
        results.append((a,b,rmssd,count,hr))
    state[["polar_t0","polar_t1",METRIC,"polar_n_ibi","polar_hr"]] = pd.DataFrame(results,index=state.index)
    center, scale = robust_scale(state.loc[baseline, METRIC])
    if not np.isfinite(center):
        state["autonomic_state"] = np.nan
    else:
        # Match the CASS convention: R0 center; scale over entire valid session.
        _, scale = robust_scale(state[METRIC])
        state["autonomic_state"] = (state[METRIC] - center) / scale
    state["autonomic_valid"] = np.isfinite(state["autonomic_state"])
    x, y = state.cortical_state, state.autonomic_state
    state["distance_reference"] = np.hypot(x, y)
    state["quadrant"] = np.select(
        [~state.autonomic_valid | ~np.isfinite(x),
         (x>=0)&(y>=0),(x<0)&(y>=0),(x<0)&(y<0)],
        ["", "Q1", "Q2", "Q3"], default="Q4")
    # Remove old PPG metrics so the exported CSV cannot masquerade as PPG analysis.
    state = state.drop(columns=[c for c in state if c.startswith("ppg2_") or c.startswith("prv_")])
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    state.to_csv(output_path,index=False)
    provenance = {"autonomic_scalar":METRIC,"autonomic_source":"Polar H10 BLE RR (ECG-derived)",
                  "rr_source":str(rr_path),"eeg_source":str(eeg_path),
                  "cortical_source":str(state_path),"span_s":span_s,
                  "min_ibi":min_ibi,"offset_s":offset_s,
                  "rr_timestamp_semantics":"interval_end_unix_seconds",
                  "quality_rule":"300..2000ms, adjacent change <=20%, consecutive valid pairs",
                  "normalization":"R0 median, full-session robust scale",
                  "valid_y_windows":int(state.autonomic_valid.sum()),
                  "total_windows":len(state)}
    if metadata_path:
        provenance["recording_metadata"]=str(metadata_path)
    output_path.with_suffix(".provenance.json").write_text(json.dumps(provenance,indent=2))
    return provenance

def main():
    p=argparse.ArgumentParser(description="Replace CASS autonomic Y with Polar H10 RR-derived RMSSD")
    p.add_argument("--state",required=True,help="Existing NB10 cass_state_*.csv")
    p.add_argument("--rr",required=True,help="Muse-Polar polar_rr.csv")
    p.add_argument("--eeg",required=True,help="Muse-Polar muse_eeg.csv (clock anchor)")
    p.add_argument("--output",required=True)
    p.add_argument("--span",type=float,default=20.)
    p.add_argument("--min-ibi",type=int,default=8)
    p.add_argument("--offset-s",type=float,default=0.,help="Validated Muse-minus-Polar offset only")
    args=p.parse_args()
    print(json.dumps(convert(args.state,args.rr,args.eeg,args.output,args.span,args.min_ibi,args.offset_s),indent=2))
if __name__=="__main__":
    main()
