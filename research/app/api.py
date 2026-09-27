"""Jalankan dari folder app-standalone/muse2-research-app:
PYTHONPATH=src uvicorn app.api:app --port 8000
Lalu buka http://127.0.0.1:8000/
"""
from __future__ import annotations
import io
import sys
from pathlib import Path

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Circle
import zipfile
import tempfile
from fastapi import FastAPI, Query, UploadFile, File
from fastapi.responses import HTMLResponse, JSONResponse, Response, RedirectResponse
from fastapi.middleware.cors import CORSMiddleware

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
    "CALM_RELAXED": "Otak lebih pelan, denyut tidak naik — nuansa istirahat.",
    "FOCUSED_ENGAGED": "Otak lebih siaga, denyut biasa — nuansa memperhatikan.",
    "ACTIVATED_HIGH_AROUSAL": "Otak dan/atau denyut lebih kencang — nuansa terpacu.",
    "INDETERMINATE": "Perubahan terlalu kecil atau campur; tidak memilih tiga label lain.",
}
DEFAULT = Path.home() / "muse2-research" / "data" / "raw" / "trials"
PROCESSED = Path.home() / "muse2-research" / "data" / "processed"
HTML = Path(__file__).with_name("dashboard.html")

app = FastAPI(title="Muse2 Research API")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


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
        return None
    try:
        return float(mannwhitneyu(a, b, alternative="two-sided").pvalue)
    except Exception:
        return None


BUNDLE_CACHE = {}


def bundle(trials: Path, label: str, titik: str, band: str, t0: int):
    key = (str(trials), label, titik, band)
    if key in BUNDLE_CACHE:
        out = dict(BUNDLE_CACHE[key])
        out["t0"] = int(t0)
        out["t1v"] = min(int(t0) + 20, out["tmax"])
        return out
    inv = list_samples(trials)
    row = inv[inv["label"] == label].iloc[0]
    data = load_sample(row["folder"], PROCESSED if PROCESSED.exists() else None)
    eeg_f, ppg, bp, meta = data["eeg_f"], data["ppg"], data["bp"], data["meta"]
    tmax = float(eeg_f["time_s"].iloc[-1])
    edges = parse_marks(titik, tmax)
    tab, _ = ruas_stats(bp, edges, band)
    p2, ts = ppg["PPG2"].to_numpy(float), ppg["time_s"].to_numpy(float)
    ses = compute_prv_09(p2, ts)
    t1v = min(t0 + 20, tmax)
    states = []
    if bp is not None and len(bp):
        tmid = (bp["t_start"] + bp["t_end"]) / 2
        feats = []
        for a, b in zip(edges[:-1], edges[1:]):
            w = bp[(tmid >= a) & (tmid < b)]
            hr = compute_prv_09(p2, ts, a, b)
            feats.append((feat_of(w, hr.get("hr", np.nan)), hr, a, b, w))
        ref = feats[0][0] if feats else {}
        for feat, hr, a, b, w in feats:
            code = classify(feat, ref)
            states.append({
                "t0": a, "t1": b, "code": code, "label": NICE[code], "arti": ARTI[code],
                "hr": hr.get("hr"), "rmssd": hr.get("prv_rmssd"),
            })
    tests = []
    if bp is not None and len(bp) and f"AF7_{band}" in bp.columns:
        tmid = (bp["t_start"] + bp["t_end"]) / 2
        packs = []
        for a, b in zip(edges[:-1], edges[1:]):
            w = bp[(tmid >= a) & (tmid < b)]
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
    frac = float(eeg_f["artifact_amp"].mean()) if "artifact_amp" in eeg_f.columns else None
    out = {
        "eeg_f": eeg_f, "ppg": ppg, "bp": bp, "tab": tab, "edges": edges,
        "tmax": tmax, "t0": t0, "t1v": t1v, "ses": ses, "states": states,
        "tests": tests, "ev": ev, "pv": pv, "frac": frac, "band": band,
    }
    BUNDLE_CACHE[key] = out
    return out


