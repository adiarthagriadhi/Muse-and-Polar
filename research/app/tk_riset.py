"""GUI riset Tk. Dari Jupyter:

import sys
from pathlib import Path
ROOT = Path.home() / "muse2-research" / "app-standalone" / "muse2-research-app"
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "app"))
from tk_riset import launch
launch()
"""
from __future__ import annotations
import sys
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use("TkAgg")
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure
from matplotlib.patches import Circle

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from muse2_pipeline.io import list_samples, load_sample
from muse2_pipeline.prv09 import compute_prv_09
from muse2_pipeline.maps import interpolate_brain_activity_idw, BRAIN_MAP_POSITIONS
from muse2_pipeline.segments import parse_marks, ruas_stats
from muse2_pipeline.eeg import CH
from scipy.stats import mannwhitneyu

NICE = {
    "CALM_RELAXED": "Tenang",
    "FOCUSED_ENGAGED": "Fokus",
    "ACTIVATED_HIGH_AROUSAL": "Teraktivasi",
    "INDETERMINATE": "Indeterminan",
}
MAPD = {"LOW_AROUSAL": "CALM_RELAXED", "ENGAGEMENT": "FOCUSED_ENGAGED", "AROUSAL": "ACTIVATED_HIGH_AROUSAL"}
ARTI = {
    "CALM_RELAXED": "Otak lebih pelan, denyut tidak naik.",
    "FOCUSED_ENGAGED": "Otak lebih siaga, denyut biasa.",
    "ACTIVATED_HIGH_AROUSAL": "Otak/denyut lebih kencang.",
    "INDETERMINATE": "Perubahan terlalu kecil atau campur.",
}
DEFAULT = Path.home() / "muse2-research" / "data" / "raw" / "trials"
PROCESSED = Path.home() / "muse2-research" / "data" / "processed"


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
        return None
    try:
        return float(mannwhitneyu(a, b, alternative="two-sided").pvalue)
    except Exception:
        return None


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


