"""Session analysis for Research View v2.

``Session`` loads one musepolar recording once (filtering, spectra, beat detection) and
answers every view the dashboard needs: static overview data, per-segment ("ruas")
analysis for a given band/metric/reference, decimated EEG for any zoom range, and exports.

Method (see research/README.md for the reasoning):

- EEG band power per 4 s window (2 s step) = mean of the artifact-free 2 s Hann sub-segments
  (0.25 s hop) inside it. A sub-segment is rejected when |x| > art_uv µV (blink, movement) or
  its SD < 0.5 µV (flat / no contact); a window without any clean sub-segment is dropped.
- Segment values are medians over clean windows. Statistics use only non-overlapping
  windows (every 2nd window) so that samples are not double counted; pairwise
  Mann–Whitney U with Holm correction per measure, Cliff's delta as effect size,
  Kruskal–Wallis when there are 3 or more segments.
- Condition labels compare each segment with the reference segment in z units:
  z = (segment median − reference median) / reference SD, on log10 band powers, log ratios
  and heart rate, so features with different units are comparable.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
from scipy.stats import kruskal, mannwhitneyu

from .eeg import BANDS, CH, subsegment_spectra, window_spectra
from .hrv import clean_ibi, hr_at, hrv_stats, ppg_beats
from .io import load_sample, marker_titik
from .segments import parse_marks

LABELS = {
    "REFERENCE": ("Acuan", "Ruas pembanding. Kondisi ruas lain dihitung relatif terhadap ruas ini."),
    "CALM_RELAXED": ("Tenang", "Otak lebih pelan, denyut tidak naik: nuansa istirahat."),
    "FOCUSED_ENGAGED": ("Fokus", "Otak lebih siaga, denyut biasa: nuansa memperhatikan."),
    "ACTIVATED_HIGH_AROUSAL": ("Teraktivasi", "Otak dan/atau denyut lebih kencang: nuansa terpacu."),
    "INDETERMINATE": ("Indeterminan", "Perubahan terlalu kecil atau bercampur; tidak memilih tiga label lain."),
    "NO_DATA": ("Data kurang", "Kurang dari 3 jendela EEG bersih di dahi (AF7 & AF8)."),
}
DOMAIN_TO_CODE = {"LOW_AROUSAL": "CALM_RELAXED", "ENGAGEMENT": "FOCUSED_ENGAGED", "AROUSAL": "ACTIVATED_HIGH_AROUSAL"}
# Minimum reference SD (floors keep z finite when the reference is very steady).
SD_FLOOR = {"alpha": 0.05, "beta": 0.05, "theta": 0.05, "tb": 0.05, "ab": 0.05, "ta": 0.05, "hr": 2.0}
Z_MIN, Z_MARGIN = 0.5, 0.25
MIN_N_TEST = 5
MEASURES = ["AF", "AF7", "AF8", "TP9", "TP10", "Asimetri AF"]


# --- small helpers ------------------------------------------------------------------

def _num(v, digits: int = 4):
    if v is None:
        return None
    try:
        v = float(v)
    except (TypeError, ValueError):
        return None
    if not np.isfinite(v):
        return None
    if abs(v) < 1e-9:
        return 0.0
    return float(f"{v:.{digits}g}")


def _arr(a, digits: int = 4) -> list:
    return [_num(v, digits) for v in np.asarray(a, float).ravel()]


def _med(x):
    x = np.asarray(x, float)
    x = x[np.isfinite(x)]
    return float(np.median(x)) if len(x) else np.nan


def holm(pvals: list) -> list:
    """Holm–Bonferroni adjusted p-values (None stays None)."""
    idx = [i for i, p in enumerate(pvals) if p is not None]
    out = [None] * len(pvals)
    m = len(idx)
    running = 0.0
    for rank, i in enumerate(sorted(idx, key=lambda i: pvals[i])):
        running = max(running, min(1.0, (m - rank) * pvals[i]))
        out[i] = running
    return out


def mw_test(a, b) -> tuple[float | None, float | None]:
    """Two-sided Mann–Whitney p and Cliff's delta (positive: b tends to be larger than a)."""
    a = np.asarray(a, float)
    b = np.asarray(b, float)
    a, b = a[np.isfinite(a)], b[np.isfinite(b)]
    if len(a) < MIN_N_TEST or len(b) < MIN_N_TEST:
        return None, None
    try:
        res = mannwhitneyu(a, b, alternative="two-sided")
    except ValueError:
        return None, None
    u_b = len(a) * len(b) - res.statistic
    return float(res.pvalue), float(2 * u_b / (len(a) * len(b)) - 1)