def fig_png(fig) -> bytes:
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=120, bbox_inches="tight", facecolor="white")
    plt.close(fig)
    return buf.getvalue()


LAST_UPLOAD = {"root": None}


def unpack_zip_bytes(data: bytes) -> Path:
    tmp = Path(tempfile.mkdtemp(prefix="muse2_zip_"))
    zpath = tmp / "data.zip"
    zpath.write_bytes(data)
    dest = tmp / "unzip"
    dest.mkdir()
    with zipfile.ZipFile(zpath) as zf:
        zf.extractall(dest)
    hits = list(dest.rglob("EEG_raw.csv"))
    if hits and hits[0].parent.name in ("experiment", "baseline"):
        return hits[0].parents[2] if hits[0].parents[1].name.startswith("P") else dest
    return dest


def filled_dashboard(label="P02_Trial / experiment", titik="60", band="alpha", t0=0, trials=None, uji=""):
    root = Path(trials) if trials else (LAST_UPLOAD["root"] or DEFAULT)
    b = bundle(root, label, titik, band, t0)
    ses = b["ses"]
    raw = HTML.read_text(encoding="utf-8")
    css = raw.split("</style>", 1)[0] + "</style>"
    qs = f"label={label.replace(' ', '%20')}&titik={titik}&band={band}&t0={t0}"
    states = "".join(
        f"<div class='card st'><h3>{s['t0']:.0f}–{s['t1']:.0f} s · "
        f"<span>{s['label']}</span></h3><p>{s['arti']}</p></div>"
        for s in b["states"]
    )
    t = b["tests"][0] if b["tests"] else None

    def fp(x):
        return "n/a" if x is None else f"{x:.3f}"

    pairs = [tt["pair"] for tt in b["tests"]]
    uji_now = uji if uji in pairs else (pairs[0] if pairs else "")
    title = ("Uji " + uji_now) if uji_now else "Uji antar ruas"
    chips = ""
    for tt in b["tests"]:
        if tt["pair"] != uji_now:
            continue
        chips = "".join(
            f"<span class='chip'>{k} <b>p={fp(tt[k2])}</b></span>"
            for k, k2 in [("Δα", "d_alpha"), ("Δβ", "d_beta"), ("AF7", "af7"), ("AF8", "af8"), ("Asim.", "asimetri")]
        )
    uji_opts = "".join(
        f"<option value=\"{p}\"{' selected' if p==uji_now else ''}>{p}</option>"
        for p in pairs
    )
    hr = ses.get("hr") or 0
    frac = b["frac"] if b["frac"] is not None else 0.0
    inv = list_samples(root)
    opts = ""
    if inv is not None and not inv.empty:
        for lab in inv["label"].tolist():
            sel = " selected" if lab == label else ""
            opts += f"<option{sel}>{lab}</option>"
    bandsel = "".join(
        f"<option value='{x}'{' selected' if x==band else ''}>{x}</option>"
        for x in ("delta", "theta", "alpha", "beta")
    )
    return f"""<!DOCTYPE html><html><head><meta charset="utf-8"/>
<title>Muse 2 — Dashboard riset</title>{css}
<style>
  .wrap > .bar {{
    display: flex !important; flex-wrap: nowrap; align-items: stretch; gap: 8px;
    grid-template-columns: none !important;
  }}
  .wrap > .bar .card {{
    display: flex; flex-direction: column; justify-content: center;
    padding: 8px 10px; min-height: 64px;
  }}
  .seg {{ display:flex; flex-wrap: nowrap; gap: 4px; }}
  .seg button {{ padding: 5px 8px; font-size: 11px; }}
  input[type=file] {{ width: 108px; font-size: 11px; }}
  #mainf {{ display: flex; flex: 1; gap: 8px; align-items: stretch; min-width: 0; }}
  #mainf .card {{ flex: 1; min-width: 0; }}
  #mainf .card.tight {{ flex: 0 0 92px; }}
  .seg button {{ min-width: 52px; }}
  select, input[type=text], input:not([type=range]):not([type=file]) {{ min-width: 0; }}
  .foot {{ grid-template-columns: 1.6fr 0.8fr; }}
</style>
</head><body>
<div class="wrap">
  <div class="bar">
    <div class="card">
      <label>Unggah ZIP</label>
      <form action="/upload" method="post" enctype="multipart/form-data">
        <input type="file" name="file" accept=".zip" />
        <button class="btn" type="submit">Pakai</button>
      </form>
    </div>
    <form id="mainf" action="/" method="get">
    <div class="card grow"><label>Sampel</label>
      <select name="label" onchange="this.form.submit()">{opts}</select></div>
    <div class="card"><label>Titik observasi</label>
      <input name="titik" value="{titik}" /></div>
    <div class="card grow"><label>Pita</label>
      <div class="seg">
        <button type="submit" name="band" value="delta" class="{'on' if band=='delta' else ''}">delta</button>
        <button type="submit" name="band" value="theta" class="{'on' if band=='theta' else ''}">theta</button>
        <button type="submit" name="band" value="alpha" class="{'on' if band=='alpha' else ''}">alpha</button>
        <button type="submit" name="band" value="beta" class="{'on' if band=='beta' else ''}">beta</button>
      </div></div>
    <div class="card grow"><label>Peta {t0}s</label>
      <input id="sl" type="range" name="t0" min="0" max="{max(0, int(b['tmax'])-20)}" value="{int(t0)}" /></div>
    <div class="card tight"><button class="btn" type="submit">Terapkan</button></div>
    </form>
  </div>
  <div class="metrics">
    <div class="card metric"><div class="k">Denyut</div><div class="v">{hr:.0f}</div></div>
    <div class="card metric"><div class="k">PRV-SDNN</div><div class="v">{ses.get('prv_sdnn', float('nan')):.0f}</div></div>
    <div class="card metric"><div class="k">PRV-RMSSD</div><div class="v">{ses.get('prv_rmssd', float('nan')):.0f}</div></div>
    <div class="card metric"><div class="k">Durasi</div><div class="v">{b['tmax']:.0f} s</div></div>
    <div class="card metric"><div class="k">EEG/PPG</div><div class="v">{b['ev']}/{b['pv']}</div></div>
    <div class="card metric"><div class="k">&gt;80 µV</div><div class="v">{100*frac:.1f}%</div></div>
  </div>
  <div class="states">{states}</div>
  <div class="main">
    <div class="pane"><img id="img-tr" src="/api/fig/traces.png?{qs}" style="width:100%;height:100%;object-fit:contain"/></div>
    <div class="pane"><img id="img-mp" src="/api/fig/maps.png?{qs}" style="width:100%;height:100%;object-fit:contain"/></div>
  </div>
  <div class="foot">
    <div class="stats">
      <div style="display:flex;align-items:center;gap:10px;flex-wrap:wrap">
        <strong>{title}</strong>
        <select name="uji" form="mainf" onchange="this.form.submit()">{uji_opts}</select>
      </div>
      <div class="chips">{chips}</div>
    </div>
    <div class="card legend">
      <div style="font-size:12px;margin-bottom:8px">Skala peta · {band}</div>
      <div style="height:14px;width:100%;border-radius:99px;border:1px solid #ddd;
                  background:linear-gradient(90deg,#313695 0%,#74add1 25%,#ffffbf 50%,#f46d43 75%,#a50026 100%)"></div>
      <div style="display:flex;justify-content:space-between;width:100%;font-size:11px;margin-top:6px">
        <span>Rendah</span><span>Tinggi</span>
      </div>
    </div>
  </div>
</div>
<script>
const sl = document.getElementById('sl');
const tr = document.getElementById('img-tr');
const mp = document.getElementById('img-mp');
function bump(url, t) {{
  url = url.replace(/t0=\\d+/, 't0=' + t);
  if (!url.includes('t0=')) url += (url.includes('?') ? '&' : '?') + 't0=' + t;
  return url.replace(/&_=.*/, '') + '&_=' + Date.now();
}}
if (sl) sl.addEventListener('change', () => {{
  const t = sl.value;
  if (tr) tr.src = bump(tr.src, t);
  if (mp) mp.src = bump(mp.src, t);
}});
</script>
</body></html>"""


