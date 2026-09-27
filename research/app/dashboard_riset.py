"""Satu layar. PYTHONPATH=src streamlit run app/dashboard_riset.py --server.port 8502"""
from __future__ import annotations
import sys
import tempfile
import zipfile
from pathlib import Path
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.patches import Circle
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from muse2_pipeline.io import list_samples, load_sample
from muse2_pipeline.prv09 import compute_prv_09
from muse2_pipeline.maps import interpolate_brain_activity_idw, BRAIN_MAP_POSITIONS
from muse2_pipeline.segments import parse_marks, ruas_stats
from muse2_pipeline.eeg import CH
from scipy.stats import mannwhitneyu, kruskal

st.set_page_config(page_title="Muse 2 Dashboard Riset", layout="wide", initial_sidebar_state="collapsed")
st.markdown(
    """
    <style>
      header, footer, [data-testid="stToolbar"], #MainMenu {visibility:hidden; height:0;}
      .block-container {padding: 0.4rem 0.9rem 0.25rem 0.9rem; max-width: 100%;}
      div[data-testid="stMetric"] {
        background:#fff; border:1px solid #e6e8ee; border-radius:12px; padding:8px 10px;
      }
      div[data-testid="stMetricValue"] {font-size:1.2rem; font-weight:650;}
      div[data-testid="stMetricLabel"] {font-size:0.7rem; color:#667;}
      [data-testid="stFileUploader"] section {padding:0.3rem 0.45rem;}
      .stCaption, .stMarkdown p {font-size:0.76rem; line-height:1.2;}
    </style>
    """,
    unsafe_allow_html=True,
)

NICE = {
    "CALM_RELAXED": "Tenang",
    "FOCUSED_ENGAGED": "Fokus",
    "ACTIVATED_HIGH_AROUSAL": "Teraktivasi",
    "INDETERMINATE": "Indeterminan",
}
MAPD = {"LOW_AROUSAL": "CALM_RELAXED", "ENGAGEMENT": "FOCUSED_ENGAGED", "AROUSAL": "ACTIVATED_HIGH_AROUSAL"}
ARTI = {
    "CALM_RELAXED": "Otak lebih pelan, denyut tidak naik — nuansa istirahat.",
    "FOCUSED_ENGAGED": "Otak lebih siaga, denyut biasa — nuansa memperhatikan.",
    "ACTIVATED_HIGH_AROUSAL": "Otak dan/atau denyut lebih kencang — nuansa terpacu.",
    "INDETERMINATE": "Perubahan terlalu kecil atau campur; tidak memilih tiga label lain.",
}


def unpack_zip(upload) -> Path:
    tmp = Path(tempfile.mkdtemp(prefix="muse2_"))
    zpath = tmp / "data.zip"
    zpath.write_bytes(upload.getbuffer())
    with zipfile.ZipFile(zpath) as zf:
        zf.extractall(tmp / "unzip")
    hits = list((tmp / "unzip").rglob("EEG_raw.csv"))
    if not hits:
        return tmp / "unzip"
    return hits[0].parents[2] if hits[0].parent.name in ("experiment", "baseline") else tmp / "unzip"


def draw_map(ax, scores, title):
    xs, ys, grid = interpolate_brain_activity_idw(scores)
    xx, yy = np.meshgrid(xs, ys)
    ax.contourf(xx, yy, grid, levels=7, cmap="RdYlBu_r")
    ax.contour(xx, yy, grid, levels=7, colors="k", linewidths=0.25, alpha=0.35)
    ax.add_patch(Circle((0, 0), 1.0, fill=False, lw=0.8))
    for ch, (x, y) in BRAIN_MAP_POSITIONS.items():
        ax.scatter(x, y, s=10, c="k")
        ax.text(x, y + 0.14, ch, ha="center", fontsize=6)
    ax.set_aspect("equal")
    ax.set_xlim(-1.15, 1.15)
    ax.set_ylim(-1.15, 1.15)
    ax.axis("off")
    ax.set_title(title, fontsize=8)


def feat_of(w, hr):
    def m(col):
        return float(w[col].median()) if w is not None and col in w and len(w) else np.nan
    al = np.nanmedian([m("AF7_alpha"), m("AF8_alpha")])
    be = np.nanmedian([m("AF7_beta"), m("AF8_beta")])
    th = np.nanmedian([m("AF7_theta"), m("AF8_theta")])
    return {
        "alpha": al, "beta": be, "theta": th,
        "tb": th / be if be else np.nan, "ab": al / be if be else np.nan,
        "ta": th / al if al else np.nan, "hr": hr,
    }


