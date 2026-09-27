"""
pip install nicegui
cd research
PYTHONPATH=src python legacy/nicegui_dashboard.py
"""
from __future__ import annotations
import sys
import tempfile
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Circle

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from muse2_pipeline.io import list_samples, load_sample, DEFAULT_RECORDINGS
from muse2_pipeline.prv09 import compute_prv_09
from muse2_pipeline.maps import interpolate_brain_activity_idw, BRAIN_MAP_POSITIONS
from muse2_pipeline.segments import parse_marks, ruas_stats
from muse2_pipeline.eeg import CH
from scipy.stats import mannwhitneyu, kruskal

from nicegui import ui, events

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
DEFAULT = DEFAULT_RECORDINGS


def draw_map(ax, scores, title):
    xs, ys, grid = interpolate_brain_activity_idw(scores)
    xx, yy = np.meshgrid(xs, ys)
    ax.contourf(xx, yy, grid, levels=7, cmap="RdYlBu_r")
    ax.contour(xx, yy, grid, levels=7, colors="k", linewidths=0.25, alpha=0.35)
    ax.add_patch(Circle((0, 0), 1.0, fill=False, lw=0.8))
    for ch, (x, y) in BRAIN_MAP_POSITIONS.items():
        ax.scatter(x, y, s=10, c="k")
        ax.text(x, y + 0.14, ch, ha="center", fontsize=7)
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


def uji_line(bp, edges, band):
    tmid = (bp["t_start"] + bp["t_end"]) / 2
    packs = []
    for a, b in zip(edges[:-1], edges[1:]):
        w = bp[(tmid >= a) & (tmid < b)]
        if len(w) == 0 or f"AF7_{band}" not in w:
            continue
        l, r = w[f"AF7_{band}"], w[f"AF8_{band}"]
        packs.append((f"{a:.0f}–{b:.0f}", l.to_numpy(), r.to_numpy(),
                      ((l + r) / 2).to_numpy(),
                      ((r - l) / (l + r).replace(0, np.nan)).to_numpy(),
                      ((w["AF7_beta"] + w["AF8_beta"]) / 2).to_numpy() if "AF7_beta" in w else np.array([])))
    bits = []
    def fmt(p):
        return "n/a" if not np.isfinite(p) else f"{p:.3f}"
    for i in range(len(packs) - 1):
        for j in range(i + 1, len(packs)):
            p7, p8 = mw(packs[i][1], packs[j][1]), mw(packs[i][2], packs[j][2])
            pa, ps, pb = mw(packs[i][3], packs[j][3]), mw(packs[i][4], packs[j][4]), mw(packs[i][5], packs[j][5])
            bits.append(
                f"{packs[i][0]} vs {packs[j][0]} Δα p={fmt(pa)} · Δβ p={fmt(pb)} · "
                f"AF7 p={fmt(p7)} · AF8 p={fmt(p8)} · asimetri p={fmt(ps)}"
            )
    return "  |  ".join(bits)


ui.add_head_html("""
<style>
  body { background:#f4f6f8; }
  .card { background:#fff; border:1px solid #e6e8ee; border-radius:14px; padding:10px 12px; }
</style>
""")

state = {"inv": None, "label": None, "band": "alpha", "titik": "60", "t0": 0}


def inventory():
    p = Path(folder.value)
    if p.exists():
        state["inv"] = list_samples(p)
    else:
        state["inv"] = None
    opts = state["inv"]["label"].tolist() if state["inv"] is not None and not state["inv"].empty else []
    sample_sel.options = opts
    if opts and state["label"] not in opts:
        state["label"] = opts[0]
        sample_sel.value = opts[0]
    refresh()


