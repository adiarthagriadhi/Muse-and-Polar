from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.stats import mannwhitneyu

CH = ["TP9", "AF7", "AF8", "TP10"]


def parse_marks(text, tmax):
    vals = []
    for tok in str(text).replace(";", ",").split(","):
        tok = tok.strip()
        if tok == "":
            continue
        try:
            vals.append(float(tok))
        except ValueError:
            continue
    vals = [v for v in vals if 0 < v < tmax]
    return [0.0] + sorted(set(vals)) + [float(tmax)]


def asimetri(l, r):
    s = l + r
    if s == 0 or pd.isna(l) or pd.isna(r):
        return np.nan
    return (r - l) / s


def arti_as(a):
    if pd.isna(a):
        return "tidak dihitung"
    if abs(a) < 0.10:
        return "kiri–kanan hampir seimbang"
    return "lebih menonjol di kanan (AF8)" if a > 0 else "lebih menonjol di kiri (AF7)"


def mw(a, b):
    a = np.asarray(a, float)
    b = np.asarray(b, float)
    a, b = a[np.isfinite(a)], b[np.isfinite(b)]
    if len(a) < 3 or len(b) < 3:
        return np.nan
    try:
        return float(mannwhitneyu(a, b, alternative="two-sided").pvalue)
    except Exception:
        return np.nan


def ruas_stats(bp, edges, band):
    if bp is None or not len(bp):
        return pd.DataFrame(), pd.DataFrame()
    tmid = (bp["t_start"] + bp["t_end"]) / 2
    chunks, rows = [], []
    for a, b in zip(edges[:-1], edges[1:]):
        w = bp[(tmid >= a) & (tmid < b)].copy()
        chunks.append(w)
        rec = {"ruas": f"{a:.0f}–{b:.0f} detik", "t0": a, "t1": b, "n_win": int(len(w))}
        if len(w):
            for c in CH:
                rec[c] = float(w[f"{c}_{band}"].median())
            rec["AF_asimetri"] = asimetri(rec["AF7"], rec["AF8"])
            rec["arti"] = arti_as(rec["AF_asimetri"])
        else:
            for c in CH:
                rec[c] = np.nan
            rec["AF_asimetri"] = np.nan
            rec["arti"] = "kosong"
        rows.append(rec)
    tab = pd.DataFrame(rows)
    comps = []
    for i in range(len(chunks) - 1):
        for j in range(i + 1, len(chunks)):
            for feat, label in [(f"AF7_{band}", "AF7"), (f"AF8_{band}", "AF8")]:
                if feat not in chunks[i] or feat not in chunks[j]:
                    continue
                p = mw(chunks[i][feat], chunks[j][feat])
                mi = chunks[i][feat].median() if len(chunks[i]) else np.nan
                mj = chunks[j][feat].median() if len(chunks[j]) else np.nan
                comps.append({
                    "perbandingan": f"{tab.iloc[i].ruas} vs {tab.iloc[j].ruas}",
                    "ukuran": label,
                    "median_1": mi,
                    "median_2": mj,
                    "selisih": (mj - mi) if pd.notna(mi) and pd.notna(mj) else np.nan,
                    "p": p,
                    "berbeda": "ya" if (pd.notna(p) and p < 0.05) else "tidak",
                })
            if len(chunks[i]) and len(chunks[j]):
                den_i = chunks[i][f"AF8_{band}"] + chunks[i][f"AF7_{band}"]
                den_j = chunks[j][f"AF8_{band}"] + chunks[j][f"AF7_{band}"]
                a1s = (chunks[i][f"AF8_{band}"] - chunks[i][f"AF7_{band}"]) / den_i.replace(0, np.nan)
                a2s = (chunks[j][f"AF8_{band}"] - chunks[j][f"AF7_{band}"]) / den_j.replace(0, np.nan)
                p_as = mw(a1s, a2s)
                comps.append({
                    "perbandingan": f"{tab.iloc[i].ruas} vs {tab.iloc[j].ruas}",
                    "ukuran": "asimetri AF",
                    "median_1": float(np.nanmedian(a1s)),
                    "median_2": float(np.nanmedian(a2s)),
                    "selisih": float(np.nanmedian(a2s) - np.nanmedian(a1s)),
                    "p": p_as,
                    "berbeda": "ya" if (pd.notna(p_as) and p_as < 0.05) else "tidak",
                })
    return tab, pd.DataFrame(comps)