class RisetApp:
    def __init__(self, root):
        self.root = root
        root.title("Muse 2 — GUI Riset")
        root.geometry("1280x820")
        self.trials = DEFAULT
        self.pack = None
        self.band = tk.StringVar(value="alpha")
        self.build()
        self.refresh_samples()

    def build(self):
        bar = ttk.Frame(self.root, padding=8)
        bar.pack(fill="x")
        ttk.Button(bar, text="Folder…", command=self.pick_folder).pack(side="left")
        ttk.Button(bar, text="ZIP…", command=self.pick_zip).pack(side="left", padx=(4, 12))
        ttk.Label(bar, text="Sampel").pack(side="left")
        self.cb = ttk.Combobox(bar, width=28, state="readonly")
        self.cb.pack(side="left", padx=4)
        self.cb.bind("<<ComboboxSelected>>", lambda e: self.compute())
        ttk.Label(bar, text="Titik").pack(side="left", padx=(10, 0))
        self.ent_titik = ttk.Entry(bar, width=14)
        self.ent_titik.insert(0, "60")
        self.ent_titik.pack(side="left", padx=4)
        for b in ("delta", "theta", "alpha", "beta"):
            ttk.Radiobutton(bar, text=b, value=b, variable=self.band,
                            command=self.compute).pack(side="left")
        ttk.Button(bar, text="Terapkan", command=self.compute).pack(side="left", padx=8)

        kpi = ttk.Frame(self.root, padding=(8, 0))
        kpi.pack(fill="x")
        self.kpi = {}
        for name in ("Denyut", "SDNN", "RMSSD", "Durasi", "EEG/PPG", ">80µV"):
            f = ttk.LabelFrame(kpi, text=name)
            f.pack(side="left", expand=True, fill="x", padx=3)
            lab = ttk.Label(f, text="–", font=("Segoe UI", 16))
            lab.pack(padx=8, pady=6)
            self.kpi[name] = lab

        self.states_fr = ttk.Frame(self.root, padding=8)
        self.states_fr.pack(fill="x")

        mid = ttk.Frame(self.root)
        mid.pack(fill="both", expand=True, padx=8, pady=4)
        self.fig = Figure(figsize=(12.2, 4.2), layout="constrained")
        self.canvas = FigureCanvasTkAgg(self.fig, mid)
        self.canvas.get_tk_widget().pack(fill="both", expand=True)

        foot = ttk.Frame(self.root, padding=8)
        foot.pack(fill="x")
        ttk.Label(foot, text="Uji").pack(side="left")
        self.cb_uji = ttk.Combobox(foot, width=28, state="readonly")
        self.cb_uji.pack(side="left", padx=6)
        self.cb_uji.bind("<<ComboboxSelected>>", lambda e: self.show_uji())
        self.uji_lab = ttk.Label(foot, text="")
        self.uji_lab.pack(side="left", padx=8)
        slf = ttk.Frame(foot)
        slf.pack(side="right")
        ttk.Label(slf, text="Peta").pack(side="left")
        self.t0 = tk.IntVar(value=0)
        self.scale = ttk.Scale(slf, from_=0, to=200, variable=self.t0,
                               command=lambda v: self.draw_figs())
        self.scale.pack(side="left", padx=6)

    def pick_folder(self):
        p = filedialog.askdirectory(initialdir=str(self.trials))
        if p:
            self.trials = Path(p)
            self.refresh_samples()

    def pick_zip(self):
        z = filedialog.askopenfilename(filetypes=[("ZIP", "*.zip")])
        if not z:
            return
        import zipfile, tempfile
        dest = Path(tempfile.mkdtemp(prefix="muse2_")) / "u"
        dest.mkdir()
        with zipfile.ZipFile(z) as zf:
            zf.extractall(dest)
        self.trials = dest
        self.refresh_samples()

    def refresh_samples(self):
        inv = list_samples(self.trials) if self.trials.exists() else None
        labs = inv["label"].tolist() if inv is not None and not inv.empty else []
        self.inv = inv
        self.cb["values"] = labs
        if labs:
            self.cb.set(labs[0] if "P02_Trial / experiment" not in labs else "P02_Trial / experiment")
            self.compute()

    def compute(self):
        if self.inv is None or self.inv.empty or not self.cb.get():
            return
        try:
            row = self.inv[self.inv["label"] == self.cb.get()].iloc[0]
            data = load_sample(row["folder"], PROCESSED if PROCESSED.exists() else None)
        except Exception as e:
            messagebox.showerror("Baca data", str(e))
            return
        eeg_f, ppg, bp, meta = data["eeg_f"], data["ppg"], data["bp"], data["meta"]
        tmax = float(eeg_f["time_s"].iloc[-1])
        edges = parse_marks(self.ent_titik.get(), tmax)
        band = self.band.get()
        tab, _ = ruas_stats(bp, edges, band)
        p2, ts = ppg["PPG2"].to_numpy(float), ppg["time_s"].to_numpy(float)
        ses = compute_prv_09(p2, ts)
        tmid = (bp["t_start"] + bp["t_end"]) / 2 if bp is not None and len(bp) else None
        states, tests = [], []
        if tmid is not None:
            feats = []
            for a, b in zip(edges[:-1], edges[1:]):
                w = bp[(tmid >= a) & (tmid < b)]
                hr = compute_prv_09(p2, ts, a, b)
                feats.append((feat_of(w, hr.get("hr", np.nan)), hr, a, b))
            ref = feats[0][0] if feats else {}
            for feat, hr, a, b in feats:
                code = classify(feat, ref)
                states.append({"a": a, "b": b, "lab": NICE[code], "arti": ARTI[code], "hr": hr})
            packs = []
            for a, b in zip(edges[:-1], edges[1:]):
                w = bp[(tmid >= a) & (tmid < b)]
                if f"AF7_{band}" not in w:
                    continue
                l, r = w[f"AF7_{band}"], w[f"AF8_{band}"]
                packs.append((f"{a:.0f}–{b:.0f}", l, r, (l + r) / 2,
                              (r - l) / (l + r).replace(0, np.nan),
                              (w["AF7_beta"] + w["AF8_beta"]) / 2 if "AF7_beta" in w else None))
            for i in range(len(packs) - 1):
                for j in range(i + 1, len(packs)):
                    tests.append({
                        "pair": f"{packs[i][0]} vs {packs[j][0]}",
                        "d_alpha": mw(packs[i][3], packs[j][3]),
                        "d_beta": mw(packs[i][5], packs[j][5]) if packs[i][5] is not None else None,
                        "af7": mw(packs[i][1], packs[j][1]),
                        "af8": mw(packs[i][2], packs[j][2]),
                        "asimetri": mw(packs[i][4], packs[j][4]),
                    })
        ev = (meta.get("eeg_validation") or {}).get("status", "-")
        pv = (meta.get("ppg_validation") or {}).get("status", "-")
        frac = float(eeg_f["artifact_amp"].mean()) if "artifact_amp" in eeg_f.columns else np.nan
        self.pack = dict(eeg_f=eeg_f, ppg=ppg, bp=bp, tab=tab, edges=edges, tmax=tmax,
                         ses=ses, states=states, tests=tests, ev=ev, pv=pv, frac=frac)
        self.scale.configure(to=max(0, int(tmax) - 20))
        self.kpi["Denyut"].config(text=f"{ses['hr']:.0f}" if ses.get("ok") else "–")
        self.kpi["SDNN"].config(text=f"{ses.get('prv_sdnn', float('nan')):.0f}")
        self.kpi["RMSSD"].config(text=f"{ses.get('prv_rmssd', float('nan')):.0f}")
        self.kpi["Durasi"].config(text=f"{tmax:.0f} s")
        self.kpi["EEG/PPG"].config(text=f"{ev}/{pv}")
        self.kpi[">80µV"].config(text=f"{100*frac:.1f}%" if np.isfinite(frac) else "–")
        for w in self.states_fr.winfo_children():
            w.destroy()
        for s in states:
            fr = ttk.LabelFrame(self.states_fr, text=f"{s['a']:.0f}–{s['b']:.0f} s · {s['lab']}")
            fr.pack(side="left", expand=True, fill="x", padx=4)
            ttk.Label(fr, text=s["arti"]).pack(anchor="w", padx=6, pady=4)
        self.cb_uji["values"] = [t["pair"] for t in tests]
        if tests:
            self.cb_uji.set(tests[0]["pair"])
        self.show_uji()
        self.draw_figs()

    def show_uji(self):
        if not self.pack:
            return
        pair = self.cb_uji.get()
        t = next((x for x in self.pack["tests"] if x["pair"] == pair), None)
        if not t:
            self.uji_lab.config(text="")
            return
        def f(x):
            return "n/a" if x is None else f"{x:.3f}"
        self.uji_lab.config(
            text=f"Δα {f(t['d_alpha'])}  Δβ {f(t['d_beta'])}  AF7 {f(t['af7'])}  AF8 {f(t['af8'])}  Asim {f(t['asimetri'])}"
        )

    def draw_figs(self):
        if not self.pack:
            return
        eeg_f, ses, edges = self.pack["eeg_f"], self.pack["ses"], self.pack["edges"]
        bp, tab, band = self.pack["bp"], self.pack["tab"], self.band.get()
        t0 = int(float(self.t0.get()))
        t1v = min(t0 + 20, self.pack["tmax"])
        self.fig.clear()
        gs = self.fig.add_gridspec(2, 2, width_ratios=[1.3, 1.0], height_ratios=[1.2, 1.0])
        ax0 = self.fig.add_subplot(gs[0, 0])
        ax1 = self.fig.add_subplot(gs[1, 0], sharex=ax0)
        for c in CH:
            ax0.plot(eeg_f["time_s"], eeg_f[c], lw=0.3)
        ax0.set_ylim(-80, 80)
        ax0.set_ylabel("EEG")
        tp = ses.get("tp", np.array([]))
        if len(tp) >= 2:
            ax1.plot(tp[:-1], np.diff(tp) * 1000, lw=0.65, color="C1")
        ax1.set_ylim(400, 1500)
        ax1.set_ylabel("IBI")
        for ax in (ax0, ax1):
            for x in edges[1:-1]:
                ax.axvline(x, color="k", ls="--", lw=0.7)
            ax.axvspan(t0, t1v, color="C0", alpha=0.10)
            ax.grid(True, alpha=0.25)
        nmini = max(len(tab), 1) if bp is not None else 1
        cols = 3 if nmini > 3 else max(nmini, 1)
        rows = int(np.ceil(nmini / cols))
        sub = gs[:, 1].subgridspec(1 + rows, cols, height_ratios=[1.3] + [1] * rows)
        axb = self.fig.add_subplot(sub[0, :])
        if bp is not None and len(bp):
            tmid = (bp["t_start"] + bp["t_end"]) / 2
            w = bp[(tmid >= t0) & (tmid < t1v)]
            if len(w) == 0:
                w = bp
            draw_map(axb, {c: float(w[f"{c}_{band}"].median()) for c in CH}, f"{t0:.0f}–{t1v:.0f}s {band}")
            for i, r in tab.iterrows():
                rr, cc = divmod(i, cols)
                ax = self.fig.add_subplot(sub[1 + rr, cc])
                short = r.get("ruas", "")
                if r.get("n_win", 0) > 0:
                    draw_map(ax, {c: float(r[c]) for c in CH}, str(short))
        self.canvas.draw_idle()


def launch():
    root = tk.Tk()
    RisetApp(root)
    root.mainloop()


if __name__ == "__main__":
    launch()
