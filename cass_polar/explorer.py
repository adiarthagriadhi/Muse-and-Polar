"""CASS Wellness Explorer for Muse–Polar recordings.

Template and payload builder taken from build_explorer.py of the CASS Wellness toolkit so the
page looks and behaves the same. Changes: Y evidence comes from Polar H10 RR (columns
polar_rr_rmssd / polar_hr / polar_n_ibi, labels "RR Polar" instead of "PRV"), and
explorer_payload() builds the payload straight from a musepolar session folder.

Bangun Wellness Explorer HTML UTUH dari template.

Berbeda dari rantai v2->v5.6 di NB10: tidak ada regex, tidak ada tambalan.
Payload masuk sebagai satu blok JSON; seluruh struktur halaman ditulis sekali.
Kalau ada yang perlu diubah, ubah template ini, lalu bangun ulang.
"""
import json
from pathlib import Path
import numpy as np
import pandas as pd

CHANNELS = ["TP9", "AF7", "AF8", "TP10"]
QUAD_POS = {"AF7": (0, 0), "AF8": (0, 1), "TP9": (1, 0), "TP10": (1, 1)}
Y_COLS = ("polar_rr_rmssd", "polar_hr", "polar_n_ibi")


def _num(v):
    v = float(v)
    return None if not np.isfinite(v) else round(v, 6)


def build_payload(state, refs, sid, marker_s, ruas_s=30.0):
    global Y_COLS
    Y_COLS = (("polar_rr_rmssd", "polar_hr", "polar_n_ibi") if "polar_rr_rmssd" in state
              else ("ppg2_prv_rmssd", "ppg2_hr", "ppg2_n_ibi"))
    """marker_s boleh None — artinya sesi diunggah tanpa marker dan
    seluruh rekaman menjadi satu ruas (R0) di explorer."""
    windows = []
    for _, r in state.iterrows():
        w = {
            "id": int(r["window_id"]),
            "t0": _num(r["window_start"]),
            "t1": _num(r["window_end"]),
            "tm": _num(r["window_mid"]),
            "phase": str(r["phase"]),
            "cortical": _num(r["cortical_state"]),
            "autonomic": _num(r["autonomic_state"]),
            "autonomic_valid": bool(r["autonomic_valid"]),
            "quadrant": str(r["quadrant"]),
            "dist": _num(r["distance_reference"]),
            "rmssd": _num(r[Y_COLS[0]]),
            "hr": _num(r[Y_COLS[1]]),
            "n_ibi": int(r[Y_COLS[2]]),
            "ch": {c: {"z": _num(r[f"{c}_cortical_raw_z"]),
                       "raw": _num(r[f"{c}_cortical_raw"]),
                       "dev": _num(r[f"{c}_deviation"])} for c in CHANNELS},
        }
        windows.append(w)

    # Ruas (segment) untuk heatmap kuadran kepala
    seg_lo = np.floor(state["window_mid"] / ruas_s) * ruas_s
    labels = [f"{int(a)}–{int(a + ruas_s)}s" for a in sorted(seg_lo.unique())]
    seg_of = {int(r["window_id"]): f"{int(lo)}–{int(lo + ruas_s)}s"
              for (_, r), lo in zip(state.iterrows(), seg_lo)}

    grid_mean, grid_dom = {}, {}
    for lab in labels:
        ids = [i for i, s in seg_of.items() if s == lab]
        d = state[state["window_id"].isin(ids)]
        grid_mean[lab] = {c: _num(d[f"{c}_cortical_raw_z"].mean()) for c in CHANNELS}
        z = d[[f"{c}_cortical_raw_z" for c in CHANNELS]].to_numpy(float)
        valid = np.isfinite(z).all(axis=1)
        if valid.sum():
            win_idx = np.argmax(z[valid], axis=1)
            grid_dom[lab] = {c: round(float((win_idx == k).sum() / valid.sum()), 6)
                             for k, c in enumerate(CHANNELS)}
        else:
            grid_dom[lab] = {c: None for c in CHANNELS}

    # Okupansi kuadran CASS per fase
    occ = {}
    for phase in ["PRE", "POST", "ALL"]:
        d = state if phase == "ALL" else state[state["phase"] == phase]
        x = pd.to_numeric(d["cortical_state"], errors="coerce").to_numpy(float)
        y = pd.to_numeric(d["autonomic_state"], errors="coerce").to_numpy(float)
        ok = np.isfinite(x) & np.isfinite(y)
        xc, yc = np.clip(x[ok], -3, 3), np.clip(y[ok], -3, 3)
        H, _, _ = np.histogram2d(xc, yc, bins=[np.linspace(-3, 3, 13)] * 2)
        n = int(ok.sum())
        occ[phase] = {
            "n_valid": n, "n_total": int(len(d)), "n_excluded": int(len(d) - n),
            "grid": H.T.astype(int).tolist(),
            "q": {"Q1": int(((xc >= 0) & (yc >= 0)).sum()),
                  "Q2": int(((xc < 0) & (yc >= 0)).sum()),
                  "Q3": int(((xc < 0) & (yc < 0)).sum()),
                  "Q4": int(((xc >= 0) & (yc < 0)).sum())},
        }

    tmax = float(state["window_end"].max()) if len(state) else float(marker_s or 0.0)
    n_y = int(state["autonomic_valid"].sum()) if "autonomic_valid" in state else 0
    return {
        "contract": "CASS_WELLNESS_STATE_CONTRACT_0.1",
        "session_id": sid,
        "marker_s": None if marker_s is None else float(marker_s),
        "default_marker_s": None if marker_s is None else float(marker_s),
        "tmax_s": tmax,
        "n_windows": int(len(state)),
        "n_y_valid": n_y,
        "ruas_s": float(ruas_s),
        "window_s": refs.get("window_s"),
        "step_s": refs.get("step_s"),
        "cortical_metric": refs.get("cortical_metric"),
        "autonomic_scalar": refs.get("autonomic_scalar"),
        "min_ibi": refs.get("min_ibi"),
        "channels": CHANNELS,
        "quad_pos": QUAD_POS,
        "seg_labels": labels,
        "grid_mean": grid_mean,
        "grid_dominance": grid_dom,
        "occupancy": occ,
        "windows": windows,
    }