def cliff_word(d: float | None) -> str:
    if d is None:
        return "-"
    a = abs(d)
    return "sangat kecil" if a < 0.147 else "kecil" if a < 0.33 else "sedang" if a < 0.474 else "besar"


# --- session ------------------------------------------------------------------------

class Session:
    def __init__(self, folder: Path):
        self.folder = Path(folder)
        self.sample = load_sample(self.folder, legacy_bp=False)
        eeg = self.sample["eeg_f"]
        self.tmax = float(eeg["time_s"].iloc[-1])
        self.sub = subsegment_spectra(eeg)
        self._specs: dict[float, dict] = {}
        self.grid = self.spec(100.0)
        ppg = self.sample["ppg"]
        self.ppg = clean_ibi(ppg_beats(ppg["PPG2"].to_numpy(float), ppg["time_s"].to_numpy(float)))
        rr = self.sample["rr"]
        self.polar = clean_ibi(rr["time_s"].to_numpy(float), rr["rr_ms"].to_numpy(float) / 1000.0)
        self.has_polar = int(self.polar["valid"].sum()) >= 20
        self._eeg_t = eeg["time_s"].to_numpy(float)
        self._eeg_x = eeg[CH].to_numpy(float)

    def spec(self, art_uv: float) -> dict:
        key = round(float(art_uv), 1)
        if key not in self._specs:
            if len(self._specs) > 6:
                self._specs.clear()
            self._specs[key] = window_spectra(self.sub, key)
        return self._specs[key]

    # static overview -----------------------------------------------------------
    def overview(self) -> dict:
        s, meta = self.sample, self.sample["meta"]
        spec = self.grid
        mk = s["markers"]
        markers = [{"t": _num(t, 6), "label": str(lab)} for t, lab in zip(mk["time_s"], mk["label"])]
        return {
            "name": s["participant"],
            "note": s["condition"],
            "folder": str(self.folder),
            "label": self.folder.name,
            "start": meta.get("start_local"),
            "duration": _num(self.tmax, 6),
            "channels": CH,
            "bands": {k: list(v) for k, v in BANDS.items()},
            "quality": {"eeg": meta.get("eeg_validation"), "ppg": meta.get("ppg_validation")},
            "sync_offset_ms": _num(s["sync_offset"] * 1000, 4) if s["sync_offset"] is not None else None,
            "markers": markers,
            "marker_titik": marker_titik(mk),
            "windows": {
                "win_s": spec["win_s"],
                "t_start": _arr(spec["t_start"], 6),
                "t_mid": _arr(spec["t_mid"], 6),
            },
            "ppg": self._series_json(self.ppg),
            "polar": self._series_json(self.polar) if len(self.polar["t"]) else None,
            "hrv": {"ppg": hrv_stats(self.ppg), "polar": hrv_stats(self.polar) if self.has_polar else None},
        }

    @staticmethod
    def _series_json(ser: dict) -> dict:
        return {"t": _arr(ser["t"], 6), "ibi": _arr(ser["ibi"] * 1000, 5), "valid": [bool(v) for v in ser["valid"]]}

    # EEG for display -------------------------------------------------------------
    def signal(self, t0: float, t1: float, n: int = 1600) -> dict:
        t, x = self._eeg_t, self._eeg_x
        i0, i1 = np.searchsorted(t, [t0, t1])
        i0, i1 = max(0, i0 - 1), min(len(t), i1 + 1)
        tt, xx = t[i0:i1], x[i0:i1]
        n = max(50, min(int(n), 5000))
        if len(tt) <= 2 * n:
            return {"kind": "raw", "t": _arr(tt, 7), "y": [_arr(xx[:, c], 4) for c in range(len(CH))]}
        size = len(tt) // n
        m = size * n
        tb = tt[:m].reshape(n, size).mean(axis=1)
        xb = xx[:m].reshape(n, size, len(CH))
        return {"kind": "env", "t": _arr(tb, 7),
                "lo": [_arr(xb[:, :, c].min(axis=1), 4) for c in range(len(CH))],
                "hi": [_arr(xb[:, :, c].max(axis=1), 4) for c in range(len(CH))]}

    # analysis for one set of settings -----------------------------------------
    def window_values(self, spec: dict, band: str, metric: str) -> np.ndarray:
        p = spec["power"][band]
        if metric == "rel":
            with np.errstate(divide="ignore", invalid="ignore"):
                return 100.0 * p / spec["total"]
        return p

    def analyze(self, titik: str = "", band: str = "alpha", metric: str = "abs",
                ref: int = 0, art_uv: float = 100.0) -> dict:
        if band not in BANDS:
            band = "alpha"
        metric = "rel" if metric == "rel" else "abs"
        spec = self.spec(art_uv)
        edges = parse_marks(titik, self.tmax)
        nseg = len(edges) - 1
        ref = int(ref) if 0 <= int(ref) < nseg else 0
        bad = spec["bad"]
        vals = self.window_values(spec, band, metric)
        tmid = spec["t_mid"]
        seg_of = np.searchsorted(edges, tmid, side="right") - 1
        seg_of[seg_of >= nseg] = nseg - 1
        af = [CH.index("AF7"), CH.index("AF8")]
        af_clean = ~bad[:, af].any(axis=1)

        # map/change values: log10 for absolute power, percent for relative power
        mvals = np.log10(np.where(vals > 0, vals, np.nan)) if metric == "abs" else vals
        ref_mask = seg_of == ref
        ref_mean, ref_sd = [], []
        for c in range(len(CH)):
            v = mvals[ref_mask & ~bad[:, c], c]
            v = v[np.isfinite(v)]
            ref_mean.append(float(np.median(v)) if len(v) >= 3 else np.nan)
            floor = 0.05 if metric == "abs" else 0.5
            ref_sd.append(max(float(v.std(ddof=1)), floor) if len(v) >= 3 else np.nan)

        feats, hr_source = self._features(spec, af_clean)
        zref = self._ref_stats(feats, seg_of == ref)

        marks = self.sample["markers"]
        segs = []
        for i, (a, b) in enumerate(zip(edges[:-1], edges[1:])):
            m = seg_of == i
            ch_vals, ch_z, ch_clean = [], [], []
            for c in range(len(CH)):
                v = vals[m & ~bad[:, c], c]
                ch_vals.append(_med(v))
                ch_z.append((_med(mvals[m & ~bad[:, c], c]) - ref_mean[c]) / ref_sd[c])
                ch_clean.append(int(len(v)))
            l, r = ch_vals[af[0]], ch_vals[af[1]]
            asym = (r - l) / (r + l) if np.isfinite(l) and np.isfinite(r) and (r + l) else np.nan
            n_af = int((m & af_clean).sum())
            z = {k: (_med(feats[k][m & af_clean]) - zref[k][0]) / zref[k][1] for k in feats}
            code, scores = self._classify(z, n_af, i == ref)
            name = ""
            for t, lab in zip(marks["time_s"], marks["label"]):
                if abs(t - a) <= 1.5 and not str(lab).startswith("SYNC"):
                    name = str(lab)
            segs.append({
                "i": i, "t0": _num(a, 6), "t1": _num(b, 6), "name": name,
                "n_win": int(m.sum()), "n_clean": ch_clean, "n_af": n_af,
                "values": _arr(ch_vals), "z": _arr(ch_z, 3), "asym": _num(asym, 3),
                "ppg": hrv_stats(self.ppg, a, b),
                "polar": hrv_stats(self.polar, a, b) if self.has_polar else None,
                "code": code, "label": LABELS[code][0], "arti": LABELS[code][1],
                "feat_z": {k: _num(v, 3) for k, v in z.items()},
                "scores": {k: _num(v, 3) for k, v in scores.items()},
                "psd": [_arr(self._mean_psd(spec, a, b, c), 4) for c in range(len(CH))],
            })

        return {
            "band": band, "metric": metric, "ref": ref, "art_uv": art_uv,
            "unit": "%" if metric == "rel" else "µV²",
            "edges": _arr(edges, 6),
            "bad": [int(sum(1 << c for c in range(len(CH)) if bad[w, c])) for w in range(len(bad))],
            "clean_frac": _arr(spec["clean"].mean(axis=0), 3) if len(spec["clean"]) else [None] * len(CH),
            "windows": {"power": {bn: [_arr(spec["power"][bn][:, c]) for c in range(len(CH))] for bn in BANDS},
                        "total": [_arr(spec["total"][:, c]) for c in range(len(CH))]},
            "ref_mean": _arr(ref_mean), "ref_sd": _arr(ref_sd),
            "hr_source": hr_source,
            "freqs": _arr(self.sub["freqs"], 4),
            "segments": segs,
            "tests": self._tests(spec, vals, bad, seg_of, nseg, edges),
        }

    def _features(self, spec, af_clean):
        p = spec["power"]
        with np.errstate(divide="ignore", invalid="ignore"):
            al = np.log10(p["alpha"][:, 1:3].mean(axis=1))
            be = np.log10(p["beta"][:, 1:3].mean(axis=1))
            th = np.log10(p["theta"][:, 1:3].mean(axis=1))
        src, ser = ("polar", self.polar) if self.has_polar else ("ppg", self.ppg)
        hr = hr_at(ser, spec["t_mid"], spec["win_s"] / 2)
        if not np.isfinite(hr).any():
            src = None
        feats = {"alpha": al, "beta": be, "theta": th, "tb": th - be, "ab": al - be, "ta": th - al, "hr": hr}
        for k in feats:
            if k != "hr":
                feats[k] = np.where(af_clean, feats[k], np.nan)
        return feats, src

    @staticmethod
    def _ref_stats(feats, ref_mask):
        out = {}
        for k, v in feats.items():
            x = v[ref_mask]
            x = x[np.isfinite(x)]
            out[k] = (float(np.median(x)), max(float(x.std(ddof=1)), SD_FLOOR[k])) if len(x) >= 3 else (np.nan, np.nan)
        return out

    @staticmethod
    def _classify(z, n_af, is_ref):
        def zz(k):
            return z.get(k, np.nan)

        dom = {
            "AROUSAL": np.nanmean([zz("beta"), zz("ab"), -zz("tb"), zz("hr")]),
            "ENGAGEMENT": np.nanmean([zz("beta"), zz("alpha"), -zz("ta")]),
            "LOW_AROUSAL": np.nanmean([zz("alpha"), zz("tb"), -zz("hr")]),
        } if any(np.isfinite(v) for v in z.values()) else {"AROUSAL": np.nan, "ENGAGEMENT": np.nan, "LOW_AROUSAL": np.nan}
        if is_ref:
            return "REFERENCE", dom
        if n_af < 3 or not all(np.isfinite(v) for v in dom.values()):
            return "NO_DATA", dom
        rk = sorted(dom.items(), key=lambda kv: kv[1], reverse=True)
        if rk[0][1] < Z_MIN or rk[0][1] - rk[1][1] < Z_MARGIN:
            return "INDETERMINATE", dom
        return DOMAIN_TO_CODE[rk[0][0]], dom

    def _mean_psd(self, spec, a, b, c):
        mid = self.sub["t0"] + self.sub["seg_s"] / 2
        mask = (mid >= a) & (mid < b) & spec["clean"][:, c]
        if not mask.any():
            return np.full(len(self.sub["freqs"]), np.nan)
        return self.sub["psd"][mask, c, :].mean(axis=0)

    def _tests(self, spec, vals, bad, seg_of, nseg, edges):
        k = max(1, int(round(spec["win_s"] / spec["step_s"])))
        keep = np.zeros(len(vals), bool)
        keep[::k] = True  # non-overlapping windows only
        i7, i8 = CH.index("AF7"), CH.index("AF8")
        per = {}
        for meas in MEASURES:
            if meas in CH:
                c = CH.index(meas)
                v, ok = vals[:, c], ~bad[:, c]
            else:
                ok = ~bad[:, i7] & ~bad[:, i8]
                l, r = vals[:, i7], vals[:, i8]
                with np.errstate(divide="ignore", invalid="ignore"):
                    v = (l + r) / 2 if meas == "AF" else (r - l) / (r + l)
            per[meas] = [v[keep & ok & (seg_of == i)] for i in range(nseg)]
        names = [f"{a:.0f}–{b:.0f} s" for a, b in zip(edges[:-1], edges[1:])]
        pairs, omnibus = [], []
        for meas, groups in per.items():
            rows = []
            for i in range(nseg - 1):
                for j in range(i + 1, nseg):
                    p, d = mw_test(groups[i], groups[j])
                    rows.append({
                        "measure": meas, "a": i, "b": j, "pair": f"{names[i]} vs {names[j]}",
                        "n_a": int(np.isfinite(groups[i]).sum()), "n_b": int(np.isfinite(groups[j]).sum()),
                        "med_a": _num(_med(groups[i])), "med_b": _num(_med(groups[j])),
                        "p": p, "delta": _num(d, 3), "effect": cliff_word(d),
                    })
            for r, ph in zip(rows, holm([r["p"] for r in rows])):
                r["p_holm"] = _num(ph, 3)
                r["p"] = _num(r["p"], 3)
                r["sig"] = bool(ph is not None and ph < 0.05)
            pairs += rows
            good = [g[np.isfinite(g)] for g in groups if np.isfinite(g).sum() >= MIN_N_TEST]
            if nseg >= 3 and len(good) >= 3:
                try:
                    omnibus.append({"measure": meas, "p": _num(kruskal(*good).pvalue, 3), "k": len(good)})
                except ValueError:
                    pass
        return {"pairs": pairs, "omnibus": omnibus, "n_step": k}