@app.get("/")
def home(label: str = "P02_Trial / experiment", trials: str = "", titik: str = "60", band: str = "alpha", t0: int = 0, uji: str = ""):
    try:
        html = filled_dashboard(label, titik=titik, band=band, t0=t0, trials=trials or None, uji=uji)
    except Exception as e:
        return HTMLResponse(f"<pre>ERROR {e}</pre>")
    return HTMLResponse(html, headers={"Cache-Control": "no-store"})


@app.post("/upload")
async def upload(file: UploadFile = File(...)):
    raw = await file.read()
    root = unpack_zip_bytes(raw)
    LAST_UPLOAD["root"] = root
    inv = list_samples(root)
    label = inv["label"].iloc[0] if inv is not None and not inv.empty else "P02_Trial / experiment"
    return RedirectResponse(url=f"/?label={label}", status_code=303)


@app.get("/simple")
def simple(label: str = "P02_Trial / experiment"):
    try:
        b = bundle(DEFAULT, label, "60", "alpha", 0)
    except Exception as e:
        return HTMLResponse(f"<pre>ERROR {e}</pre>")
    ses = b["ses"]
    rows = "".join(
        f"<li>{s['t0']:.0f}–{s['t1']:.0f}s {s['label']} HR={s['hr']}</li>"
        for s in b["states"]
    )
    tes = b["tests"][:1]
    return HTMLResponse(
        f"<h2>{label}</h2><p>Denyut {ses.get('hr')} RMSSD {ses.get('prv_rmssd')}</p>"
        f"<ul>{rows}</ul><pre>{tes}</pre>"
        f"<p><a href='/'>Dashboard</a></p>"
    )