TEMPLATE = r"""<!DOCTYPE html>
<html lang="id">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>CASS Wellness Explorer</title>
<style>
  :root{
    color-scheme: light;
    --surface:#fcfcfb; --plane:#f9f9f7; --ink:#0b0b0b; --ink2:#52514e;
    --muted:#898781; --grid:#e1e0d9; --axis:#c3c2b7;
    --accent:#2a78d6; --border:rgba(11,11,11,.10);
    --pri:rgba(42,120,214,.30);
  }
  @media (prefers-color-scheme: dark){
    :root:not([data-theme="light"]){
      color-scheme: dark;
      --surface:#1a1a19; --plane:#0d0d0d; --ink:#fff; --ink2:#c3c2b7;
      --muted:#898781; --grid:#2c2c2a; --axis:#383835;
      --accent:#3987e5; --border:rgba(255,255,255,.10);
      --pri:rgba(57,135,229,.45);
    }
  }
  :root[data-theme="dark"]{
    color-scheme: dark;
    --surface:#1a1a19; --plane:#0d0d0d; --ink:#fff; --ink2:#c3c2b7;
    --muted:#898781; --grid:#2c2c2a; --axis:#383835;
    --accent:#3987e5; --border:rgba(255,255,255,.10);
    --pri:rgba(57,135,229,.45);
  }
  *{box-sizing:border-box;margin:0}
  html,body{height:100%}
  body{background:var(--plane);color:var(--ink);overflow:hidden;
    font:13px/1.35 system-ui,-apple-system,"Segoe UI",sans-serif;
    display:grid;grid-template-rows:auto minmax(0,1fr) auto;
    grid-template-columns:minmax(0,1fr);gap:8px;padding:8px 11px}

  /* ---------- topbar ---------- */
  .bar{background:var(--surface);border:1px solid var(--border);border-radius:10px;
    padding:6px 12px;display:flex;align-items:center;gap:14px;flex-wrap:nowrap;position:relative}
  .bar h1{font:650 15px/1 Georgia,"Source Serif 4",serif;white-space:nowrap;flex:0 0 auto}
  /* chip boleh menyusut dan digeser; tombol dan pemilih peserta tidak pernah turun baris */
  .chips{flex:1 1 auto;min-width:0;display:flex;gap:14px;overflow-x:auto;
    scrollbar-width:none;-ms-overflow-style:none}
  .chips::-webkit-scrollbar{display:none}
  .acts{flex:0 0 auto;display:flex;gap:6px;margin-left:auto}
  .chip{font-size:10.5px;color:var(--muted);white-space:nowrap}
  .chip b{display:block;font-size:13px;color:var(--ink);font-variant-numeric:tabular-nums;
    font-weight:650;max-width:200px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
  .chip b.warn{color:#d03b3b}
  .btn{background:var(--accent);color:#fff;border:0;border-radius:7px;padding:6px 11px;
    font:600 11.5px/1 system-ui;cursor:pointer;white-space:nowrap}
  .btn.g{background:transparent;color:var(--ink2);border:1px solid var(--axis)}
  #partWrap{display:flex;align-items:center;gap:6px;flex:0 0 auto}
  #partWrap[hidden]{display:none}
  #partWrap span{font-size:10.5px;color:var(--muted)}
  select{background:var(--plane);color:var(--ink);border:1px solid var(--axis);
    border-radius:7px;padding:5px 8px;font:600 12px/1 system-ui;max-width:220px}

  /* ---------- popover marker ---------- */
  .pop{position:absolute;top:calc(100% + 6px);right:0;z-index:20;width:min(520px,92vw);
    background:var(--surface);border:1px solid var(--axis);border-radius:12px;
    padding:12px 14px;box-shadow:0 10px 30px rgba(0,0,0,.18);max-height:72vh;overflow:auto}
  .pop[hidden]{display:none}
  .pop h3{font:600 12px/1.3 system-ui;margin-bottom:6px}
  .evrow{display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin:6px 0}
  .evrow input[type=number],.evrow input[type=text]{padding:6px 8px;border:1px solid var(--axis);
    border-radius:8px;background:var(--plane);color:var(--ink);font-size:12px}
  .evrow input[type=number]{width:92px}
  .evrow input[type=text]{width:150px}
  .tag{font-size:10.5px;border:1px solid var(--axis);border-radius:999px;padding:2px 8px;color:var(--ink2)}
  .ghost{background:transparent;border:1px solid var(--axis);color:var(--ink2);
    border-radius:8px;padding:6px 10px;cursor:pointer;font-size:11.5px}
  .danger{color:#b42318;border:1px solid #e8b4b0;background:transparent;
    border-radius:8px;padding:5px 9px;cursor:pointer;font-size:11.5px}
  .note{font-size:11px;color:var(--muted);line-height:1.55}

  /* ---------- grid utama: satu layar, tanpa scroll halaman ---------- */
  /* Kolom okupansi dibuat seukuran bujur sangkarnya saja — lebih lebar dari itu
     hanya menambah margin kosong, karena sisi bujur sangkar dikunci tinggi baris. */
  .grid{display:grid;gap:8px;min-height:0;
    grid-template-rows:clamp(136px,16.5vh,164px) minmax(0,1fr) auto;
    grid-template-columns:minmax(0,.85fr) minmax(0,1.5fr) minmax(0,1.15fr)}
  .panel{background:var(--surface);border:1px solid var(--border);border-radius:10px;
    padding:6px 9px;display:flex;flex-direction:column;min-height:0;min-width:0;overflow:hidden}
  /* hanya .plot yang boleh mengalah; slider, keterangan dan KPI jangan terpotong */
  .panel > .ph, .panel > input[type=range], .panel > .cap, .panel > .kpi{flex:none}
  .panel.pri{border-color:var(--pri);box-shadow:0 0 0 1px var(--pri) inset}
  .banner{grid-column:1/4;grid-row:1}
  .strip{grid-column:1/4;grid-row:3;max-height:168px}

  .ph{display:flex;align-items:center;gap:7px;margin-bottom:3px;min-height:16px}
  .ph h2{font:600 10.5px/1 system-ui;letter-spacing:.055em;text-transform:uppercase;
    color:var(--muted);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
  /* judul banner memuat rumus (log β/α, ±domain) — huruf besar paksa membuatnya salah baca */
  #headTitle{text-transform:none;letter-spacing:0;font-size:11px;font-weight:600}
  .ph .pill{background:var(--accent);color:#fff;border-radius:4px;padding:2px 6px;
    font:600 9px/1.4 system-ui;letter-spacing:.04em}
  .seg{margin-left:auto;display:flex;gap:3px;flex-wrap:nowrap}
  .seg label{border:1px solid var(--axis);border-radius:5px;padding:2px 7px;
    font-size:10px;color:var(--ink2);cursor:pointer;white-space:nowrap;user-select:none}
  .seg label.on{background:var(--accent);color:#fff;border-color:var(--accent)}
  .seg input{position:absolute;opacity:0;pointer-events:none;width:0;height:0}

  .plot{flex:1;min-height:0;min-width:0;position:relative}
  .plot svg{position:absolute;inset:0;width:100%;height:100%;display:block}
  .cap{font-size:10.5px;color:var(--muted);margin-top:3px;line-height:1.35;
    white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
  .cap b{color:var(--ink)}
  .cap .warn{color:#d03b3b}

  input[type=range]{width:100%;accent-color:var(--accent);margin-top:3px;height:14px}

  /* satu baris yang bisa digeser — versi grid dulu memakan 4 baris di layar
     pendek dan menggencet state map sampai hampir hilang */
  .kpi{display:flex;gap:11px;margin-top:3px;overflow-x:auto;
    scrollbar-width:none;-ms-overflow-style:none}
  .kpi::-webkit-scrollbar{display:none}
  .kpi div{font-size:9.5px;color:var(--muted);white-space:nowrap;flex:0 0 auto}
  .kpi div b{display:block;font-size:12.5px;color:var(--ink);font-weight:650;
    font-variant-numeric:tabular-nums}
  .kpi div b.warn{color:#d03b3b}

  /* ringkasan antar-ruas: scroll lokal saat ruas bertambah */
  .scroll{flex:1;min-height:0;overflow:auto}
  table{border-collapse:separate;border-spacing:0;width:100%;font-size:11px}
  th,td{text-align:left;padding:2px 8px;border-bottom:1px solid var(--grid);white-space:nowrap}
  th{color:var(--muted);font-weight:600;position:sticky;top:0;z-index:2;
    background:var(--surface)}
  td.num,th.num{text-align:right;font-variant-numeric:tabular-nums}
  tbody td:first-child,thead th:first-child{position:sticky;left:0;z-index:1;
    background:var(--surface)}
  thead th:first-child{z-index:3}
  tr:last-child td{border-bottom:0}

  .foot{background:var(--surface);border:1px solid var(--border);border-radius:10px;
    padding:5px 12px;font-size:10.5px;color:var(--muted);line-height:1.45}
  .foot b{color:var(--ink2)}

  /* ---------- cetak / simpan PDF ----------
     Halaman 1 = dashboard apa adanya, lanskap. Halaman 2 = ringkasan + tabel
     antar-ruas utuh (di layar tabel itu ter-scroll). Palet dipaksa terang:
     tema gelap memboroskan tinta dan ramp sekuensialnya terbalik di kertas. */
  .sheet{display:none}
  @media print{
    :root, :root[data-theme="dark"], :root:not([data-theme="light"]){
      color-scheme: light;
      --surface:#ffffff; --plane:#ffffff; --ink:#000000; --ink2:#333333;
      --muted:#666666; --grid:#e3e3e3; --axis:#9a9a9a;
      --accent:#1f5fae; --border:#c9c9c9; --pri:#9ab8dd;
    }
    *{-webkit-print-color-adjust:exact;print-color-adjust:exact}
    html,body{height:auto;overflow:visible}
    body{display:block;padding:0;background:#fff;gap:0}
    .acts,.pop,input[type=range]{display:none!important}
    .bar{border:0;box-shadow:none;padding:0 0 3mm;margin:0}
    .bar h1{font-size:13px}
    .chips{overflow:visible;flex-wrap:wrap}
    .grid{height:158mm;gap:3mm;margin:0}
    .panel{break-inside:avoid;box-shadow:none}
    .seg{display:none}
    /* di kertas tidak ada yang bisa digeser atau di-hover: semua harus tampak utuh */
    .kpi,.chips{overflow:visible;flex-wrap:wrap}
    .cap{white-space:normal;overflow:visible;text-overflow:clip}
    #partWrap select{border:0;background:none;padding:0;font-weight:650;
      max-width:none;-webkit-appearance:none;appearance:none}
    .strip{max-height:none}
    .scroll{overflow:visible}
    .foot{margin-top:3mm;break-inside:avoid}
    .sheet{display:block;break-before:page;page-break-before:always}
    .sheet h2{font:650 14px/1.3 Georgia,serif;margin:0 0 2mm}
    .sheet h3{font:600 10.5px/1.3 system-ui;letter-spacing:.04em;
      text-transform:uppercase;color:#555;margin:4mm 0 1.5mm}
    .sheet p,.sheet li{font-size:10px;line-height:1.5;color:#111}
    .sheet ul{margin:0;padding-left:5mm}
    .sheet .meta{font-size:9.5px;color:#666;margin-bottom:1mm}
    .sheet table{font-size:9.5px;margin-top:1.5mm}
    .sheet th,.sheet td{border-bottom:1px solid #ddd;padding:1.2mm 2mm}
    .sheet .flag{border-left:3px solid #b42318;background:#fdf3f2;
      padding:2mm 3mm;margin:1.5mm 0;font-size:10px;color:#6b1a12}
    .sheet .note2{font-size:9px;color:#555;line-height:1.5;margin-top:1mm}
    .sheet .tafsir-hd{font-size:9.5px;color:#555;background:#f4f6f8;
      border-left:3px solid #1f5fae;padding:2mm 3mm;margin:0 0 2mm}
    .sheet ul.tafsir li{margin-bottom:2mm}
    .sheet ul.tafsir u{text-decoration:none;font-weight:600;color:#1f5fae}
    /* seluruh bagian teknis jadi satu blok; pindah utuh ke halaman berikutnya
       kalau tidak muat, bukan terbelah di tengah */
    .sheet .metode{break-inside:avoid;page-break-inside:avoid;margin-top:5mm;
      border-top:1.5px solid #bbb;padding-top:3mm}
    .sheet h4{font:600 10px/1.3 system-ui;color:#222;margin:3mm 0 1mm}
    .sheet .metode p{font-size:9.5px;line-height:1.5}
    .sheet table.kamus{margin-top:2mm;font-size:9px}
    .sheet table.kamus tr.hi td{background:#eef3fa;font-weight:600}
  }
  @page{size:A4 landscape;margin:8mm}
</style>
</head>
<body>

<div class="bar">
  <h1>CASS Wellness</h1>
  <div id="partWrap" hidden><span>Peserta</span><select id="partSel"></select></div>
  <div id="barChips" class="chips"></div>
  <div class="acts">
    <button class="btn" id="markBtn" type="button">Marker &amp; ruas &#9662;</button>
    <button class="btn g" id="pdfBtn" type="button" title="Simpan sebagai PDF lewat dialog cetak">PDF</button>
    <button class="btn g" id="themeBtn" type="button">Tema</button>
  </div>

  <div class="pop" id="markPop" hidden>
    <h3>Rantai marker &mdash; ruas pengamatan</h3>
    <p class="note">n marker memotong rekaman menjadi n+1 ruas berurutan. z robust selalu dari
      <b>ruas pertama</b> (R0). Tanpa marker, seluruh rekaman adalah R0. Marker berlaku
      untuk peserta yang sedang dipilih saja.</p>
    <div id="eventList"></div>
    <div class="evrow">
      <input id="newEvT" type="number" step="0.5" placeholder="detik">
      <input id="newEvL" type="text" placeholder="label (opsional)">
      <button class="btn" id="addEv" type="button">Tambah marker</button>
      <button class="ghost" id="resetMark" type="button">Reset ke marker asal</button>
    </div>
    <div class="note" id="segLegend"></div>
  </div>
</div>

<div class="grid">

  <!-- BARIS 1 : heatmap kuadran kepala, selebar layar -->
  <div class="panel banner">
    <div class="ph"><h2 id="headTitle">Heatmap kuadran kepala</h2>
      <div class="seg" id="hmodeSeg">
        <label><input type="radio" name="hmode" value="raw">log &beta;/&alpha; mutlak</label>
        <label class="on"><input type="radio" name="hmode" value="mean" checked>z vs R0</label>
        <label><input type="radio" name="hmode" value="dom">dominansi %</label>
      </div>
    </div>
    <div class="plot"><svg id="headSvg" role="img"
      aria-label="Heatmap kuadran kepala terhadap ruas waktu"></svg></div>
  </div>

  <!-- BARIS 2 KIRI : state map + window terpilih -->
  <div class="panel">
    <div class="ph"><h2>State map CASS</h2></div>
    <div class="plot"><svg id="mapSvg" role="img"
      aria-label="Peta state CASS: sumbu X cortical, sumbu Y autonomic"></svg></div>
    <input id="slider" type="range" min="0" value="0">
    <div class="cap" id="winLabel"></div>
    <div class="kpi" id="kpi"></div>
  </div>

  <!-- BARIS 2 KANAN : OKUPANSI (peta utama) -->
  <div class="panel pri">
    <div class="ph"><span class="pill">UTAMA</span><h2>Okupansi kuadran CASS</h2>
      <div class="seg" id="occSeg">
        <label class="on"><input type="checkbox" id="occDens" checked>kontur</label>
        <label class="on"><input type="checkbox" id="occLayer" checked>per ruas</label>
        <label class="on"><input type="checkbox" id="occPts" checked>titik</label>
      </div>
      <div class="seg" id="occPhase" style="margin-left:6px"></div>
    </div>
    <div class="plot"><svg id="occSvg" role="img"
      aria-label="Heatmap okupansi bidang CASS dengan empat kuadran"></svg></div>
    <div class="cap" id="occNote"></div>
  </div>

  <!-- BARIS 2 KANAN : lintasan waktu — X dan Y sebagai fungsi waktu kontinu -->
  <div class="panel">
    <div class="ph"><h2>Lintasan waktu &middot; X dan Y</h2>
      <div class="seg" id="tmodeSeg">
        <label class="on"><input type="checkbox" id="tRuas" checked>warna ruas</label>
        <label class="on"><input type="checkbox" id="tPts" checked>titik</label>
      </div>
    </div>
    <div class="plot"><svg id="timeSvg" role="img"
      aria-label="Cortical state dan autonomic state sebagai fungsi waktu"></svg></div>
    <div class="cap" id="timeNote"></div>
  </div>

  <!-- BARIS 3 : ringkasan antar-ruas, mendatar, scroll lokal -->
  <div class="panel strip">
    <div class="ph"><h2>Ringkasan antar-ruas &middot; deskriptif vs R0</h2>
      <span class="cap" id="statTest" style="margin-left:auto;flex:0 1 auto"></span></div>
    <div class="scroll" id="statBlock"></div>
  </div>

</div>

<div class="foot" id="contract"></div>

<!-- Halaman kedua PDF. display:none di layar; tata letak layar tidak berubah. -->
<div class="sheet" id="printSheet" aria-hidden="true"></div>
<script id="payload" type="application/json">__PAYLOAD__</script>
<script>
/* Muatan boleh satu sesi (objek) atau beberapa peserta (larik objek).
   Rumus tidak dihitung ulang di sini — semuanya datang dari NB06 + NB10. */
const BUNDLE = JSON.parse(document.getElementById("payload").textContent);
const SESSIONS = Array.isArray(BUNDLE) ? BUNDLE : [BUNDLE];

let D = null, W = null, CH = null;
let si = 0, idx = 0, rawLim = 1;
let splits = [], splitLabels = {};
const MARK = SESSIONS.map(s => ({
  splits: (s.default_marker_s === null || s.default_marker_s === undefined) ? [] : [Number(s.default_marker_s)],
  labels: (s.default_marker_s === null || s.default_marker_s === undefined) ? {} : {[Number(s.default_marker_s)]: "asal"},
}));

const CHLABEL = {AF7:"Frontal Kiri · AF7", AF8:"Frontal Kanan · AF8",
                 TP9:"Posterior Kiri · TP9", TP10:"Posterior Kanan · TP10"};
const ROWS = ["AF7","AF8","TP9","TP10"];
const QLAB = {Q1:"Q1 · cortical↑ / autonomic↑", Q2:"Q2 · cortical↓ / autonomic↑",
              Q3:"Q3 · cortical↓ / autonomic↓", Q4:"Q4 · cortical↑ / autonomic↓"};

const esc = s => String(s).replace(/[&<>"']/g, c =>
  ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const fx = (v,d=2) => (v===null||v===undefined||!isFinite(v)) ? "—"
  : (v>=0?"+":"") + Number(v).toFixed(d);
const fu = (v,d=2) => (v===null||v===undefined||!isFinite(v)) ? "—" : Number(v).toFixed(d);

/* ---------- warna ---------- */
function lerp(a,b,t){return Math.round(a+t*(b-a));}
function ramp(stops, t){
  t = Math.max(0, Math.min(1, t));
  const n = stops.length - 1, i = Math.min(n-1, Math.floor(t*n)), f = t*n - i;
  const [r1,g1,b1] = stops[i], [r2,g2,b2] = stops[i+1];
  return `rgb(${lerp(r1,r2,f)},${lerp(g1,g2,f)},${lerp(b1,b2,f)})`;
}
/* Sekuensial: langkah paling dekat nol harus MENYATU dengan permukaan.
   Di terang itu berarti hampir putih; di gelap berarti hampir hitam —
   jadi ramp-nya dibalik per mode, bukan sekadar dipakai ulang. */
const SEQ_LIGHT = [[252,252,251],[205,226,251],[109,167,236],[37,106,191],[13,54,107]];
const SEQ_DARK  = [[26,26,25],[24,79,149],[42,120,214],[109,167,236],[205,226,251]];
const DIV = [[13,54,107],[57,135,229],[205,226,251],[240,239,236],
             [244,167,167],[227,73,72],[122,30,31]];
let PRINTING = false;
function isDark(){
  if(PRINTING) return false;          // kertas selalu terang
  const t = document.documentElement.getAttribute("data-theme");
  if(t === "dark") return true;
  if(t === "light") return false;
  return window.matchMedia("(prefers-color-scheme: dark)").matches;
}
const seqColor = t => ramp(isDark() ? SEQ_DARK : SEQ_LIGHT, t);
const divColor = v => ramp(DIV, (Math.max(-3,Math.min(3,v)) + 3) / 6);
const inkOn = rgb => {
  const m = rgb.match(/\d+/g).map(Number);
  return (0.299*m[0]+0.587*m[1]+0.114*m[2]) < 140 ? "#fff" : "#0b0b0b";
};

/* ---------- statistik deskriptif ---------- */
function median(a){
  const x=a.filter(v=>v!==null && isFinite(v)).slice().sort((p,q)=>p-q);
  if(!x.length) return null;
  const m=Math.floor(x.length/2);
  return x.length%2 ? x[m] : (x[m-1]+x[m])/2;
}
function robustLS(a){
  const x=a.filter(v=>v!==null && isFinite(v));
  if(!x.length) return {loc:null, scale:1};
  const loc=median(x);
  const mad=median(x.map(v=>Math.abs(v-loc)));
  let scale = 1.4826*(mad||0);
  if(!isFinite(scale) || scale<1e-12){
    const m=x.reduce((s,v)=>s+v,0)/x.length;
    scale=Math.sqrt(x.reduce((s,v)=>s+(v-m)*(v-m),0)/Math.max(1,x.length-1));
  }
  if(!isFinite(scale) || scale<1e-12) scale=1;
  return {loc, scale};
}
function erf(z){
  const s=z<0?-1:1; z=Math.abs(z);
  const t=1/(1+0.3275911*z);
  const a=(((((1.061405429*t-1.453152027)*t)+1.421413741)*t-0.284496736)*t+0.254829592)*t;
  return s*(1-a*Math.exp(-z*z));
}
function twoTail(z){ return Math.max(0, Math.min(1, 1-erf(Math.abs(z)/Math.SQRT2))); }
function mannWhitney(a,b){
  const x=a.filter(v=>v!==null && isFinite(v));
  const y=b.filter(v=>v!==null && isFinite(v));
  const n1=x.length, n2=y.length;
  if(n1<3 || n2<3) return {U:null, z:null, p:null, n1, n2};
  const all=x.map(v=>({v,g:0})).concat(y.map(v=>({v,g:1}))).sort((p,q)=>p.v-q.v);
  let r1=0, i=0;
  while(i<all.length){
    let j=i; while(j<all.length && all[j].v===all[i].v) j++;
    const avg=(i+1+j)/2;
    for(let k=i;k<j;k++) if(all[k].g===0) r1+=avg;
    i=j;
  }
  const U=r1-n1*(n1+1)/2;
  const mu=n1*n2/2, sig=Math.sqrt(n1*n2*(n1+n2+1)/12);
  const z=(U-mu)/sig;
  return {U, z, p:twoTail(z), n1, n2};
}
function chi2sf(x,k){
  if(!isFinite(x)) return null;
  const t=Math.pow(x/k,1/3)-(1-2/(9*k));
  const s=Math.sqrt(2/(9*k));
  return twoTail(t/s);
}
function chi2quad(pre, post){
  const qs=["Q1","Q2","Q3","Q4"];
  const rp=qs.map(q=>pre[q]||0), po=qs.map(q=>post[q]||0);
  const rt=rp.reduce((s,v)=>s+v,0), ct=po.reduce((s,v)=>s+v,0), N=rt+ct;
  if(N<8 || rt<1 || ct<1) return {chi2:null,p:null,df:3};
  let chi=0;
  qs.forEach((_,i)=>{
    const col=rp[i]+po[i];
    const e1=rt*col/N, e2=ct*col/N;
    if(e1>0) chi+=(rp[i]-e1)**2/e1;
    if(e2>0) chi+=(po[i]-e2)**2/e2;
  });
  return {chi2:chi, p:chi2sf(chi, 3), df:3};
}
function fmtP(p){
  if(p===null||!isFinite(p)) return "—";
  if(p<0.001) return "<0.001";
  return p.toFixed(3);
}
function cassQ(x,y){
  if(!isFinite(x)||!isFinite(y)) return "INVALID";
  if(x>=0 && y>=0) return "Q1";
  if(x<0 && y>=0) return "Q2";
  if(x<0 && y<0) return "Q3";
  return "Q4";
}
const SEGCOL = ["#898781","#2a78d6","#2f6b4f","#b45309","#7c3aed","#b42318","#0f766e"];

function tmaxNow(){
  return D.tmax_s || Math.max(...W.map(w=>w.t1||0), 10);
}
function sortedSplits(){
  const tM=tmaxNow();
  return [...new Set(splits.map(Number).filter(t=>isFinite(t)&&t>0&&t<tM))].sort((a,b)=>a-b);
}
function segmentOf(tm){
  const sp=sortedSplits();
  let i=0; while(i<sp.length && tm>=sp[i]) i++;
  return i;
}
function segName(i){ return i===0 ? "R0" : "R"+i; }
function syncSeg(box){
  if(!box) return;
  box.querySelectorAll("label").forEach(l=>{
    const inp=l.querySelector("input");
    if(inp) l.classList.toggle("on", inp.checked);
  });
}

function rebuildFromMarker(){
  const sp=sortedSplits();
  D.marker_s = sp.length ? sp[0] : null;
  D.splits = sp;
  W.forEach(w=>{ w.seg = segmentOf(w.tm); w.phase = segName(w.seg); });
  const pre = W.filter(w=>w.seg===0);
  CH.forEach(c=>{
    const ls=robustLS(pre.map(w=>w.ch[c] && w.ch[c].raw));
    W.forEach(w=>{
      const raw=w.ch[c]?w.ch[c].raw:null;
      w.ch[c].z = (raw===null||ls.loc===null||!isFinite(raw)) ? null : (raw-ls.loc)/ls.scale;
    });
  });
  const ord=W.slice().sort((a,b)=>a.tm-b.tm);
  ord.forEach(w=>{
    if(!w.autonomic_valid || w.rmssd===null || !isFinite(w.rmssd)){ w.rmssd_s=null; return; }
    let s=0, ww=0;
    ord.forEach(u=>{
      if(!u.autonomic_valid || u.rmssd===null || !isFinite(u.rmssd)) return;
      const dt=Math.abs(u.tm-w.tm); if(dt>5) return;
      const k=1-dt/5; s+=k*u.rmssd; ww+=k;
    });
    w.rmssd_s = ww>0 ? s/ww : w.rmssd;
  });
  const lsY0=robustLS(pre.map(w=>w.rmssd_s));
  const lsYS=robustLS(W.map(w=>w.rmssd_s));
  const yScale = (lsYS.scale && lsYS.scale>1e-12) ? lsYS.scale : (lsY0.scale||1);
  W.forEach(w=>{
    const zs=CH.map(c=>w.ch[c].z).filter(v=>v!==null && isFinite(v));
    w.cortical = zs.length ? zs.reduce((s,v)=>s+v,0)/zs.length : null;
    w.autonomic = (w.rmssd_s!==null && lsY0.loc!==null)
      ? (w.rmssd_s-lsY0.loc)/yScale : null;
    w.quadrant = cassQ(w.cortical, w.autonomic);
    CH.forEach(c=>{
      w.ch[c].dev = (w.ch[c].z!==null && w.cortical!==null) ? w.ch[c].z-w.cortical : null;
    });
  });
  function occ(phase){
    const d = phase==="ALL" ? W : W.filter(w=>w.phase===phase);
    const xs=[], ys=[];
    d.forEach(w=>{ if(w.cortical!==null && w.autonomic!==null){ xs.push(w.cortical); ys.push(w.autonomic);} });
    const bins=12, H=Array.from({length:bins},()=>Array(bins).fill(0));
    const q={Q1:0,Q2:0,Q3:0,Q4:0};
    xs.forEach((x,i)=>{
      const y=ys[i];
      const cx=Math.max(0,Math.min(bins-1, Math.floor((Math.max(-3,Math.min(3,x))+3)/6*bins)));
      const cy=Math.max(0,Math.min(bins-1, Math.floor((Math.max(-3,Math.min(3,y))+3)/6*bins)));
      H[cy][cx]+=1;
      q[cassQ(x,y)]++;
    });
    return {n_valid:xs.length, n_total:d.length, n_excluded:d.length-xs.length, grid:H, q};
  }
  const nSeg = sp.length + 1;
  D.occupancy={ALL:occ("ALL")};
  for(let i=0;i<nSeg;i++) D.occupancy[segName(i)] = occ(segName(i));
  const box=document.getElementById("occPhase");
  if(box){
    const cur=document.querySelector('input[name=ophase]:checked');
    let keep=cur?cur.value:"ALL";
    if(!D.occupancy[keep]) keep="ALL";
    box.innerHTML = ["ALL", ...Array.from({length:nSeg},(_,i)=>segName(i))].map(p=>
      `<label class="${p===keep?"on":""}"><input type="radio" name="ophase" value="${p}" ${p===keep?"checked":""}>${p}</label>`
    ).join("");
    box.querySelectorAll('input[name=ophase]').forEach(r=>r.addEventListener("change", ()=>{
      syncSeg(box); drawOcc();
    }));
  }
  // grid heatmap kepala: mutlak (raw), relatif (z), dominansi
  const ruas=D.ruas_s||30;
  const labs=[...new Set(W.map(w=>`${Math.floor(w.tm/ruas)*ruas}–${Math.floor(w.tm/ruas)*ruas+ruas}s`))]
    .sort((a,b)=>parseInt(a)-parseInt(b));
  D.seg_labels=labs;
  D.grid_raw={}; D.grid_mean={}; D.grid_dominance={};
  labs.forEach(lab=>{
    const lo=parseInt(lab);
    const d=W.filter(w=>Math.floor(w.tm/ruas)*ruas===lo);
    D.grid_raw[lab]={}; D.grid_mean[lab]={}; D.grid_dominance[lab]={};
    CH.forEach(c=>{
      const zs=d.map(w=>w.ch[c].z).filter(v=>v!==null && isFinite(v));
      D.grid_mean[lab][c]=zs.length?zs.reduce((s,v)=>s+v,0)/zs.length:null;
      const rs=d.map(w=>w.ch[c].raw).filter(v=>v!==null && isFinite(v));
      D.grid_raw[lab][c]=rs.length?rs.reduce((s,v)=>s+v,0)/rs.length:null;
    });
    let counts={TP9:0,AF7:0,AF8:0,TP10:0}, n=0;
    d.forEach(w=>{
      let best=null,bv=-Infinity;
      CH.forEach(c=>{ const v=w.ch[c].z; if(v!==null && isFinite(v) && v>bv){bv=v;best=c;} });
      if(best){ counts[best]++; n++; }
    });
    CH.forEach(c=> D.grid_dominance[lab][c]= n? counts[c]/n : null);
  });
}

/* ---------- topbar + ringkasan ---------- */
function renderChips(){
  const nY=W.filter(w=>w.autonomic_valid).length;
  const bad = nY < W.length*0.5;
  const sp=sortedSplits();
  const rows = [
    ["Durasi", fu(D.tmax_s,1)+" s", false],
    ["Window", W.length, false],
    ["Y valid", nY+" / "+W.length, bad],
    ["Ruas", (sp.length+1)+(sp.length?" · acuan R0":" · R0 saja"), false],
    ["CASS", (D.window_s||5)+" / "+(D.step_s||2.5)+" s", false],
    ["IBI min", D.min_ibi, false],
    ["X", D.cortical_metric, false],
    ["Y", D.autonomic_scalar, false],
  ];
  if(SESSIONS.length < 2) rows.unshift(["Sesi", D.session_id, false]);  // kalau ada dropdown, nama sesi sudah ada di sana
  document.getElementById("barChips").innerHTML = rows
    .map(([k,v,w])=>`<div class="chip" title="${esc(k)}: ${esc(String(v))}">${esc(k)}<b class="${w?"warn":""}">${esc(String(v))}</b></div>`).join("");
}
function renderStats(){
  const sp=sortedSplits(), nSeg=sp.length+1, tM=tmaxNow();
  const ref=W.filter(w=>w.seg===0);
  const med=(arr,key)=>fu(median(arr.map(w=>w[key])),2);
  const edge=[0].concat(sp).concat([tM]);
  let rows="";
  for(let i=0;i<nSeg;i++){
    const d=W.filter(w=>w.seg===i);
    const o=D.occupancy[segName(i)];
    let vs="acuan z";
    if(i>0){
      const mwX=mannWhitney(ref.map(w=>w.cortical), d.map(w=>w.cortical));
      const mwY=mannWhitney(ref.map(w=>w.autonomic), d.map(w=>w.autonomic));
      const chi=chi2quad((D.occupancy[segName(0)]||{}).q||{}, (o||{}).q||{});
      vs=`X p≈${fmtP(mwX.p)} · Y p≈${fmtP(mwY.p)} · χ² p≈${fmtP(chi.p)}`;
    }
    rows += `<tr>
      <td><b style="color:${SEGCOL[i%SEGCOL.length]}">${segName(i)}</b>
        <span style="color:var(--muted)">${fu(edge[i],0)}–${fu(edge[i+1],0)}s</span></td>
      <td class="num">${d.length}</td>
      <td class="num">${med(d,"cortical")}</td>
      <td class="num">${med(d,"autonomic")}</td>
      <td class="num">${med(d,"rmssd")}</td>
      ${["Q1","Q2","Q3","Q4"].map(q=>`<td class="num">${o?o.q[q]:"—"}</td>`).join("")}
      <td class="num">${o?o.n_excluded:"—"}</td>
      <td>${vs}</td></tr>`;
  }
  document.getElementById("statBlock").innerHTML = `
    <table><thead><tr>
      <th>Ruas</th><th class="num">n window</th><th class="num">median X (z)</th>
      <th class="num">median Y (z)</th><th class="num">median RMSSD</th>
      <th class="num">Q1</th><th class="num">Q2</th><th class="num">Q3</th><th class="num">Q4</th>
      <th class="num">dikecualikan</th><th>vs R0 (deskriptif)</th>
    </tr></thead><tbody>${rows}</tbody></table>`;
  document.getElementById("statTest").textContent =
    "Mann–Whitney U & χ² okupansi — window 5 s tumpang-tindih, p bukan inferensi independen";
}
function renderEvents(){
  const el=document.getElementById("eventList");
  const sp=sortedSplits(), tM=tmaxNow();
  const parts=["0s"].concat(sp.map(t=>fu(t,1)+"s")).concat([fu(tM,1)+"s"]);
  document.getElementById("segLegend").textContent =
    Array.from({length:sp.length+1},(_,i)=>segName(i)+" = "+parts[i]+"–"+parts[i+1]).join("   ·   ");
  el.innerHTML = sp.map((t,i)=>`
    <div class="evrow">
      <span class="tag" style="border-color:${SEGCOL[(i+1)%SEGCOL.length]}">M${i+1}</span>
      <input type="number" step="0.5" value="${t}" data-edit="${i}">
      <span class="note">${esc(splitLabels[t]||"")}</span>
      <button class="danger" data-del="${t}">hapus</button>
    </div>`).join("") || `<div class="note">Tidak ada marker — seluruh rekaman = R0.</div>`;
  el.querySelectorAll("[data-del]").forEach(b=>b.onclick=()=>{
    splits = splits.filter(x=>+x!==+b.dataset.del);
    commitMarkers();
  });
  el.querySelectorAll("[data-edit]").forEach(inp=>inp.onchange=()=>{
    const i=+inp.dataset.edit, nv=parseFloat(inp.value);
    if(!isFinite(nv)) return;
    splits = sortedSplits().map((x,k)=>k===i?nv:x);
    commitMarkers();
  });
}
function commitMarkers(){
  MARK[si].splits = splits.slice();
  MARK[si].labels = Object.assign({}, splitLabels);
  rebuildFromMarker(); refreshAll();
}

/* ---------- geometri: SVG memakai piksel nyata sel grid ---------- */
function boxOf(svg){
  const r = svg.parentNode.getBoundingClientRect();
  const w = Math.max(80, Math.round(r.width)), h = Math.max(80, Math.round(r.height));
  svg.setAttribute("viewBox", `0 0 ${w} ${h}`);
  svg.setAttribute("preserveAspectRatio", "xMidYMid meet");
  return {w, h};
}
function planeGeom(w, h){
  const padL=30, padR=6, padT=5, padB=26;
  const size = Math.max(60, Math.min(w-padL-padR, h-padT-padB));
  return {size,
    x0: padL + (w-padL-padR-size)/2,
    y0: padT + (h-padT-padB-size)/2};
}
const PX = (g,v) => g.x0 + (Math.max(-3,Math.min(3,v))+3)/6*g.size;
const PY = (g,v) => g.y0 + g.size - (Math.max(-3,Math.min(3,v))+3)/6*g.size;

function planeBack(g){
  return [`<rect x="${g.x0}" y="${g.y0}" width="${g.size}" height="${g.size}"
    fill="var(--surface)" stroke="var(--axis)"/>`];
}
/* kisi, sumbu nol dan label digambar DI ATAS data — latar terpisah di planeBack,
   kalau tidak kontur KDE tertutup persegi latar. */
function planeFront(g, opts){
  opts = opts || {};
  const s=[];
  const tick = g.size>300 ? 9.5 : g.size>190 ? 8.5 : 0;
  for(let t=-3;t<=3;t++){
    const px=PX(g,t), py=PY(g,t);
    s.push(`<line x1="${px}" y1="${g.y0}" x2="${px}" y2="${g.y0+g.size}" stroke="var(--grid)"/>`,
           `<line x1="${g.x0}" y1="${py}" x2="${g.x0+g.size}" y2="${py}" stroke="var(--grid)"/>`);
    if(t && tick)
      s.push(`<text x="${px}" y="${g.y0+g.size+12}" font-size="${tick}" fill="var(--muted)" text-anchor="middle">${t}</text>`,
             `<text x="${g.x0-5}" y="${py+3}" font-size="${tick}" fill="var(--muted)" text-anchor="end">${t}</text>`);
  }
  const mx=PX(g,0), my=PY(g,0);
  s.push(`<line x1="${mx}" y1="${g.y0}" x2="${mx}" y2="${g.y0+g.size}" stroke="var(--ink)" stroke-width="1.3"/>`,
         `<line x1="${g.x0}" y1="${my}" x2="${g.x0+g.size}" y2="${my}" stroke="var(--ink)" stroke-width="1.3"/>`);
  const ax = g.size>190 ? 10 : 9;
  s.push(`<text x="${g.x0+g.size/2}" y="${g.y0+g.size+25}" font-size="${ax}"
    fill="var(--ink2)" text-anchor="middle">cortical state (z)</text>`);
  s.push(`<text x="${g.x0-21}" y="${g.y0+g.size/2}" font-size="${ax}" fill="var(--ink2)"
    text-anchor="middle" transform="rotate(-90 ${g.x0-21} ${g.y0+g.size/2})">autonomic state (z)</text>`);
  if(opts.quadLabels){
    const f = g.size>190 ? 10 : 9, pad = 6;
    [["Q2",g.x0+pad,g.y0+f+3,"start"],["Q1",g.x0+g.size-pad,g.y0+f+3,"end"],
     ["Q3",g.x0+pad,g.y0+g.size-pad,"start"],["Q4",g.x0+g.size-pad,g.y0+g.size-pad,"end"]]
      .forEach(([q,px,py,anc])=>s.push(
        `<text x="${px}" y="${py}" font-size="${f}" fill="var(--ink2)" text-anchor="${anc}">${q}</text>`));
  }
  return s;
}

/* ---------- state map ---------- */
function drawMap(){
  const svg=document.getElementById("mapSvg");
  const {w,h}=boxOf(svg);
  const g=planeGeom(w,h);
  const s=planeBack(g).concat(planeFront(g,{quadLabels:true}));
  const pts = W.filter(x => x.cortical!==null && x.autonomic!==null);
  let dpath = "";
  pts.forEach((x,i)=>{ dpath += (i?" L":"M") + PX(g,x.cortical).toFixed(1) + " " + PY(g,x.autonomic).toFixed(1); });
  s.push(`<path d="${dpath}" fill="none" stroke="var(--accent)" stroke-width="1.1" opacity=".35"/>`);
  const r = Math.max(2, Math.min(4.2, g.size/130));
  pts.forEach(x=>{
    s.push(`<circle cx="${PX(g,x.cortical).toFixed(1)}" cy="${PY(g,x.autonomic).toFixed(1)}" r="${r.toFixed(1)}"
      fill="${SEGCOL[(x.seg||0)%SEGCOL.length]}" opacity=".82"
      stroke="var(--surface)" stroke-width="1.1"><title>w${x.id} ${x.phase} t=${fu(x.tm,1)}s ${x.quadrant}</title></circle>`);
  });
  const c = W[idx];
  if(c && c.cortical!==null && c.autonomic!==null)
    s.push(`<circle cx="${PX(g,c.cortical).toFixed(1)}" cy="${PY(g,c.autonomic).toFixed(1)}"
      r="${(r*2.2).toFixed(1)}" fill="none" stroke="var(--ink)" stroke-width="2.2"/>`);
  svg.innerHTML = s.join("");
}
function drawKpi(){
  const w = W[idx];
  if(!w) return;
  document.getElementById("winLabel").textContent =
    `Window #${w.id} · ${w.phase} · ${fu(w.t0,1)}–${fu(w.t1,1)} s`;
  const av = w.autonomic_valid;
  document.getElementById("kpi").innerHTML = `
    <div>cortical X<b>${fx(w.cortical)}</b></div>
    <div>autonomic Y<b class="${av?'':'warn'}">${av?fx(w.autonomic):"invalid"}</b></div>
    <div>kuadran<b>${esc(w.quadrant)}</b></div>
    <div>RMSSD<b>${fu(w.rmssd,1)}</b></div>
    <div>halus<b>${fu(w.rmssd_s,1)}</b></div>
    <div>HR<b>${fu(w.hr,1)}</b></div>
    <div>IBI<b class="${w.n_ibi< D.min_ibi?'warn':''}">${w.n_ibi}</b></div>`;
}

/* ---------- heatmap kuadran kepala: mutlak / relatif / dominansi ---------- */
function drawHead(){
  const svg=document.getElementById("headSvg");
  const {w,h}=boxOf(svg);
  const mode = document.querySelector('input[name=hmode]:checked').value;
  const src = mode==="raw" ? D.grid_raw : mode==="mean" ? D.grid_mean : D.grid_dominance;
  const segs = D.seg_labels || [];
  if(!segs.length){ svg.innerHTML=""; return; }
  const wide = w>900;
  const left = wide ? 126 : 58, right = 6, top = 12, bot = 13;
  const rh = Math.max(10, (h - top - bot)/ROWS.length);
  const cw = Math.max(14, (w - left - right)/segs.length);
  const fCell = Math.max(7, Math.min(11, rh*0.45, cw*0.26));
  const fLab  = Math.max(7, Math.min(10.5, rh*0.46));
  const s=[];
  ROWS.forEach((ch,i)=>{
    s.push(`<text x="${left-7}" y="${top+i*rh+rh/2+fLab*0.35}" font-size="${fLab.toFixed(1)}"
      fill="var(--ink2)" text-anchor="end">${esc(wide?CHLABEL[ch]:ch)}</text>`);
    segs.forEach((sg,j)=>{
      const v = src[sg] ? src[sg][ch] : null;
      const x = left + j*cw, y = top + i*rh;
      let fill="var(--surface)", txt="—", col="var(--muted)", over=false;
      if(v!==null && v!==undefined && isFinite(v)){
        if(mode==="raw"){ fill = divColor(v/rawLim*3); txt = fx(v); }
        else if(mode==="mean"){ over = Math.abs(v)>3; fill = divColor(v); txt = fx(v)+(over?"*":""); }
        else { fill = seqColor(v); txt = Math.round(v*100)+"%"; }
        col = inkOn(fill);
      }
      s.push(`<rect x="${x+0.7}" y="${y+0.7}" width="${cw-1.4}" height="${rh-1.4}" fill="${fill}"><title>${esc(sg)} ${esc(ch)} ${txt}</title></rect>`);
      if(over) s.push(`<rect x="${x+0.7}" y="${y+0.7}" width="${cw-1.4}" height="${rh-1.4}" fill="url(#hatch)"/>`);
      if(cw>26 && rh>=15) s.push(`<text x="${x+cw/2}" y="${y+rh/2+fCell*0.35}" font-size="${fCell.toFixed(1)}"
        fill="${col}" text-anchor="middle">${txt}</text>`);
    });
  });
  segs.forEach((sg,j)=>{
    let best=null, bv=-Infinity;
    ROWS.forEach((ch,i)=>{ const v=src[sg]?src[sg][ch]:null;
      if(v!==null && isFinite(v) && v>bv){ bv=v; best=i; } });
    if(best!==null) s.push(`<rect x="${left+j*cw+0.7}" y="${top+best*rh+0.7}"
      width="${cw-1.4}" height="${rh-1.4}" fill="none" stroke="var(--ink)" stroke-width="1.8"/>`);
  });
  const step = Math.ceil(segs.length/Math.max(1,Math.floor((w-left)/44)));
  segs.forEach((sg,j)=>{
    if(j%step) return;
    s.push(`<text x="${left+j*cw+cw/2}" y="${top+ROWS.length*rh+10}" font-size="8.5"
      fill="var(--muted)" text-anchor="middle">${esc(String(parseInt(sg,10)))}</text>`);
  });
  s.push(`<text x="${left-7}" y="${top+ROWS.length*rh+10}" font-size="8.5"
    fill="var(--muted)" text-anchor="end">detik</text>`);
  sortedSplits().forEach((t,i)=>{
    const xm = Math.min(left+segs.length*cw, left + (t/(D.ruas_s||30))*cw);
    s.push(`<line x1="${xm}" y1="${top}" x2="${xm}" y2="${top+ROWS.length*rh}"
      stroke="${SEGCOL[(i+1)%SEGCOL.length]}" stroke-width="2"/>`);
    s.push(`<text x="${xm}" y="${top-3}" font-size="8.5" font-weight="700"
      fill="${SEGCOL[(i+1)%SEGCOL.length]}" text-anchor="middle">M${i+1} ${fu(t,0)}s</text>`);
  });
  svg.innerHTML = `<defs><pattern id="hatch" width="7" height="7"
      patternTransform="rotate(45)" patternUnits="userSpaceOnUse">
      <line x1="0" y1="0" x2="0" y2="7" stroke="#ffffff" stroke-opacity=".45" stroke-width="2.5"/>
    </pattern></defs>` + s.join("");
  const lead = `HEATMAP KUADRAN KEPALA · kolom ruas ${fu(D.ruas_s||30,0)} s · `;
  document.getElementById("headTitle").textContent = lead + (
    mode==="raw"  ? `mutlak: log β/α sebelum di-z, domain ±${fu(rawLim,2)} — nilai 0 berarti daya β setara α`
  : mode==="mean" ? "relatif: robust-z terhadap ruas R0, domain ±3"
                  : "relatif: proporsi window dengan elektroda ini tertinggi");
}

/* ---------- okupansi CASS ---------- */
function kde2(pts, n=40, h=0.55){
  const G=Array.from({length:n},()=>Array(n).fill(0));
  if(!pts.length) return G;
  const sig=h/6*n;
  pts.forEach(([x,y])=>{
    const cx=(Math.max(-3,Math.min(3,x))+3)/6*(n-1);
    const cy=(Math.max(-3,Math.min(3,y))+3)/6*(n-1);
    const r=Math.ceil(sig*3);
    for(let i=Math.max(0,Math.floor(cy)-r);i<Math.min(n,Math.ceil(cy)+r+1);i++)
      for(let j=Math.max(0,Math.floor(cx)-r);j<Math.min(n,Math.ceil(cx)+r+1);j++){
        const dx=(j-cx)/sig, dy=(i-cy)/sig;
        G[i][j]+=Math.exp(-0.5*(dx*dx+dy*dy));
      }
  });
  return G;
}
function hexAlpha(hex,a){
  const m=hex.replace("#","");
  const r=parseInt(m.slice(0,2),16), g=parseInt(m.slice(2,4),16), b=parseInt(m.slice(4,6),16);
  return `rgba(${r},${g},${b},${a})`;
}
function drawOcc(){
  const svg=document.getElementById("occSvg");
  const {w,h}=boxOf(svg);
  const phaseEl=document.querySelector('input[name=ophase]:checked');
  const phase = phaseEl?phaseEl.value:"ALL";
  const o = D.occupancy[phase] || D.occupancy.ALL;
  if(!o){ svg.innerHTML=""; return; }
  const g=planeGeom(w,h);
  const showD=document.getElementById("occDens")?.checked!==false;
  const showL=document.getElementById("occLayer")?.checked!==false;
  const showP=document.getElementById("occPts")?.checked!==false;
  const s=planeBack(g);
  function paintK(G, colorFn){
    const n=G.length, cell=g.size/n;
    let mx=0; G.forEach(row=>row.forEach(v=>{ if(v>mx) mx=v; }));
    if(mx<=0) return;
    for(let r=0;r<n;r++) for(let c=0;c<n;c++){
      const v=G[r][c]/mx; if(v<0.08) continue;
      s.push(`<rect x="${(g.x0+c*cell).toFixed(1)}" y="${(g.y0+g.size-(r+1)*cell).toFixed(1)}"
        width="${(cell+0.4).toFixed(1)}" height="${(cell+0.4).toFixed(1)}" fill="${colorFn(v)}"/>`);
    }
  }
  const sel = W.filter(x=>x.cortical!==null && x.autonomic!==null)
               .filter(x=>phase==="ALL"||x.phase===phase);
  if(showD) paintK(kde2(sel.map(x=>[x.cortical,x.autonomic])),
    v=>seqColor(v).replace("rgb","rgba").replace(")",`,${0.15+0.55*v})`));
  if(showL){
    const nSeg=sortedSplits().length+1;
    for(let i=0;i<nSeg;i++){
      if(phase!=="ALL" && segName(i)!==phase) continue;
      const pts=W.filter(x=>x.seg===i && x.cortical!==null && x.autonomic!==null)
        .map(x=>[x.cortical,x.autonomic]);
      paintK(kde2(pts,36,0.5), v=>hexAlpha(SEGCOL[i%SEGCOL.length], 0.12+0.45*v));
    }
  }
  s.push(...planeFront(g,{}));
  if(showP){
    const r = Math.max(1.8, Math.min(3.4, g.size/160));
    sel.forEach(x=>{
      s.push(`<circle cx="${PX(g,x.cortical).toFixed(1)}" cy="${PY(g,x.autonomic).toFixed(1)}" r="${r.toFixed(1)}"
        fill="${SEGCOL[(x.seg||0)%SEGCOL.length]}" opacity=".85"
        stroke="var(--surface)" stroke-width="1"><title>w${x.id} ${x.phase} ${x.quadrant}</title></circle>`);
    });
  }
  const f = g.size>320 ? 11 : g.size>200 ? 10 : 9;
  const pos = {Q1:[g.x0+g.size-8, g.y0+f+6,"end"], Q2:[g.x0+8, g.y0+f+6,"start"],
               Q3:[g.x0+8, g.y0+g.size-8,"start"], Q4:[g.x0+g.size-8, g.y0+g.size-8,"end"]};
  Object.keys(pos).forEach(q=>{
    const [px,py,anc]=pos[q], cnt=o.q[q];
    const pct = o.n_valid ? Math.round(cnt/o.n_valid*100) : 0;
    const label = `${q} · n=${cnt} · ${pct}%`;
    const bw = label.length*f*0.53 + 10, bh = f+6;
    const rx = anc==="end" ? px-bw+2 : px-2;
    s.push(`<rect x="${rx.toFixed(1)}" y="${(py-f-1).toFixed(1)}" width="${bw.toFixed(1)}" height="${bh.toFixed(1)}" rx="4"
      fill="var(--surface)" stroke="var(--axis)" stroke-width=".7" opacity=".93"/>`);
    s.push(`<text x="${px}" y="${py}" font-size="${f}" fill="var(--ink2)" text-anchor="${anc}">${label}</text>`);
  });
  svg.innerHTML = s.join("");
  const top_q = Object.keys(o.q).reduce((a,b)=> o.q[a]>=o.q[b]?a:b);
  document.getElementById("occNote").innerHTML =
    `Terbanyak <b>${esc(QLAB[top_q])}</b> — ${o.q[top_q]}/${o.n_valid} window valid`
    + (o.n_excluded ? ` · <span class="warn">${o.n_excluded} dikecualikan (bukan nol)</span>` : "");
}

/* ---------- lintasan waktu: X(t) dan Y(t) ----------
   Bidang fase membuang sumbu waktu, heatmap kepala meringkasnya per ruas.
   Panel ini menyajikan kedua sumbu apa adanya terhadap waktu — konvensi
   dua-sumbu untuk data kontinu. Window dengan Y tidak valid memutus garis,
   tidak digambar sebagai nol. */
function drawTime(){
  const svg=document.getElementById("timeSvg");
  const {w,h}=boxOf(svg);
  const byRuas=document.getElementById("tRuas")?.checked!==false;
  const showP=document.getElementById("tPts")?.checked!==false;
  const padL=30, padR=7, padT=6, padB=20, gap=15;
  const rowH=Math.max(30,(h-padT-padB-gap)/2);
  const tM=tmaxNow();
  const TX = t => padL + (Math.max(0,Math.min(tM,t))/tM)*(w-padL-padR);
  const VY = (row,v) => padT + row*(rowH+gap) + rowH - (Math.max(-3,Math.min(3,v))+3)/6*rowH;
  const ord=W.slice().sort((a,b)=>a.tm-b.tm);
  const s=[];

  [["cortical","X · cortical state (z)",0],["autonomic","Y · autonomic state (z)",1]]
  .forEach(([key,label,row])=>{
    const y0=padT+row*(rowH+gap);
    s.push(`<rect x="${padL}" y="${y0}" width="${w-padL-padR}" height="${rowH}"
      fill="var(--surface)" stroke="var(--axis)"/>`);
    for(const g of [-3,-1.5,0,1.5,3]){
      const py=VY(row,g);
      s.push(`<line x1="${padL}" y1="${py}" x2="${w-padR}" y2="${py}"
        stroke="${g===0?"var(--ink)":"var(--grid)"}" stroke-width="${g===0?1.2:1}"/>`);
      if(Number.isInteger(g) && g)
        s.push(`<text x="${padL-4}" y="${py+3}" font-size="8.5" fill="var(--muted)" text-anchor="end">${g}</text>`);
    }
    // marker ruas
    sortedSplits().forEach((t,i)=>s.push(`<line x1="${TX(t).toFixed(1)}" y1="${y0}"
      x2="${TX(t).toFixed(1)}" y2="${y0+rowH}" stroke="${SEGCOL[(i+1)%SEGCOL.length]}" stroke-width="1.6"/>`));
    // garis: terputus di window tanpa nilai (Y invalid tidak dinolkan)
    let d="", open=false;
    ord.forEach(x=>{
      const v=x[key];
      if(v===null||!isFinite(v)){ open=false; return; }
      d += (open?" L":"M") + TX(x.tm).toFixed(1) + " " + VY(row,v).toFixed(1);
      open=true;
    });
    s.push(`<path d="${d}" fill="none" stroke="var(--accent)" stroke-width="1.2" opacity=".55"/>`);
    if(showP) ord.forEach(x=>{
      const v=x[key];
      if(v===null||!isFinite(v)) return;
      // nilai di luar ±3 menempel di tepi — beri cincin merah supaya deretan
      // mendatar di batas tidak terbaca sebagai plateau sungguhan
      const clip = Math.abs(v)>3;
      s.push(`<circle cx="${TX(x.tm).toFixed(1)}" cy="${VY(row,v).toFixed(1)}" r="${clip?2.4:1.9}"
        fill="${byRuas?SEGCOL[(x.seg||0)%SEGCOL.length]:"var(--accent)"}" opacity=".9"
        ${clip?'stroke="#d03b3b" stroke-width="1.1"':""}><title>t=${fu(x.tm,1)}s ${fx(v)}${clip?" (di luar ±3)":""}</title></circle>`);
    });
    s.push(`<text x="${padL+4}" y="${y0+10}" font-size="9" fill="var(--ink2)">${label}</text>`);
  });

  // window tanpa bukti RR Polar: pita di bawah baris Y, bukan titik pada nol
  const bad=ord.filter(x=>x.autonomic===null||!isFinite(x.autonomic));
  const yb=padT+(rowH+gap)+rowH;
  bad.forEach(x=>s.push(`<line x1="${TX(x.tm).toFixed(1)}" y1="${(yb-4).toFixed(1)}"
    x2="${TX(x.tm).toFixed(1)}" y2="${yb.toFixed(1)}" stroke="#d03b3b" stroke-width="1.6" opacity=".8"/>`));

  // window terpilih
  const c=W[idx];
  if(c) s.push(`<line x1="${TX(c.tm).toFixed(1)}" y1="${padT}" x2="${TX(c.tm).toFixed(1)}"
    y2="${(padT+2*rowH+gap).toFixed(1)}" stroke="var(--ink)" stroke-width="1.4" stroke-dasharray="3 2"/>`);

  // sumbu waktu
  const nTick=Math.max(2,Math.min(6,Math.floor((w-padL)/60)));
  for(let k=0;k<=nTick;k++){
    const t=tM*k/nTick;
    s.push(`<text x="${TX(t).toFixed(1)}" y="${h-6}" font-size="8.5" fill="var(--muted)"
      text-anchor="${k===0?"start":k===nTick?"end":"middle"}">${fu(t,0)}${k===nTick?" s":""}</text>`);
  }
  svg.innerHTML=s.join("");
  const clip=ord.filter(x=>["cortical","autonomic"].some(k=>{
    const v=x[k]; return v!==null && isFinite(v) && Math.abs(v)>3; })).length;
  const bits=["klik untuk memindahkan window terpilih"];
  if(clip) bits.unshift(`<span class="warn">${clip} window di luar ±3</span> (bercincin merah, menempel tepi)`);
  if(bad.length) bits.unshift(`<span class="warn">${bad.length} tanpa bukti RR Polar</span> — garis Y diputus, bukan dinolkan`);
  document.getElementById("timeNote").innerHTML = bits.join(" · ");
}

/* ---------- ringkasan hasil (hanya untuk PDF) ----------
   Semuanya angka terhitung dari payload yang sama dengan yang di layar.
   Tidak ada kalimat sebab-akibat; yang ditambahkan hanya peringatan
   metodologis ketika datanya memang tidak layak ditafsirkan. */
function summaryFacts(){
  const sp=sortedSplits(), nSeg=sp.length+1, tM=tmaxNow();
  const edge=[0].concat(sp).concat([tM]);
  const nY=W.filter(w=>w.autonomic_valid).length;
  const all=D.occupancy.ALL || {q:{},n_valid:0,n_excluded:0};
  const topAll=Object.keys(all.q||{}).reduce((a,b)=>(all.q[a]>=all.q[b]?a:b), "Q1");
  const ruas=[];
  for(let i=0;i<nSeg;i++){
    const d=W.filter(w=>w.seg===i), o=D.occupancy[segName(i)];
    const tq=o && o.n_valid ? Object.keys(o.q).reduce((a,b)=>(o.q[a]>=o.q[b]?a:b)) : null;
    const el={};
    CH.forEach(c=>{
      const v=d.map(w=>w.ch[c].z).filter(x=>x!==null&&isFinite(x));
      el[c]= v.length ? v.reduce((s,x)=>s+x,0)/v.length : null;
    });
    let best=null,bv=-Infinity;
    CH.forEach(c=>{ if(el[c]!==null && el[c]>bv){bv=el[c]; best=c;} });
    ruas.push({i, nama:segName(i), t0:edge[i], t1:edge[i+1], n:d.length, o, tq,
               el, best, bestVal:bv,
               mx:median(d.map(w=>w.cortical)), my:median(d.map(w=>w.autonomic)),
               mr:median(d.map(w=>w.rmssd)),
               nY:d.filter(w=>w.autonomic_valid).length});
  }
  let shift=null;
  if(nSeg>1){
    const A=D.occupancy[segName(0)], B=D.occupancy[segName(nSeg-1)];
    if(A&&B&&A.n_valid&&B.n_valid){
      shift={dari:segName(0), ke:segName(nSeg-1), q:{}};
      ["Q1","Q2","Q3","Q4"].forEach(q=>{
        shift.q[q]=(B.q[q]/B.n_valid - A.q[q]/A.n_valid)*100; });
      shift.top=Object.keys(shift.q).reduce((a,b)=>Math.abs(shift.q[a])>=Math.abs(shift.q[b])?a:b);
    }
  }
  const clip=W.filter(w=>["cortical","autonomic"].some(k=>{
    const v=w[k]; return v!==null && isFinite(v) && Math.abs(v)>3; })).length;
  return {nSeg, tM, nY, n:W.length, all, topAll, ruas, shift, clip,
          excl:all.n_excluded||0};
}

function summaryFlags(f){
  const out=[];
  const frac=f.n ? f.nY/f.n : 0;
  if(frac < 0.5) out.push(`Bukti RR Polar hanya <b>${f.nY} dari ${f.n} window</b> (${Math.round(frac*100)}%). `
    + `Sumbu autonomic tidak layak ditafsirkan untuk sesi ini: sebagian besar window tidak punya cukup IBI `
    + `(ambang ${D.min_ibi}), dan window tanpa bukti dikecualikan — bukan dianggap nol.`);
  else if(frac < 0.8) out.push(`Bukti RR Polar tersedia pada ${f.nY} dari ${f.n} window (${Math.round(frac*100)}%). `
    + `Pernyataan tentang sumbu autonomic berlaku hanya untuk window yang punya bukti.`);
  f.ruas.forEach(r=>{ if(r.n>0 && r.n<10)
    out.push(`Ruas <b>${r.nama}</b> hanya berisi ${r.n} window (${fu(r.t0,0)}–${fu(r.t1,0)} s). `
      + `Median dan sebaran kuadrannya tidak stabil.`); });
  f.ruas.forEach(r=>{ if(r.o && r.o.n_valid>0 && r.o.n_valid<10)
    out.push(`Okupansi kuadran ruas <b>${r.nama}</b> dihitung dari hanya ${r.o.n_valid} window valid — `
      + `persentase dan pergeseran poin-persen yang melibatkan ruas ini kasar.`); });
  f.ruas.forEach(r=>{ if(r.n>0 && r.nY===0)
    out.push(`Ruas <b>${r.nama}</b> tidak punya satu pun window dengan bukti RR Polar — nilai Y untuk ruas itu kosong, bukan nol.`); });
  if(f.clip/Math.max(1,f.n) > 0.05)
    out.push(`<b>${f.clip} window</b> (${Math.round(f.clip/f.n*100)}%) memiliki X atau Y di luar domain ±3 dan digambar menempel di tepi. `
      + `Bentuk sebaran di dekat tepi tidak mencerminkan nilai sebenarnya.`);
  if(f.nSeg<2) out.push(`Sesi ini tidak punya marker: seluruh rekaman adalah R0, jadi tidak ada pembanding antar-ruas.`);
  return out;
}

/* ---------- PEMBACAAN POLA CASS (lapisan tafsir) ----------
   Aturan di bawah disusun sekali, di luar berkas ini, lalu ditanam sebagai
   mesin aturan. Tidak ada model bahasa yang dipanggil saat mencetak: berkas
   ini berjalan tanpa internet, dan hasil yang bisa diaudit lebih berguna
   untuk naskah daripada teks yang berubah tiap kali dijalankan.

   Dasar fisiologis yang dipakai:
     X = log(β/α) robust-z. Naik  -> β relatif menguat: korteks teraktivasi.
                            Turun -> α relatif menguat: korteks melambat/idling.
     Y = RMSSD robust-z.    Naik  -> modulasi vagal (parasimpatis) menguat.
                            Turun -> modulasi vagal melemah / geser simpatis.
   Kuadran adalah kombinasi tanda keduanya. Semua kalimat memakai "dibaca
   sebagai" / "konsisten dengan" — tidak ada klaim sebab-akibat, dan tidak
   ada klaim klinis. */
const CARA_BACA_ANGKA = `<b>A</b> adalah peluang bahwa satu window acak dari ruas pertama bernilai lebih
  tinggi daripada satu window acak dari ruas pembanding; 0,50 berarti tidak ada beda, dan angka ini tidak
  bergantung pada banyaknya window. <b>Δ poin persen</b> adalah selisih proporsi window per kuadran.
  Keduanya layak dilaporkan apa adanya. <b>p</b> (Mann–Whitney dan χ²) disertakan sebagai pelengkap
  deskriptif saja: window 5 s bergeser 2,5 s sehingga saling tumpang-tindih, jumlah pengamatan efektif
  jauh lebih kecil daripada jumlah window, dan p menjadi terlalu kecil. Jangan melaporkan p ini sebagai
  uji hipotesis.`;
const QBACA = {
  Q1: {nama:"aktivasi terkendali",
       arti:"korteks teraktivasi (β menguat atas α) sementara modulasi vagal tetap tinggi",
       baca:"kesiagaan yang masih disertai cadangan regulasi otonom — bekerja tanpa kehilangan rem parasimpatis"},
  Q2: {nama:"pemulihan aktif",
       arti:"korteks melambat (α menguat atas β) dengan modulasi vagal tinggi",
       baca:"kondisi istirahat/pemulihan: beban pemrosesan turun dan regulasi otonom justru menguat"},
  Q3: {nama:"penurunan ganda",
       arti:"korteks melambat sekaligus modulasi vagal melemah",
       baca:"arousal rendah tanpa disertai penguatan regulasi — pola yang lazim menyertai kelelahan, kantuk, atau penarikan diri dari tugas"},
  Q4: {nama:"aktivasi bertegangan",
       arti:"korteks teraktivasi sementara modulasi vagal melemah",
       baca:"upaya kognitif yang dibayar dengan turunnya rem parasimpatis — pola bertegangan/effortful"},
};
function mad(a){
  const x=a.filter(v=>v!==null&&isFinite(v));
  if(x.length<2) return null;
  const m=median(x);
  return 1.4826*median(x.map(v=>Math.abs(v-m)));
}
function arah(d, kuat, sedang){
  const a=Math.abs(d);
  if(a<sedang) return "praktis tidak berubah";
  return (d>0?"naik":"turun") + (a>=kuat ? " tajam" : "");
}
function bacaCASS(f){
  const Ylayak = f.n ? (f.nY/f.n) >= 0.5 : false;
  const out=[];

  // 1. posisi dominan
  const t=f.topAll, m=QBACA[t];
  const pct=f.all.n_valid ? (f.all.q[t]/f.all.n_valid*100).toFixed(1) : "—";
  out.push(`<li><b>Posisi dominan.</b> ${pct}% window valid jatuh di <b>${t}</b> — ${m.arti}. `
    + `Dalam kerangka CASS pola ini dibaca sebagai <b>${m.nama}</b>: ${m.baca}.`
    + (Ylayak ? "" : ` <i>Karena bukti RR Polar tipis, penamaan kuadran ini bertumpu pada sedikit window; lihat peringatan.</i>`));

  // 2. perpindahan antar-ruas — bersandar pada statistik yang sudah dihitung
  if(f.nSeg>1){
    const r0=f.ruas[0];
    const ref=W.filter(w=>w.seg===0);
    f.ruas.slice(1).forEach(r=>{
      const d=W.filter(w=>w.seg===r.i);
      const mwX=mannWhitney(ref.map(w=>w.cortical), d.map(w=>w.cortical));
      const mwY=mannWhitney(ref.map(w=>w.autonomic), d.map(w=>w.autonomic));
      const chi=chi2quad((f.ruas[0].o||{}).q||{}, (r.o||{}).q||{});
      // A = P(nilai acak R0 > nilai acak Rk). 0,5 = tidak ada beda.
      // Tidak bergantung ukuran sampel, jadi lebih layak dilaporkan daripada p
      // ketika window saling tumpang-tindih.
      const Ax = (mwX.U!==null && mwX.n1 && mwX.n2) ? mwX.U/(mwX.n1*mwX.n2) : null;
      const Ay = (mwY.U!==null && mwY.n1 && mwY.n2) ? mwY.U/(mwY.n1*mwY.n2) : null;
      const kuat = a => a===null ? "" :
        (Math.abs(a-0.5)<0.06 ? "praktis setara" :
         Math.abs(a-0.5)<0.14 ? "beda kecil" :
         Math.abs(a-0.5)<0.28 ? "beda sedang" : "beda besar");
      const dx = (r.mx!==null && r0.mx!==null) ? r.mx-r0.mx : null;
      const dy = (Ylayak && r.my!==null && r0.my!==null) ? r.my-r0.my : null;

      let b = `<li><b>${r0.nama} &rarr; ${r.nama}</b> (${fu(r.t0,0)}–${fu(r.t1,0)} s, ${r.n} window).<br>`;

      // --- sumbu kortikal
      b += `<u>Sumbu kortikal X.</u> Median ${fu(r0.mx,2)} &rarr; ${fu(r.mx,2)} (Δ ${fx(dx)}). `;
      if(Ax!==null){
        const lbh = Ax>0.5 ? r0.nama : r.nama;
        b += `A = ${fu(Ax,2)} — pada ${Math.round((Ax>0.5?Ax:1-Ax)*100)}% pasangan window acak, `
           + `<b>${lbh}</b> bernilai lebih tinggi (${kuat(Ax)}); Mann–Whitney p≈${fmtP(mwX.p)}. `;
      }
      b += `Dibaca: `
        + (dx===null ? "tidak cukup data"
         : dx<-0.25 ? `α menguat relatif terhadap β — korteks melambat${Ax!==null&&Math.abs(Ax-0.5)>=0.28?", dan pergeseran itu berlaku menyeluruh pada ruas ini, bukan hanya pada sebagian window":""}`
         : dx>0.25  ? `β menguat relatif terhadap α — korteks teraktivasi${Ax!==null&&Math.abs(Ax-0.5)>=0.28?", menyeluruh pada ruas ini":""}`
                    : "keseimbangan β/α praktis tidak berpindah")
        + `.<br>`;

      // --- sumbu otonom
      b += `<u>Sumbu otonom Y.</u> `;
      if(!Ylayak){
        b += `Tidak dibaca: bukti RR Polar hanya ${f.nY}/${f.n} window untuk sesi ini.<br>`;
      } else if(r.nY===0){
        b += `Tidak dibaca: ruas ini tidak memiliki window dengan bukti RR Polar.<br>`;
      } else {
        b += `Median ${fu(r0.my,2)} &rarr; ${fu(r.my,2)} (Δ ${fx(dy)}). `;
        if(Ay!==null){
          const lbh = Ay>0.5 ? r0.nama : r.nama;
          b += `A = ${fu(Ay,2)} — <b>${lbh}</b> lebih tinggi pada ${Math.round((Ay>0.5?Ay:1-Ay)*100)}% pasangan (${kuat(Ay)}); p≈${fmtP(mwY.p)}. `;
        }
        b += `Dibaca: `
          + (dy===null ? "tidak cukup data"
           : dy>0.25 ? "modulasi vagal menguat — rem parasimpatis lebih aktif"
           : dy<-0.25 ? "modulasi vagal melemah — rem parasimpatis berkurang"
                      : "modulasi vagal praktis setara")
          + `.<br>`;
      }

      // --- redistribusi kuadran
      if(r.o && f.ruas[0].o && r.o.n_valid && f.ruas[0].o.n_valid){
        const A0=f.ruas[0].o, B0=r.o;
        const dpp={}; ["Q1","Q2","Q3","Q4"].forEach(k=>
          dpp[k]=(B0.q[k]/B0.n_valid - A0.q[k]/A0.n_valid)*100);
        // seri sering terjadi (mis. dua kuadran sama-sama +40,0 pp). Pemenangnya
        // dipecah oleh pangsa di ruas tujuan supaya sejalan dengan kuadran dominan.
        const sh=(o,k)=> o.n_valid ? o.q[k]/o.n_valid : 0;
        const naik=Object.keys(dpp).filter(k=>dpp[k]>0)
          .sort((a,b)=> (dpp[b]-dpp[a]) || (sh(B0,b)-sh(B0,a)));
        const turun=Object.keys(dpp).filter(k=>dpp[k]<0)
          .sort((a,b)=> (dpp[a]-dpp[b]) || (sh(A0,b)-sh(A0,a)));
        b += `<u>Sebaran kuadran.</u> χ² p≈${fmtP(chi.p)} untuk perbedaan sebaran empat kuadran. `
          + `Perubahan: ${["Q1","Q2","Q3","Q4"].map(k=>`${k} ${dpp[k]>=0?"+":""}${dpp[k].toFixed(1)}`).join(" · ")} poin persen. `;
        if(naik.length && turun.length){
          const ke=QBACA[naik[0]], dari=QBACA[turun[0]];
          b += `Dibaca: bobot keadaan berpindah dari <b>${turun[0]}</b> (${dari.nama}) ke <b>${naik[0]}</b> (${ke.nama}) — `
             + `${ke.baca}.`
             + (Ylayak ? "" : ` <i>Penamaan kuadran memakai tanda Y, yang untuk sesi ini bertumpu pada ${f.nY} window saja.</i>`);
        } else {
          b += `Dibaca: sebaran kuadran tidak berpindah secara berarti.`;
        }
        b += `<br>`;
      }

      // --- makna gabungan
      if(r.tq && QBACA[r.tq]){
        b += `<u>Makna gabungan.</u> Ruas ${r.nama} paling sering berada di <b>${r.tq}</b> `
           + `(${r.o?(r.o.q[r.tq]/r.o.n_valid*100).toFixed(1):"—"}% window valid) — `
           + `dalam kerangka CASS: <b>${QBACA[r.tq].nama}</b>, ${QBACA[r.tq].baca}.`;
        if(r0.tq && r0.tq!==r.tq)
          b += ` Ruas acuan ${r0.nama} paling sering di <b>${r0.tq}</b> (${QBACA[r0.tq].nama}), `
             + `sehingga perubahan antar-ruas adalah perpindahan dari ${QBACA[r0.tq].nama} ke ${QBACA[r.tq].nama}.`;
        if(!Ylayak)
          b += ` <i>Kuadran ditentukan oleh tanda X dan Y; karena bukti RR Polar tipis, komponen Y dari penamaan ini lemah — `
             + `pernyataan yang hanya bersandar pada X (arah β/α) tetap berlaku.</i>`;
      }
      out.push(b + `</li>`);
    });
  } else {
    out.push(`<li><b>Perpindahan.</b> Sesi tanpa marker: tidak ada ruas pembanding, sehingga tidak ada pernyataan
      perpindahan maupun statistik antar-ruas. Tambahkan marker di dashboard untuk memunculkan bagian ini.</li>`);
  }

  // 3. kestabilan
  f.ruas.forEach(r=>{
    const d=W.filter(w=>w.seg===r.i);
    const sx=mad(d.map(w=>w.cortical));
    if(sx===null) return;
    const sy=Ylayak ? mad(d.map(w=>w.autonomic)) : null;
    const lab = sx<0.5 ? "terkonsentrasi" : sx<1.2 ? "sedang" : "tersebar luas";
    out.push(`<li><b>Kestabilan ${r.nama}.</b> Sebaran X (MAD robust) ${fu(sx,2)}`
      + (sy!==null?` dan Y ${fu(sy,2)}`:"")
      + ` — sebaran ${lab}. `
      + (sx<0.5 ? "Keadaan kortikal bertahan pada satu tingkat selama ruas ini."
                : sx<1.2 ? "Keadaan kortikal berayun dalam rentang moderat."
                         : "Keadaan kortikal berpindah-pindah; nilai median ruas ini mewakili sebaran yang lebar, bukan satu keadaan tunggal.")
      + `</li>`);
  });

  // 4. topografi elektroda
  f.ruas.forEach(r=>{
    if(!r.best) return;
    const fr=(r.el.AF7+r.el.AF8)/2, po=(r.el.TP9+r.el.TP10)/2;
    if(!isFinite(fr)||!isFinite(po)) return;
    const g=fr-po;
    const latF=r.el.AF8-r.el.AF7, latP=r.el.TP10-r.el.TP9;
    out.push(`<li><b>Topografi ${r.nama}.</b> Rata-rata z frontal ${fx(fr)} vs posterior ${fx(po)} (selisih ${fx(g)}) — `
      + (g>0.3 ? "rasio β/α lebih tinggi di frontal, konsisten dengan beban pemrosesan frontal yang lebih besar"
       : g<-0.3 ? "rasio β/α lebih tinggi di posterior; frontal relatif lebih ber-α"
                : "gradien frontal–posterior tipis")
      + `. Beda kanan−kiri frontal ${fx(latF)}, posterior ${fx(latP)}. `
      + `<i>Catatan: ini selisih log β/α antar-elektroda, bukan indeks frontal alpha asymmetry baku, dan tidak boleh dibaca sebagai indeks pendekatan/penghindaran.</i></li>`);
  });
  return out;
}

function buildSheet(){
  const f=summaryFacts();
  const flags=summaryFlags(f);
  const q=(o,k)=> o&&o.n_valid ? `${o.q[k]} (${(o.q[k]/o.n_valid*100).toFixed(1)}%)` : "—";
  const now=new Date();
  const tgl=now.toLocaleString("id-ID",{dateStyle:"long",timeStyle:"short"});

  let baris=f.ruas.map(r=>`<tr>
    <td><b>${r.nama}</b> ${fu(r.t0,0)}–${fu(r.t1,0)}s</td>
    <td class="num">${r.n}</td><td class="num">${r.nY}</td>
    <td class="num">${fu(r.mx,2)}</td><td class="num">${fu(r.my,2)}</td><td class="num">${fu(r.mr,1)}</td>
    ${["Q1","Q2","Q3","Q4"].map(k=>`<td class="num">${q(r.o,k)}</td>`).join("")}
    <td class="num">${r.o?r.o.n_excluded:"—"}</td>
    <td>${r.best?esc(r.best)+" ("+fx(r.bestVal)+")":"—"}</td></tr>`).join("");

  const pergeseran = f.shift
    ? `<li>Dari <b>${f.shift.dari}</b> ke <b>${f.shift.ke}</b>, pergeseran okupansi terbesar pada
        <b>${f.shift.top}</b> sebesar ${f.shift.q[f.shift.top]>=0?"+":""}${f.shift.q[f.shift.top].toFixed(1)} poin persen
        (${["Q1","Q2","Q3","Q4"].map(k=>`${k} ${f.shift.q[k]>=0?"+":""}${f.shift.q[k].toFixed(1)}`).join(" · ")}).</li>`
    : "";

  document.getElementById("printSheet").innerHTML = `
    <h2>Ringkasan hasil — ${esc(D.session_id)}</h2>
    <div class="meta">Dicetak ${esc(tgl)} · kontrak ${esc(D.contract)}</div>

    <h3>1 · Hasil</h3>
    <ul>
      <li>Rekaman ${fu(f.tM,1)} s · ${f.n} window CASS · ${f.nSeg} ruas pengamatan${
        f.nSeg>1?`, marker pada ${sortedSplits().map(t=>fu(t,1)+" s").join(", ")}`:" (tanpa marker)"}.</li>
      <li>Bukti autonomic (RR Polar) tersedia pada <b>${f.nY} dari ${f.n}</b> window; ${f.excl} window dikecualikan dari bidang CASS.</li>
      <li>Seluruh sesi: kuadran terbanyak <b>${f.topAll}</b> — ${q(f.all,f.topAll)} dari ${f.all.n_valid} window valid.</li>
      ${f.ruas.filter(r=>r.tq).map(r=>`<li>${r.nama} (${fu(r.t0,0)}–${fu(r.t1,0)} s): terbanyak <b>${r.tq}</b> ${q(r.o,r.tq)};
          median X ${fu(r.mx,2)} · median Y ${fu(r.my,2)} · median RMSSD ${fu(r.mr,1)} ms;
          rata-rata z elektroda tertinggi ${r.best?esc(r.best)+" ("+fx(r.bestVal)+")":"—"}.</li>`).join("")}
      ${pergeseran}
    </ul>

    <table><thead><tr>
      <th>Ruas</th><th class="num">n window</th><th class="num">n Y valid</th>
      <th class="num">median X (z)</th><th class="num">median Y (z)</th><th class="num">median RMSSD</th>
      <th class="num">Q1</th><th class="num">Q2</th><th class="num">Q3</th><th class="num">Q4</th>
      <th class="num">dikecualikan</th><th>elektroda tertinggi</th>
    </tr></thead><tbody>${baris}</tbody></table>

    <h3>2 · Pembacaan pola menurut kerangka CASS</h3>
    <p class="tafsir-hd">Bagian ini <b>tafsir</b>, bukan hasil hitungan langsung. Aturannya disusun di muka
      dari makna kedua sumbu dan dijalankan apa adanya oleh berkas ini — tanpa internet dan tanpa model
      bahasa saat pencetakan, sehingga hasilnya sama setiap kali. Setiap kalimat disertai angka yang
      mendasarinya. Definisi kuadran dan cara membaca angka perbandingan ada di segmen 3.</p>
    <ul class="tafsir">${bacaCASS(f).join("")}</ul>

    <div class="metode">
    <h3>3 · Catatan metode dan keterbatasan</h3>

      <h4>3.1 Definisi sumbu dan kuadran</h4>
      <p>X = <b>${esc(D.cortical_metric)}</b> per elektroda, dirata-ratakan atas empat elektroda, lalu di-robust-z
        terhadap ruas <b>R0</b>. X naik = β menguat relatif terhadap α (korteks teraktivasi); X turun = α menguat
        (korteks melambat). Y = <b>${esc(D.autonomic_scalar)}</b> di-robust-z; Y naik = modulasi vagal menguat.</p>
      <table class="kamus"><thead><tr><th>Kuadran</th><th>Tanda</th><th>Dibaca sebagai</th></tr></thead><tbody>
        ${["Q1","Q2","Q3","Q4"].map(k=>`<tr${k===f.topAll?' class="hi"':''}><td><b>${k}</b></td>
          <td>${k==="Q1"?"X↑ Y↑":k==="Q2"?"X↓ Y↑":k==="Q3"?"X↓ Y↓":"X↑ Y↓"}</td>
          <td><b>${QBACA[k].nama}</b> — ${QBACA[k].arti}</td></tr>`).join("")}
      </tbody></table>

      <h4>3.2 Parameter pengolahan</h4>
      <ul>
        <li>Window CASS ${D.window_s||5} s, langkah ${D.step_s||2.5} s — tumpang-tindih
            ${Math.round((1-(D.step_s||2.5)/(D.window_s||5))*100)}%.</li>
        <li>Acuan robust-z: ruas <b>R0</b> (median dan 1,4826 × MAD).</li>
        <li>Ambang bukti RR Polar: minimal ${D.min_ibi} IBI per window; RMSSD dihaluskan segitiga ±5 s;
            pusat Y = R0, skala Y = seluruh sesi.</li>
        <li>Lebar kolom heatmap kepala ${fu(D.ruas_s||30,0)} s. Satu sel = satu elektroda, tanpa interpolasi anatomis.</li>
        <li>Domain tampilan ±3; nilai di luar domain digambar menempel di tepi dan ditandai.</li>
      </ul>

      <h4>3.3 Cara membaca angka perbandingan antar-ruas</h4>
      <p>${CARA_BACA_ANGKA}</p>

      <h4>3.4 Peringatan untuk sesi ini</h4>
      ${flags.length ? flags.map(x=>`<div class="flag">${x}</div>`).join("")
                     : `<p>Tidak ada peringatan otomatis untuk sesi ini.</p>`}

      <h4>3.5 Berlaku untuk setiap sesi</h4>
      <p class="note2">R0 adalah acuan robust-z, jadi median X ruas R0 mendekati nol secara konstruksi;
        perbandingan ruas lain bersifat relatif terhadap acuan itu, bukan terhadap norma populasi.
        Window invalid dikecualikan, bukan dianggap nol — bukti RR Polar yang tidak memadai bukan berarti
        keadaan otonom yang buruk. Selisih log β/α antar-elektroda bukan indeks frontal alpha asymmetry
        baku dan tidak boleh dibaca sebagai indeks pendekatan/penghindaran. Seluruh isi lembar ini
        deskriptif atau tafsir berlabel — tidak ada pernyataan sebab-akibat maupun klaim klinis.</p>
      <p class="note2"><b>Kontrak ${esc(D.contract)}</b> · deskriptif, bukan inferensial.</p>
    </div>`;
}

/* ---------- orkestrasi ---------- */
let raf=0;
function drawAll(){ drawHead(); drawMap(); drawKpi(); drawOcc(); drawTime(); }
function scheduleDraw(){
  if(raf) cancelAnimationFrame(raf);
  raf = requestAnimationFrame(()=>{ raf=0; drawAll(); });
}
function refreshAll(){ renderChips(); renderStats(); renderEvents(); scheduleDraw(); }

function loadSession(i){
  si = i;
  D = SESSIONS[i];
  W = D.windows; CH = D.channels;
  splits = MARK[i].splits.slice();
  splitLabels = Object.assign({}, MARK[i].labels);
  idx = 0;
  const sl=document.getElementById("slider");
  sl.max = Math.max(0, W.length - 1); sl.value = 0;
  let lim = 0;
  W.forEach(w=>CH.forEach(c=>{
    const v=w.ch[c] && w.ch[c].raw;
    if(v!==null && v!==undefined && isFinite(v)) lim=Math.max(lim, Math.abs(v));
  }));
  rawLim = lim>1e-9 ? lim : 1;
  rebuildFromMarker();
  renderContract();
  refreshAll();
}
function renderContract(){
  const nY = W.filter(w=>w.autonomic_valid).length;
  document.getElementById("contract").innerHTML = `
    <b>Kontrak ${esc(D.contract)}</b> · X = ${esc(D.cortical_metric)} robust-z acuan R0 ·
    Y = ${esc(D.autonomic_scalar)} (ambang ${D.min_ibi} IBI; RMSSD dihaluskan ±5 s; pusat Y = R0, skala Y = sesi) ·
    Autonomic valid <b>${nY}/${W.length}</b> window · 1 sel = 1 elektroda, tanpa interpolasi anatomis ·
    window tumpang-tindih — sel bukan observasi independen ·
    window invalid dikecualikan, bukan dinolkan · <b>deskriptif, bukan inferensial</b>`;
}

/* pemilih peseta — tersembunyi kalau hanya satu sesi */
(function initParticipants(){
  const wrap=document.getElementById("partWrap"), sel=document.getElementById("partSel");
  if(SESSIONS.length<2) return;
  wrap.hidden=false;
  sel.innerHTML = SESSIONS.map((s,i)=>
    `<option value="${i}">${esc(s.session_id)}</option>`).join("");
  sel.addEventListener("change", ()=>{ loadSession(+sel.value); });
})();

document.getElementById("resetMark").onclick=()=>{
  const d=SESSIONS[si].default_marker_s;
  splits = (d===null||d===undefined) ? [] : [Number(d)];
  splitLabels = (d===null||d===undefined) ? {} : {[Number(d)]:"asal"};
  commitMarkers();
};
document.getElementById("addEv").onclick=()=>{
  const t=parseFloat(document.getElementById("newEvT").value);
  const lab=document.getElementById("newEvL").value||"";
  if(!isFinite(t)) return;
  splits.push(t);
  if(lab) splitLabels[t]=lab;
  commitMarkers();
};
const markPop=document.getElementById("markPop");
document.getElementById("markBtn").onclick=(e)=>{ e.stopPropagation(); markPop.hidden=!markPop.hidden; };
markPop.addEventListener("click", e=>e.stopPropagation());
document.addEventListener("click", ()=>{ markPop.hidden=true; });

const slider=document.getElementById("slider");
slider.addEventListener("input", e=>{ idx=+e.target.value; drawMap(); drawKpi(); drawTime(); });
document.addEventListener("keydown", e=>{
  if(e.target.matches("input,textarea,select")) return;
  if(e.key==="ArrowRight" || e.key==="l"){ idx=Math.min(W.length-1, idx+1); slider.value=idx; drawMap(); drawKpi(); drawTime(); }
  if(e.key==="ArrowLeft"  || e.key==="h"){ idx=Math.max(0, idx-1); slider.value=idx; drawMap(); drawKpi(); drawTime(); }
  if(e.key==="Home"){ idx=0; slider.value=idx; drawMap(); drawKpi(); drawTime(); }
  if(e.key==="End"){ idx=W.length-1; slider.value=idx; drawMap(); drawKpi(); drawTime(); }
});
document.getElementById("themeBtn").addEventListener("click", ()=>{
  const cur=document.documentElement.getAttribute("data-theme");
  const next = cur==="dark" ? "light" : cur==="light" ? "" : "dark";
  if(next) document.documentElement.setAttribute("data-theme", next);
  else document.documentElement.removeAttribute("data-theme");
  scheduleDraw();
});
const hSeg=document.getElementById("hmodeSeg");
hSeg.querySelectorAll('input[name=hmode]').forEach(r=>r.addEventListener("change", ()=>{
  syncSeg(hSeg); drawHead();
}));
const tSeg=document.getElementById("tmodeSeg");
["tRuas","tPts"].forEach(id=>{
  const el=document.getElementById(id);
  if(el) el.addEventListener("change", ()=>{ syncSeg(tSeg); drawTime(); });
});
/* klik di lintasan waktu memindahkan window terpilih */
document.getElementById("timeSvg").addEventListener("click", ev=>{
  const r=ev.currentTarget.getBoundingClientRect();
  const tM=tmaxNow(), padL=30, padR=7;
  const t=((ev.clientX-r.left-padL)/Math.max(1,r.width-padL-padR))*tM;
  let best=0, bd=Infinity;
  W.forEach((x,i)=>{ const d=Math.abs(x.tm-t); if(d<bd){bd=d; best=i;} });
  idx=best; document.getElementById("slider").value=idx;
  drawMap(); drawKpi(); drawTime();
});
const oSeg=document.getElementById("occSeg");
["occDens","occLayer","occPts"].forEach(id=>{
  const el=document.getElementById(id);
  if(el) el.addEventListener("change", ()=>{ syncSeg(oSeg); drawOcc(); });
});
/* cetak: paksa palet terang, gambar ulang pada ukuran halaman, siapkan lembar 2 */
function sebelumCetak(){ PRINTING=true; buildSheet(); drawAll(); }
function sesudahCetak(){ PRINTING=false; scheduleDraw(); }
window.addEventListener("beforeprint", sebelumCetak);
window.addEventListener("afterprint", sesudahCetak);
const mqCetak = window.matchMedia("print");
if(mqCetak.addEventListener) mqCetak.addEventListener("change", e=>{ e.matches ? sebelumCetak() : sesudahCetak(); });
document.getElementById("pdfBtn").addEventListener("click", ()=>{
  markPop.hidden=true;
  sebelumCetak();
  window.print();
});
window.matchMedia("(prefers-color-scheme: dark)").addEventListener("change", scheduleDraw);
new ResizeObserver(scheduleDraw).observe(document.querySelector(".grid"));

loadSession(0);
</script>
</body>
</html>
"""