def refresh():
    if state["inv"] is None or state["inv"].empty or not state["label"]:
        return
    row = state["inv"][state["inv"]["label"] == state["label"]]
    if row.empty:
        return
    row = row.iloc[0]
    data = load_sample(row["folder"])
    eeg_f, ppg, bp, meta = data["eeg_f"], data["ppg"], data["bp"], data["meta"]
    tmax = float(eeg_f["time_s"].iloc[-1])
    edges = parse_marks(state["titik"], tmax)
    tab, _ = ruas_stats(bp, edges, state["band"])
    prv = compute_prv_09(ppg["PPG2"].to_numpy(float), ppg["time_s"].to_numpy(float))
    t0, t1v = state["t0"], min(state["t0"] + 20, tmax)
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
            states.append((a, b, stt, hr))

    hr_s = f"{prv['hr']:.0f}" if prv.get("ok") else "n/a"
    sd = f"{prv.get('prv_sdnn', float('nan')):.0f}" if prv.get("ok") else "n/a"
    rm = f"{prv.get('prv_rmssd', float('nan')):.0f}" if prv.get("ok") else "n/a"
    ev = (meta.get("eeg_validation") or {}).get("status", "-")
    pv = (meta.get("ppg_validation") or {}).get("status", "-")
    frac = float(eeg_f["artifact_amp"].mean()) if "artifact_amp" in eeg_f.columns else np.nan
    metrics_row.clear()
    with metrics_row:
        for lab, val in [
            ("Denyut", hr_s), ("PRV-SDNN", sd), ("PRV-RMSSD", rm),
            ("Durasi", f"{tmax:.0f} s"), ("EEG/PPG", f"{ev}/{pv}"),
            (">80 µV", f"{frac:.1%}" if np.isfinite(frac) else "n/a"),
        ]:
            with ui.card().classes("w-full"):
                ui.label(lab).classes("text-xs text-grey-7")
                ui.label(str(val)).classes("text-xl font-medium")

    cond_row.clear()
    with cond_row:
        for a, b, stt, hr in states:
            with ui.card().classes("w-full"):
                ui.label(f"{a:.0f}–{b:.0f} s · {NICE[stt]}").classes("font-medium")
                ui.label(ARTI[stt]).classes("text-xs text-grey-8")
                if hr.get("ok"):
                    ui.label(f"Denyut {hr['hr']:.0f}/menit · RMSSD {hr.get('prv_rmssd', float('nan')):.0f} ms").classes("text-xs")

    fig, axes = plt.subplots(2, 1, figsize=(7.0, 2.3), sharex=True, layout="constrained")
    for c in CH:
        axes[0].plot(eeg_f["time_s"], eeg_f[c], lw=0.3)
    axes[0].set_ylim(-80, 80)
    axes[0].set_ylabel("EEG")
    tp = prv.get("tp", np.array([]))
    if len(tp) >= 2:
        axes[1].plot(tp[:-1], np.diff(tp) * 1000, lw=0.65, color="C1")
    axes[1].set_ylim(400, 1500)
    axes[1].set_ylabel("IBI")
    for ax in axes:
        for x in edges[1:-1]:
            ax.axvline(x, color="k", ls="--", lw=0.7)
        ax.axvspan(t0, t1v, color="C0", alpha=0.10)
        ax.grid(True, alpha=0.25)
    fig_path = Path(tempfile_fig("traces.png"))
    fig.savefig(fig_path, dpi=110)
    plt.close(fig)

    nmini = max(len(tab), 1) if bp is not None else 1
    fig2 = plt.figure(figsize=(4.4, 3.2), layout="constrained")
    gs = fig2.add_gridspec(2, max(nmini, 1), height_ratios=[1.3, 1.0])
    axb = fig2.add_subplot(gs[0, :])
    if bp is not None and len(bp):
        tmid = (bp["t_start"] + bp["t_end"]) / 2
        w = bp[(tmid >= t0) & (tmid < t1v)]
        if len(w) == 0:
            w = bp
        draw_map(axb, {c: float(w[f"{c}_{state['band']}"].median()) for c in CH},
                 f"{t0:.0f}–{t1v:.0f}s {state['band']}")
        for i, r in tab.iterrows():
            ax = fig2.add_subplot(gs[1, i])
            if r.get("n_win", 0) > 0:
                lab = NICE[states[i][2]] if i < len(states) else ""
                draw_map(ax, {c: float(r[c]) for c in CH}, f"{r['ruas']} · {lab}")
    map_path = Path(tempfile_fig("maps.png"))
    fig2.savefig(map_path, dpi=110)
    plt.close(fig2)

    traces_img.set_source(str(fig_path))
    maps_img.set_source(str(map_path))
    tes.text = uji_line(bp, edges, state["band"]) if bp is not None else ""


def tempfile_fig(name):
    d = Path(tempfile.gettempdir()) / "muse2_figures"
    d.mkdir(parents=True, exist_ok=True)
    return d / name


with ui.row().classes("w-full items-end gap-3"):
    folder = ui.input("Folder recordings", value=str(DEFAULT)).classes("w-80")
    ui.button("Muat folder", on_click=inventory)
    sample_sel = ui.select([], label="Sampel", on_change=lambda e: (state.update(label=e.value), refresh()))
    titik_in = ui.input("Titik", value="60").classes("w-24")
    titik_in.on("blur", lambda: (state.update(titik=titik_in.value), refresh()))
    band_sel = ui.toggle(["delta", "theta", "alpha", "beta"], value="alpha",
                         on_change=lambda e: (state.update(band=e.value), refresh()))
    t0_sl = ui.slider(min=0, max=230, value=0, step=5).classes("w-40")
    t0_sl.on("update:model-value", lambda e: (state.update(t0=int(e.args if not isinstance(e.args, list) else e.args[0])), refresh()))

metrics_row = ui.row().classes("w-full gap-2")
cond_row = ui.row().classes("w-full gap-2")
with ui.row().classes("w-full items-start"):
    traces_img = ui.image().classes("w-7/12")
    maps_img = ui.image().classes("w-5/12")
tes = ui.label("").classes("text-xs text-grey-8")
ui.label(
    "Tenang = otak lebih pelan, denyut tidak naik. Fokus = otak lebih siaga, denyut biasa. "
    "Teraktivasi = otak/denyut lebih kencang. Indeterminan = terlalu kecil atau campur. "
    "PRV dahi ≠ HRV Polar. Acuan = ruas pertama. Hipotesis tampilan."
).classes("text-xs text-grey-7")

ui.timer(0.2, inventory, once=True)
ui.run(title="Muse 2 Dashboard Riset", reload=False, port=8510)
