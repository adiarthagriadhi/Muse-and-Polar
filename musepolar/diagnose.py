"""Technical diagnosis of Muse–Polar synchronisation in recorded sessions.

    python -m musepolar.diagnose recordings/20261101_093000_xxx [more folders ...]

Reads only timestamps, Polar ``sensor_ns``, the accelerometer columns inside the
recorded sync windows, ``session.json`` and the ``SYNC`` marker labels.  Prints
numbers only (rates, gaps, timestamp shifts, correlation results): no EEG, PPG,
ECG, HR or RR values and no name / note, so the output can be shared.

What it shows:

* ``polar_host_shift``: Polar host timestamps minus the strap's own clock
  (``sensor_ns``), relative to its lower envelope.  With correct timestamps this
  stays within Bluetooth jitter (tens of ms).  Steps of several hundred ms that
  do not come back are the v1.0.0 ``SampleClock`` fault (fixed in 1.0.1).
* ``last_stamp_after_stop_s``: the last sample of a stream stamped later than
  the moment recording stopped is impossible with correct timestamps.
* ``syncs``: every recorded sync window re-analysed with the v1.0.0 rule
  (±1 s) and with a wide search (±``--wide`` s).  A clear peak outside ±1 s
  means the jumps were there but the timestamps were shifted.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

import numpy as np

from .analysis import estimate_offset


def _read_columns(path: Path, cols: list[str], t_range: tuple[float, float] | None = None) -> dict | None:
    """Read selected numeric columns of a recorder CSV (optionally only rows inside a time range)."""
    if not path.exists():
        return None
    out: dict[str, list[float]] = {c: [] for c in cols}
    with open(path, newline="", encoding="utf-8") as f:
        r = csv.reader(f)
        header = next(r, None)
        if not header:
            return None
        idx = [header.index(c) for c in cols if c in header]
        if len(idx) != len(cols):
            return None
        it = header.index("timestamp")
        for row in r:
            try:
                if t_range is not None:
                    t = float(row[it])
                    if t < t_range[0] or t > t_range[1]:
                        continue
                for c, i in zip(cols, idx):
                    out[c].append(float(row[i]))
            except (ValueError, IndexError):
                continue
    return {c: np.asarray(v) for c, v in out.items()}


def _rolling_min(t: np.ndarray, y: np.ndarray, window: float) -> np.ndarray:
    """Lower envelope: minimum of y over the trailing and leading ``window``/2 seconds."""
    out = np.empty_like(y)
    j0 = j1 = 0
    n = len(t)
    for i in range(n):
        while t[j0] < t[i] - window / 2:
            j0 += 1
        while j1 < n and t[j1] <= t[i] + window / 2:
            j1 += 1
        out[i] = y[j0:j1].min()
    return out


def stream_timing(ts: np.ndarray, nominal: float, end_unix: float | None) -> dict:
    if len(ts) < 2:
        return {"n": int(len(ts))}
    d = np.diff(ts)
    span = float(ts[-1] - ts[0])
    res = {
        "n": int(len(ts)),
        "span_s": round(span, 3),
        "rate_from_stamps_hz": round((len(ts) - 1) / span, 3) if span > 0 else None,
        "nominal_hz": nominal,
        "max_gap_s": round(float(d.max()), 3),
        "gaps_over_0_25_s": int(np.sum(d > 0.25)),
        "backwards_steps": int(np.sum(d <= 0)),
    }
    if end_unix:
        res["last_stamp_after_stop_s"] = round(float(ts[-1] - end_unix), 3)
    return res


def polar_shift(ts: np.ndarray, sensor_ns: np.ndarray, window: float = 60.0) -> dict:
    """Host timestamps against the Polar strap clock (true sample times up to drift)."""
    ok = np.isfinite(sensor_ns) & (sensor_ns > 0)
    ts, s = ts[ok], sensor_ns[ok] * 1e-9
    if len(ts) < 100:
        return {}
    # remove the strap/host rate difference with a robust line through the lower envelope
    k = max(1, len(ts) // 2000)
    ts_d, s_d = ts[::k], s[::k]
    resid = ts_d - s_d
    env = _rolling_min(ts_d, resid, window)
    shift = resid - env
    # steps: sustained shift (median over 5 s) above 0.2 s
    med = np.array([np.median(shift[max(0, i - 25):i + 25]) for i in range(len(shift))])
    return {
        "median_ms": round(float(np.median(shift)) * 1000, 1),
        "p95_ms": round(float(np.percentile(shift, 95)) * 1000, 1),
        "max_sustained_ms": round(float(med.max()) * 1000, 1),
        "share_time_shift_over_200ms": round(float(np.mean(med > 0.2)), 3),
        "strap_vs_host_ppm": round(float(np.polyfit(s_d - s_d[0], env, 1)[0]) * 1e6, 1) if len(s_d) > 10 else None,
    }


def analyse_sync_window(folder: Path, t0: float, t1: float, wide: float) -> dict:
    pad = wide + 1.0
    m = _read_columns(folder / "muse_acc.csv", ["timestamp", "x", "y", "z"], (t0 - pad, t1 + pad))
    p = _read_columns(folder / "polar_acc.csv", ["timestamp", "x", "y", "z"], (t0 - pad, t1 + pad))
    if m is None or p is None:
        return {"error": "muse_acc.csv / polar_acc.csv tidak ada"}
    out: dict = {"start_unix": t0, "n_muse": int(np.sum((m["timestamp"] >= t0) & (m["timestamp"] <= t1))),
                 "n_polar": int(np.sum((p["timestamp"] >= t0) & (p["timestamp"] <= t1)))}

    def run(lo, hi, max_lag):
        sm = (m["timestamp"] >= lo) & (m["timestamp"] <= hi)
        sp = (p["timestamp"] >= lo) & (p["timestamp"] <= hi)
        mx = np.stack([m["x"], m["y"], m["z"]], 1)[sm]
        px = np.stack([p["x"], p["y"], p["z"]], 1)[sp]
        r = estimate_offset(m["timestamp"][sm], mx, p["timestamp"][sp], px, max_lag=max_lag)
        return {k: (round(v, 4) if isinstance(v, float) else v) for k, v in r.items()}

    r1 = run(t0, t1, 1.0)
    r1["ok_rule_v1_0_0"] = bool(r1.get("correlation", 0) >= 0.5 and min(r1.get("events_a", 0), r1.get("events_b", 0)) >= 2)
    out["v1_0_0_window_1s"] = r1
    out["v1_0_1_window_3s"] = run(t0, t1, 3.0)
    out[f"wide_{wide:g}s"] = run(t0 - wide, t1 + wide, wide)
    return out


def diagnose(folder: Path, wide: float = 8.0) -> dict:
    folder = Path(folder)
    meta = json.loads((folder / "session.json").read_text(encoding="utf-8"))
    end = meta.get("end_unix")
    rep: dict = {
        "folder": "_".join(folder.name.split("_")[:2]),  # date_time only; the rest may be a participant code
        "duration_sec": meta.get("duration_sec"),
        "effective_rate_hz": meta.get("effective_rate_hz"),
        "samples": meta.get("samples"),
        "device_names": {k: (v or {}).get("name") for k, v in (meta.get("devices") or {}).items()},
        "sync_in_session_json": meta.get("sync"),
        "sync_drift_ms_per_hour": meta.get("sync_drift_ms_per_hour"),
    }
    markers = _read_marker_labels(folder / "marker.csv")
    rep["sync_markers"] = markers
    timing = {}
    for stream, nominal in (("muse_acc", 52), ("muse_eeg", 256), ("muse_ppg", 64), ("polar_acc", 200), ("polar_ecg", 130)):
        c = _read_columns(folder / f"{stream}.csv", ["timestamp"])
        if c is not None:
            timing[stream] = stream_timing(c["timestamp"], nominal, end)
    rep["timing"] = timing
    for stream in ("polar_acc", "polar_ecg"):
        c = _read_columns(folder / f"{stream}.csv", ["timestamp", "sensor_ns"])
        if c is not None and len(c["timestamp"]):
            rep.setdefault("polar_host_shift", {})[stream] = polar_shift(c["timestamp"], c["sensor_ns"])
    windows = [(s["start_unix"], s["end_unix"]) for s in (meta.get("sync") or []) if "start_unix" in s]
    if not windows:  # sync result missing from session.json: fall back to the markers
        starts = [t for t, lab in markers if lab.startswith("SYNC mulai")]
        windows = [(t, t + 10.0) for t in starts]
    rep["syncs"] = [analyse_sync_window(folder, a, b, wide) for a, b in windows]
    return rep


def _read_marker_labels(path: Path) -> list:
    """Only the app's own SYNC markers (free-text markers may contain personal notes)."""
    if not path.exists():
        return []
    out = []
    with open(path, newline="", encoding="utf-8") as f:
        r = csv.reader(f)
        next(r, None)
        for row in r:
            if len(row) >= 2 and row[1].startswith("SYNC"):
                try:
                    out.append((float(row[0]), row[1]))
                except ValueError:
                    pass
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("folders", nargs="+", type=Path, help="folder sesi rekaman (berisi session.json)")
    ap.add_argument("--wide", type=float, default=8.0, help="rentang pencarian lebar (detik), default 8")
    ap.add_argument("-o", "--out", type=Path, default=Path("diagnosa_sinkron.json"))
    args = ap.parse_args(argv)
    reports = []
    for d in args.folders:
        try:
            reports.append(diagnose(d, args.wide))
        except Exception as e:  # noqa: BLE001
            reports.append({"folder": d.name, "error": f"{type(e).__name__}: {e}"})
    text = json.dumps(reports, indent=2, ensure_ascii=False)
    args.out.write_text(text, encoding="utf-8")
    print(text)
    print(f"\nDisimpan di {args.out.resolve()}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