def build_html(payload):
    """payload: satu dict (satu sesi) atau list of dict (beberapa peserta).

    Bentuk list menghasilkan satu berkas dengan pemilih peserta di topbar;
    bentuk dict tetap dipakai apa adanya supaya pemanggil lama tidak berubah.
    """
    blob = json.dumps(payload, ensure_ascii=False, allow_nan=False,
                      separators=(",", ":"))
    blob = blob.replace("<", "\\u003c").replace(">", "\\u003e")
    return TEMPLATE.replace("__PAYLOAD__", blob)


def payload_from_csv(path, sid=None, marker_s=60.0, ruas_s=30.0, refs=None):
    """Bangun payload explorer dari cass_state_*.csv (tanpa pipeline)."""
    state = pd.read_csv(path)
    refs = refs or {
        "window_s": 5.0, "step_s": 2.5,
        "cortical_metric": "log_beta_alpha",
        "autonomic_scalar": "ppg2_prv_rmssd",
        "min_ibi": 8,
    }
    sid = sid or Path(path).stem.replace("cass_state_", "")
    return build_payload(state, refs, sid, marker_s, ruas_s=ruas_s)


DEFAULT_MARKER_S = 60.0  # same default as the CASS Wellness portal / payload_from_csv


def session_label(folder):
    """Participant-style name like the toolkit's session_id: <session name>__<YYYYMMDDTHHMMSS>."""
    import re
    from datetime import datetime
    folder = Path(folder)
    meta = {}
    try:
        meta = json.loads((folder / "session.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        pass
    name = re.sub(r"[^A-Za-z0-9_]+", "_", meta.get("name") or "").strip("_")
    start = meta.get("start_unix")
    if not name or not start:
        return folder.name
    return f"{name}__{datetime.fromtimestamp(start).strftime('%Y%m%dT%H%M%S')}"


def explorer_payload(folder, marker_s="default", ruas_s=30.0):
    """Payload for one musepolar session: X from Muse EEG, Y from Polar RR RMSSD.

    marker_s "default" = 60 s when the recording is long enough (as the toolkit), None = no marker.
    Normalisation here mirrors NB10 (robust z against R0); the page recomputes it
    in the browser whenever markers change.
    """
    from .engine import MIN_RR, RR_SPAN_S, STEP_S, WINDOW_S, _robust_location_scale, window_state

    if marker_s == "default":
        try:
            state, duration, _w = window_state(Path(folder), DEFAULT_MARKER_S)
            marker_s = DEFAULT_MARKER_S
        except ValueError:  # shorter than marker + 5 s: whole recording is R0
            marker_s = None
    if marker_s is None or marker_s != DEFAULT_MARKER_S:
        state, duration, _w = window_state(Path(folder), marker_s)
    state["window_id"] = range(len(state))
    ref = state["phase"].eq("PRE")
    for c in CHANNELS:
        loc, scale = _robust_location_scale(state.loc[ref, f"{c}_cortical_raw"])
        state[f"{c}_cortical_raw_z"] = (state[f"{c}_cortical_raw"] - loc) / scale
    zcols = [f"{c}_cortical_raw_z" for c in CHANNELS]
    state["cortical_state"] = state[zcols].mean(axis=1, skipna=True)
    loc, _ = _robust_location_scale(state.loc[ref, "polar_rr_rmssd"])
    _, scale = _robust_location_scale(state["polar_rr_rmssd"])
    state["autonomic_state"] = (state["polar_rr_rmssd"] - loc) / scale
    for c in CHANNELS:
        state[f"{c}_deviation"] = state[f"{c}_cortical_raw_z"] - state["cortical_state"]
    state["distance_reference"] = np.hypot(state["cortical_state"], state["autonomic_state"])
    x, y = state["cortical_state"], state["autonomic_state"]
    state["quadrant"] = np.select([(x >= 0) & (y >= 0), (x < 0) & (y >= 0), (x < 0) & (y < 0), (x >= 0) & (y < 0)],
                                  ["Q1", "Q2", "Q3", "Q4"], default="INVALID")
    state["autonomic_valid"] = np.isfinite(state["autonomic_state"])
    refs = {"window_s": WINDOW_S, "step_s": STEP_S, "cortical_metric": "log_beta_alpha",
            "autonomic_scalar": "polar_rr_rmssd", "min_ibi": MIN_RR, "rr_span_s": RR_SPAN_S}
    return build_payload(state, refs, session_label(folder), marker_s, ruas_s=ruas_s)


_CACHE = {}


def cached_payload(folder):
    """explorer_payload() memoised on the session's input files, so the multi-session page stays fast."""
    folder = Path(folder)
    key = tuple((f.name, f.stat().st_mtime_ns, f.stat().st_size)
                for f in (folder / "muse_eeg.csv", folder / "polar_rr.csv", folder / "session.json") if f.exists())
    hit = _CACHE.get(folder)
    if hit and hit[0] == key:
        return hit[1]
    payload = explorer_payload(folder)
    _CACHE[folder] = (key, payload)
    return payload