def trials_path(trials: str | None) -> Path:
    raw = (trials or "").strip()
    p = Path(raw) if raw else DEFAULT
    return p if p.exists() else DEFAULT


@app.get("/api/samples")
def samples(trials: str = Query(default="")):
    candidates = [
        trials_path(trials),
        DEFAULT,
        Path.home() / "muse2-research" / "data" / "raw" / "trials",
        Path.home() / "Library/CloudStorage/OneDrive-Personal/2. PROJECT/0. LPPM 2026/2. HRP/DATA PENELITIAN/Raw Data",
    ]
    debug = []
    seen = set()
    for root in candidates:
        key = str(root)
        if key in seen:
            continue
        seen.add(key)
        inv = list_samples(root) if root.exists() else None
        n = 0 if inv is None or inv.empty else int(len(inv))
        debug.append({"root": key, "exists": bool(root.exists()), "n": n})
        if n:
            return {"trials": key, "labels": inv["label"].tolist(), "debug": debug}
    return {"trials": str(trials_path(trials)), "labels": [], "debug": debug}


@app.get("/api/view")
def view(
    trials: str = Query(default=str(DEFAULT)),
    label: str = "P02_Trial / experiment",
    titik: str = "60",
    band: str = "alpha",
    t0: int = 0,
):
    try:
        b = bundle(trials_path(trials), label, titik, band, t0)
    except Exception as e:
        return JSONResponse({"error": str(e), "label": label}, status_code=200)
    ses = b["ses"]

    def fnum(x):
        return None if x is None or (isinstance(x, float) and not np.isfinite(x)) else (float(x) if not isinstance(x, str) else x)

    return JSONResponse({
        "tmax": b["tmax"],
        "denyut": fnum(ses.get("hr")),
        "sdnn": fnum(ses.get("prv_sdnn")),
        "rmssd": fnum(ses.get("prv_rmssd")),
        "eeg": b["ev"],
        "ppg": b["pv"],
        "frac": fnum(b["frac"]),
        "states": [
            {**s, "hr": fnum(s["hr"]), "rmssd": fnum(s["rmssd"])}
            for s in b["states"]
        ],
        "tests": b["tests"],
    })