def classify(feat, ref):
    def z(k):
        if not np.isfinite(feat.get(k, np.nan)) or not np.isfinite(ref.get(k, np.nan)):
            return np.nan
        return feat[k] - ref[k]
    fz = {k: z(k) for k in feat}
    dom = {
        "AROUSAL": np.nanmean([fz["beta"], fz["ab"], -fz["tb"], fz["hr"]]),
        "ENGAGEMENT": np.nanmean([fz["beta"], fz["alpha"], -fz["ta"]]),
        "LOW_AROUSAL": np.nanmean([fz["alpha"], fz["tb"], -fz["hr"]]),
    }
    if not all(np.isfinite(v) for v in dom.values()):
        return "INDETERMINATE"
    rk = sorted(dom.items(), key=lambda kv: kv[1], reverse=True)
    if rk[0][1] < 0.50 or rk[0][1] - rk[1][1] < 0.25:
        return "INDETERMINATE"
    return MAPD[rk[0][0]]


def mw(a, b):
    a, b = np.asarray(a, float), np.asarray(b, float)
    a, b = a[np.isfinite(a)], b[np.isfinite(b)]
    if len(a) < 5 or len(b) < 5:
        return np.nan
    try:
        return float(mannwhitneyu(a, b, alternative="two-sided").pvalue)
    except Exception:
        return np.nan


def uji_delta(bp, edges, band="alpha"):
    tmid = (bp["t_start"] + bp["t_end"]) / 2
    packs = []
    for a, b in zip(edges[:-1], edges[1:]):
        w = bp[(tmid >= a) & (tmid < b)]
        if len(w) == 0 or f"AF7_{band}" not in w:
            packs.append((f"{a:.0f}–{b:.0f}",) + tuple(np.array([]) for _ in range(5)))
            continue
        l, r = w[f"AF7_{band}"], w[f"AF8_{band}"]
        asym = ((r - l) / (l + r).replace(0, np.nan)).to_numpy()
        packs.append((
            f"{a:.0f}–{b:.0f}",
            ((l + r) / 2).to_numpy(),
            ((w["AF7_beta"] + w["AF8_beta"]) / 2).to_numpy() if "AF7_beta" in w else np.array([]),
            l.to_numpy(), r.to_numpy(), asym,
        ))
    out = []

    def fmt(p):
        return "n/a" if not np.isfinite(p) else f"{p:.3f}"

    if len(packs) >= 3:
        bits = []
        for name, idx in [("Δα", 1), ("Δβ", 2), ("AF7", 3), ("AF8", 4), ("asimetri", 5)]:
            good = [p[idx][np.isfinite(p[idx])] for p in packs if np.isfinite(p[idx]).sum() >= 5]
            if len(good) >= 3:
                try:
                    bits.append(f"{name} p={kruskal(*good).pvalue:.3f}")
                except Exception:
                    pass
        if bits:
            out.append("semua ruas — " + " · ".join(bits) + " (Kruskal–Wallis)")
    for i in range(len(packs) - 1):
        for j in range(i + 1, len(packs)):
            pa, pb = mw(packs[i][1], packs[j][1]), mw(packs[i][2], packs[j][2])
            p7, p8, ps = mw(packs[i][3], packs[j][3]), mw(packs[i][4], packs[j][4]), mw(packs[i][5], packs[j][5])
            out.append(
                f"{packs[i][0]} vs {packs[j][0]}  "
                f"Δα p={fmt(pa)} · Δβ p={fmt(pb)} · AF7 p={fmt(p7)} · AF8 p={fmt(p8)} · asimetri p={fmt(ps)}"
            )
    return out


default = Path.home() / "muse2-research" / "data" / "raw" / "trials"
processed = Path.home() / "muse2-research" / "data" / "processed"

r1 = st.columns([1.7, 0.85, 0.55, 1.35, 1.55])
with r1[0]:
    path = st.text_input("Folder trials", str(default))
with r1[1]:
    with st.expander("ZIP", expanded=False):
        up = st.file_uploader("Unggah", type=["zip"], label_visibility="collapsed")
with r1[2]:
    titik = st.text_input("Titik", "60")
with r1[3]:
    band = st.radio("Pita", ["delta", "theta", "alpha", "beta"], index=2, horizontal=True, label_visibility="collapsed")
trials = unpack_zip(up) if up is not None else Path(path)
inv = list_samples(trials) if Path(trials).exists() else None
if inv is None or inv.empty:
    st.error("Tidak ada EEG_raw + PPG_raw.")
    st.stop()
with r1[4]:
    label = st.selectbox("Sampel", inv["label"].tolist())

row = inv[inv["label"] == label].iloc[0]
data = load_sample(row["folder"], processed if processed.exists() else None)
eeg_f, ppg, bp, meta = data["eeg_f"], data["ppg"], data["bp"], data["meta"]
tmax = float(eeg_f["time_s"].iloc[-1])
edges = parse_marks(titik, tmax)
tab, _ = ruas_stats(bp, edges, band)
prv = compute_prv_09(ppg["PPG2"].to_numpy(float), ppg["time_s"].to_numpy(float))
t0 = st.slider("Peta (s)", 0, max(0, int(tmax) - 20), 0, 5)
t1v = min(t0 + 20, tmax)