@app.get("/api/fig/traces.png")
def traces(
    trials: str = Query(default=str(DEFAULT)),
    label: str = "P02_Trial / experiment",
    titik: str = "60",
    band: str = "alpha",
    t0: int = 0,
):
    b = bundle(trials_path(trials), label, titik, band, t0)
    eeg_f, edges, t0, t1v, ses = b["eeg_f"], b["edges"], b["t0"], b["t1v"], b["ses"]
    fig, axes = plt.subplots(2, 1, figsize=(7.2, 2.4), sharex=True, layout="constrained")
    for c in CH:
        axes[0].plot(eeg_f["time_s"], eeg_f[c], lw=0.3)
    axes[0].set_ylim(-80, 80)
    axes[0].set_ylabel("EEG")
    tp = ses.get("tp", np.array([]))
    if len(tp) >= 2:
        axes[1].plot(tp[:-1], np.diff(tp) * 1000, lw=0.65, color="C1")
    axes[1].set_ylim(400, 1500)
    axes[1].set_ylabel("IBI")
    for ax in axes:
        for x in edges[1:-1]:
            ax.axvline(x, color="k", ls="--", lw=0.7)
        ax.axvspan(t0, t1v, color="C0", alpha=0.10)
        ax.grid(True, alpha=0.25)
    return Response(fig_png(fig), media_type="image/png")


@app.get("/api/fig/maps.png")
def maps(
    trials: str = Query(default=str(DEFAULT)),
    label: str = "P02_Trial / experiment",
    titik: str = "60",
    band: str = "alpha",
    t0: int = 0,
):
    b = bundle(trials_path(trials), label, titik, band, t0)
    bp, tab, states, t0, t1v, band = b["bp"], b["tab"], b["states"], b["t0"], b["t1v"], b["band"]
    nmini = max(len(tab), 1) if bp is not None else 1
    cols = 3 if nmini > 3 else max(nmini, 1)
    rows_mini = int(np.ceil(nmini / cols))
    fig = plt.figure(figsize=(5.2, 2.2 + 1.15 * rows_mini), layout="constrained")
    gs = fig.add_gridspec(1 + rows_mini, cols, height_ratios=[1.35] + [1.0] * rows_mini)
    axb = fig.add_subplot(gs[0, :])
    if bp is not None and len(bp):
        tmid = (bp["t_start"] + bp["t_end"]) / 2
        w = bp[(tmid >= t0) & (tmid < t1v)]
        if len(w) == 0:
            w = bp
        draw_map(axb, {c: float(w[f"{c}_{band}"].median()) for c in CH}, f"{t0:.0f}–{t1v:.0f}s {band}")
        for i, r in tab.iterrows():
            rr, cc = divmod(i, cols)
            ax = fig.add_subplot(gs[1 + rr, cc])
            lab = states[i]["label"] if i < len(states) else ""
            short = {"Tenang": "T", "Fokus": "F", "Teraktivasi": "A", "Indeterminan": "I"}.get(lab, lab[:1])
            title = f"{r['t0']:.0f}–{r['t1']:.0f} {short}"
            if r.get("n_win", 0) > 0:
                draw_map(ax, {c: float(r[c]) for c in CH}, title)
    return Response(fig_png(fig), media_type="image/png")