p2, ts = ppg["PPG2"].to_numpy(float), ppg["time_s"].to_numpy(float)
states = []
if bp is not None and len(bp):
    tmid = (bp["t_start"] + bp["t_end"]) / 2
    feats = []
    for a, b in zip(edges[:-1], edges[1:]):
        w = bp[(tmid >= a) & (tmid < b)]
        hr = compute_prv_09(p2, ts, a, b)
        feats.append((feat_of(w, hr.get("hr", np.nan)), hr, a, b))
    ref = feats[0][0] if feats else {}
    for feat, hr, a, b in feats:
        stt = classify(feat, ref)
        states.append({"a": a, "b": b, "code": stt, "lab": NICE[stt],
                       "hr": hr.get("hr"), "rmssd": hr.get("prv_rmssd")})

ev = (meta.get("eeg_validation") or {}).get("status", "-")
pv = (meta.get("ppg_validation") or {}).get("status", "-")
frac = float(eeg_f["artifact_amp"].mean()) if "artifact_amp" in eeg_f.columns else np.nan

m = st.columns(6)
m[0].metric("Denyut", f"{prv['hr']:.0f}" if prv.get("ok") else "n/a")
m[1].metric("PRV-SDNN", f"{prv.get('prv_sdnn', float('nan')):.0f}" if prv.get("ok") else "n/a")
m[2].metric("PRV-RMSSD", f"{prv.get('prv_rmssd', float('nan')):.0f}" if prv.get("ok") else "n/a")
m[3].metric("Durasi", f"{tmax:.0f} s")
m[4].metric("EEG/PPG", f"{ev}/{pv}")
m[5].metric(">80 µV", f"{frac:.1%}" if np.isfinite(frac) else "n/a")

if states:
    cols = st.columns(len(states))
    for i, s in enumerate(states):
        with cols[i]:
            st.markdown(f"**{s['a']:.0f}–{s['b']:.0f} s · {s['lab']}**")
            st.caption(ARTI[s["code"]])
            if np.isfinite(s.get("hr", np.nan)):
                rm = s.get("rmssd", np.nan)
                rm_s = f"{rm:.0f}" if np.isfinite(rm) else "n/a"
                st.caption(f"Denyut {s['hr']:.0f}/menit · RMSSD {rm_s} ms")

left, right = st.columns([1.35, 1.05])
with left:
    fig, axes = plt.subplots(2, 1, figsize=(7.2, 2.35), sharex=True, layout="constrained")
    for c in CH:
        axes[0].plot(eeg_f["time_s"], eeg_f[c], lw=0.3)
    axes[0].set_ylim(-80, 80)
    axes[0].set_ylabel("EEG", fontsize=7)
    tp = prv.get("tp", np.array([]))
    if len(tp) >= 2:
        axes[1].plot(tp[:-1], np.diff(tp) * 1000, lw=0.65, color="C1")
    axes[1].set_ylim(400, 1500)
    axes[1].set_ylabel("IBI", fontsize=7)
    axes[1].set_xlabel("s", fontsize=7)
    for ax in axes:
        for x in edges[1:-1]:
            ax.axvline(x, color="k", ls="--", lw=0.7)
        ax.axvspan(t0, t1v, color="C0", alpha=0.10)
        ax.tick_params(labelsize=7)
        ax.grid(True, alpha=0.25)
    st.pyplot(fig, clear_figure=True, use_container_width=True)
with right:
    nmini = max(len(tab), 1) if bp is not None else 1
    fig2 = plt.figure(figsize=(4.4, 3.35), layout="constrained")
    gs = fig2.add_gridspec(2, max(nmini, 1), height_ratios=[1.35, 1.0])
    axb = fig2.add_subplot(gs[0, :])
    if bp is not None and len(bp):
        tmid = (bp["t_start"] + bp["t_end"]) / 2
        w = bp[(tmid >= t0) & (tmid < t1v)]
        if len(w) == 0:
            w = bp
        draw_map(axb, {c: float(w[f"{c}_{band}"].median()) for c in CH}, f"{t0:.0f}–{t1v:.0f}s {band}")
    if states and bp is not None and len(tab):
        for i, r in tab.iterrows():
            ax = fig2.add_subplot(gs[1, i])
            if r.get("n_win", 0) > 0:
                lab = states[i]["lab"] if i < len(states) else ""
                draw_map(ax, {c: float(r[c]) for c in CH}, f"{r['ruas']} · {lab}")
    st.pyplot(fig2, clear_figure=True, use_container_width=True)

if bp is not None:
    tes = uji_delta(bp, edges, band)
    if tes:
        st.caption("Uji antar ruas (Mann–Whitney; ≥3 ruas + Kruskal–Wallis). Bukan pengganti label.  " + "  |  ".join(tes))
st.caption(
    "Tenang = otak lebih pelan, denyut tidak naik. Fokus = otak lebih siaga, denyut biasa. "
    "Teraktivasi = otak/denyut lebih kencang. Indeterminan = terlalu kecil atau campur. "
    "PRV dahi ≠ HRV Polar. Acuan kondisi = ruas pertama. Hipotesis tampilan."
)
