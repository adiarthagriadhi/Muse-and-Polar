"""CorVa Space page (v0.3): the analysis of corva/session.py drawn for people.

One self-contained HTML page per session:
- the CorVa Space map: 3 × 3 grid (neutral zone |z| < 0.6), the trajectory of analysed windows and the
  median of each protocol phase (numbered 1–5);
- one card per phase: label, meaning, reading, Q3 qualifier, comparison with the expectation, medians with
  their magnitude, data coverage (confidence), cell occupancy, alternative names and citations;
- timelines of X and Y per window with the phase boundaries and settling minutes;
- CSV export (per phase, per window) and print / PDF.

Encoding of the five phases on the map: colour = breathing (blue spontaneous, orange slow), shape = eyes
(circle open, square closed), grey = baseline R0; every phase median also carries its number.
"""

from __future__ import annotations

import json

from . import labels, protocol


def _page_data(result: dict, others: list[dict], current: str) -> dict:
    refs = labels.references()
    used = set()
    for p in result["phases"]:
        used.update(p["label"]["refs"])
        used.update(p["expected_refs"])
    cites = {k: {"cite": labels.cite(k), "title": refs[k]["title"], "doi": refs[k]["doi"],
                 "ok": bool(refs[k]["authors_complete"] and refs[k]["doi_verified"])}
             for k in sorted(used) if k in refs}
    cells = {code: {"label": label, "meaning": meaning} for code, label, meaning in [*labels.CELLS.values(), labels.NO_DATA]}
    phases = [{"id": p["id"], "num": i + 1, "name": p["name"], "eyes": p["eyes"], "breathing": p["breathing"],
               "reference": p["reference"]} for i, p in enumerate(protocol.PROTOCOL)]
    return {"result": result, "sessions": others, "current": current, "cites": cites, "cells": cells,
            "protocol": phases, "threshold": labels.THRESHOLD_Z}


def build_html(result: dict, others: list[dict], current: str) -> str:
    data = json.dumps(_page_data(result, others, current), ensure_ascii=False, allow_nan=False)
    data = data.replace("</", "<\\/")  # keep the JSON inside its <script> element
    return TEMPLATE.replace("/*__DATA__*/", data)


TEMPLATE = r"""<!doctype html>
<html lang="id">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>CorVa Space</title>
<style>
:root {
  color-scheme: light;
  --bg: #f4f4f1; --surface-1: #fcfcfb; --surface-2: #f0efec; --border: #dddcd6; --grid: #e7e6e1;
  --axis: #8a8983; --text-primary: #0b0b0b; --text-secondary: #52514e; --text-muted: #7a7973;
  --series-1: #2a78d6; --series-2: #eb6834; --ref: #7a7973; --settle: #e9e8e3;
  --good: #0ca30c; --warning: #b77f00; --critical: #d03b3b; --link: #1665bc;
}
@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) {
    color-scheme: dark;
    --bg: #111110; --surface-1: #1a1a19; --surface-2: #232321; --border: #33332f; --grid: #2a2a27;
    --axis: #8f8e86; --text-primary: #ffffff; --text-secondary: #c3c2b7; --text-muted: #8f8e86;
    --series-1: #3987e5; --series-2: #d95926; --ref: #a3a299; --settle: #262624;
    --good: #2fbf2f; --warning: #e0a000; --critical: #e66767; --link: #8fb8f0;
  }
}
:root[data-theme="dark"] {
  color-scheme: dark;
  --bg: #111110; --surface-1: #1a1a19; --surface-2: #232321; --border: #33332f; --grid: #2a2a27;
  --axis: #8f8e86; --text-primary: #ffffff; --text-secondary: #c3c2b7; --text-muted: #8f8e86;
  --series-1: #3987e5; --series-2: #d95926; --ref: #a3a299; --settle: #262624;
  --good: #2fbf2f; --warning: #e0a000; --critical: #e66767; --link: #8fb8f0;
}
* { box-sizing: border-box; }
body { margin: 0; background: var(--bg); color: var(--text-primary); font: 14px/1.45 system-ui, -apple-system, "Segoe UI", sans-serif; }
a { color: var(--link); }
header { padding: 18px 16px 10px; max-width: 1180px; margin: 0 auto; }
header h1 { margin: 4px 0 2px; font-size: 22px; letter-spacing: -0.01em; }
.sub { color: var(--text-secondary); margin: 0; }
.tools { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; margin-top: 12px; }
.btn, select { font: inherit; color: var(--text-primary); background: var(--surface-1); border: 1px solid var(--border);
  border-radius: 8px; padding: 6px 10px; cursor: pointer; text-decoration: none; }
.btn:hover, select:hover { border-color: var(--axis); }
main { max-width: 1180px; margin: 0 auto; padding: 0 16px 40px; }
.panel { background: var(--surface-1); border: 1px solid var(--border); border-radius: 12px; padding: 16px; margin: 12px 0; }
.panel h2 { font-size: 15px; margin: 0 0 4px; }
.muted { color: var(--text-muted); }
.small { font-size: 12px; }
.notice { color: var(--text-secondary); font-size: 13px; }
.warn { margin: 8px 0 0; padding-left: 18px; color: var(--text-secondary); font-size: 13px; }
.summary { display: flex; flex-wrap: wrap; gap: 10px 28px; margin-top: 10px; }
.stat b { display: block; font-size: 22px; font-weight: 650; }
.stat span { color: var(--text-muted); font-size: 12px; }
.map-wrap { display: grid; grid-template-columns: minmax(0, 1fr) 260px; gap: 16px; align-items: start; }
@media (max-width: 820px) { .map-wrap { grid-template-columns: 1fr; } }
svg { display: block; width: 100%; height: auto; overflow: visible; }
svg.sw { display: inline-block; width: auto; flex: none; }
svg text { fill: var(--text-muted); font-size: 11px; }
svg .cell-name { fill: var(--text-muted); font-size: 12px; }
svg .cell-name, svg .cell-code { paint-order: stroke; stroke: var(--surface-1); stroke-width: 3px; stroke-linejoin: round; }
svg .cell-code { fill: var(--text-muted); font-size: 10px; letter-spacing: 0.04em; }
svg .axis-title { fill: var(--text-secondary); font-size: 12px; }
svg .num { fill: #fff; font-size: 11px; font-weight: 700; pointer-events: none; }
.legend { display: grid; gap: 6px; font-size: 13px; color: var(--text-secondary); }
.legend .row { display: flex; align-items: center; gap: 8px; }
.chips { display: flex; flex-wrap: wrap; gap: 6px; margin: 4px 0 10px; }
.chip { font: inherit; font-size: 12px; border: 1px solid var(--border); background: var(--surface-1); color: var(--text-secondary);
  border-radius: 999px; padding: 3px 10px; cursor: pointer; }
.chip[aria-pressed="true"] { background: var(--text-primary); color: var(--surface-1); border-color: var(--text-primary); }
.cards { display: grid; grid-template-columns: repeat(auto-fill, minmax(330px, 1fr)); gap: 12px; }
.card { background: var(--surface-1); border: 1px solid var(--border); border-radius: 12px; padding: 14px; break-inside: avoid; }
.card-head { display: flex; gap: 10px; align-items: flex-start; }
.card-head svg.sw { margin-top: 2px; }
.card h3 { margin: 0; font-size: 14px; }
.card .time { color: var(--text-muted); font-size: 12px; }
.lab { font-size: 19px; font-weight: 650; margin: 10px 0 0; }
.code { font: 11px ui-monospace, SFMono-Regular, Menlo, monospace; color: var(--text-muted); border: 1px solid var(--border);
  border-radius: 4px; padding: 0 4px; margin-left: 6px; vertical-align: 2px; }
.meaning { color: var(--text-secondary); margin: 2px 0 0; }
.reading { margin: 6px 0 0; }
.cmp { display: inline-flex; gap: 6px; align-items: center; margin-top: 10px; font-weight: 600; font-size: 13px; }
.cmp.good { color: var(--good); } .cmp.warning { color: var(--warning); } .cmp.ref, .cmp.none { color: var(--text-muted); }
dl { display: grid; grid-template-columns: max-content 1fr; gap: 3px 12px; margin: 10px 0 0; font-size: 13px; }
dt { color: var(--text-muted); } dd { margin: 0; font-variant-numeric: tabular-nums; }
.reasons { color: var(--critical); font-size: 13px; margin: 8px 0 0; }
.alts, .refs { color: var(--text-muted); font-size: 12px; margin: 8px 0 0; }
.tl-title { display: flex; justify-content: space-between; gap: 12px; margin: 10px 0 2px; font-size: 13px; color: var(--text-secondary); }
.tip { position: fixed; pointer-events: none; z-index: 10; background: var(--surface-1); color: var(--text-primary);
  border: 1px solid var(--border); border-radius: 8px; padding: 8px 10px; font-size: 12px; box-shadow: 0 4px 16px #0002;
  max-width: 260px; display: none; }
.tip b { display: block; margin-bottom: 2px; }
.reflist { font-size: 13px; color: var(--text-secondary); padding-left: 18px; }
.reflist li { margin: 3px 0; }
table { border-collapse: collapse; width: 100%; font-size: 13px; }
th, td { text-align: left; padding: 6px 8px; border-bottom: 1px solid var(--border); vertical-align: top; }
th { color: var(--text-muted); font-weight: 600; }
td.num { font-variant-numeric: tabular-nums; }
.table-wrap { overflow-x: auto; }
@media print {
  body { background: #fff; color: #000; }
  .tools, .chips, .tip, .no-print { display: none !important; }
  .panel, .card { border-color: #ccc; }
  main, header { max-width: none; }
}
</style>
</head>
<body>
<header>
  <a href="/" class="small no-print">← Muse–Polar Live</a>
  <h1>CorVa Space <span class="muted" style="font-weight:400">· CASS-NV</span></h1>
  <p class="sub" id="sub"></p>
  <div class="tools">
    <select id="sessionSel" aria-label="Pilih sesi"></select>
    <a class="btn" id="csvPhases">Unduh CSV fase</a>
    <a class="btn" id="csvWindows">Unduh CSV jendela</a>
    <button class="btn" id="printBtn">Cetak / PDF</button>
  </div>
</header>
<main>
  <section class="panel">
    <p class="notice">Label menggambarkan posisi <b>relatif terhadap acuan R0 orang ini sendiri</b> (baseline setelah menit
      stabilisasi), bukan norma populasi dan bukan diagnosis. Zona netral |z| &lt; <span id="thr"></span>.</p>
    <div class="summary" id="summary"></div>
    <ul class="warn" id="warnings"></ul>
  </section>

  <section class="panel">
    <h2>Peta CorVa Space</h2>
    <p class="muted small">Sumbu X = kondisi kortikal (z log β/α EEG Muse), sumbu Y = kondisi vagal (z lnRMSSD RR Polar).
      Titik kecil = jendela 5 s yang dianalisis; titik besar bernomor = median fase.</p>
    <div class="chips" id="chips" role="group" aria-label="Sorot fase"></div>
    <div class="map-wrap">
      <div id="map"></div>
      <div>
        <div class="legend" id="legend"></div>
        <label class="small no-print" style="display:block;margin-top:14px"><input type="checkbox" id="showSettle">
          tampilkan menit stabilisasi (titik berongga)</label>
      </div>
    </div>
  </section>

  <section>
    <h2 style="font-size:15px;margin:18px 0 8px">Label per fase</h2>
    <div class="cards" id="cards"></div>
  </section>

  <section class="panel">
    <h2>Lintasan waktu</h2>
    <p class="muted small">Pita abu-abu = zona netral; area arsir = menit stabilisasi (tidak dianalisis). Garis vertikal = awal fase.</p>
    <div class="tl-title"><span>X kortikal · z log(β/α)</span></div>
    <div id="tlx"></div>
    <div class="tl-title"><span>Y vagal · z lnRMSSD</span></div>
    <div id="tly"></div>
  </section>

  <section class="panel">
    <h2>Tabel fase</h2>
    <div class="table-wrap" id="table"></div>
  </section>

  <section class="panel">
    <h2>Metode dan rujukan</h2>
    <dl id="method"></dl>
    <ul class="reflist" id="refs"></ul>
    <p class="muted small">⚠ = DOI atau daftar penulis belum terverifikasi; cek naskah asli sebelum dikutip. Peta bukti lengkap:
      <code>corva/EVIDENCE.md</code>.</p>
  </section>
</main>
<div class="tip" id="tip" role="tooltip"></div>
<script id="corva-data" type="application/json">/*__DATA__*/</script>
<script>
(() => {
const D = JSON.parse(document.getElementById('corva-data').textContent);
const R = D.result, THR = D.threshold;
const $ = (id) => document.getElementById(id);
const esc = (t) => String(t ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]);
const fz = (v) => v == null ? '–' : (v < 0 ? '−' : '+') + Math.abs(v).toFixed(2);
const ft = (s) => s == null ? '–' : `${Math.floor(s / 60)}:${String(Math.floor(s % 60)).padStart(2, '0')}`;
const SPEC = Object.fromEntries(D.protocol.map((p) => [p.id, p]));
const PH = Object.fromEntries(R.phases.map((p) => [p.id, p]));
const cellName = (c) => (D.cells[c] || {}).label || c;
const color = (pid) => { const s = SPEC[pid]; return !s ? 'var(--axis)' : s.reference ? 'var(--ref)' : s.breathing === 'slow' ? 'var(--series-2)' : 'var(--series-1)'; };
const square = (pid) => SPEC[pid] && SPEC[pid].eyes === 'closed';
let focus = null;  // highlighted phase id

// ---------------------------------------------------------------- header
const name = (D.sessions.find((s) => s.id === D.current) || {}).name || D.current;
$('sub').textContent = `${name} · ${ft(R.duration_s)} menit rekaman · ${R.windows.length} jendela 5 s`;
document.title = `CorVa Space · ${name}`;
$('thr').textContent = String(THR).replace('.', ',');
$('sessionSel').innerHTML = D.sessions.map((s) => `<option value="${esc(s.id)}"${s.id === D.current ? ' selected' : ''}>${esc(s.name)}</option>`).join('');
$('sessionSel').addEventListener('change', (e) => { location.href = '/corva/session/' + encodeURIComponent(e.target.value); });
$('csvPhases').href = `/api/corva/export/${encodeURIComponent(D.current)}?level=phases`;
$('csvWindows').href = `/api/corva/export/${encodeURIComponent(D.current)}?level=windows`;
$('printBtn').addEventListener('click', () => window.print());

const r0 = R.r0;
$('summary').innerHTML = [
  [`${R.summary.n_as_expected} / ${R.summary.n_compared}`, 'fase sesuai harapan'],
  [r0.adequate ? '✓ memenuhi' : '✕ kurang', `R0: ${ft(r0.start)}–${ft(r0.end)}, ${r0.n_windows} jendela`],
  [`${Math.round(r0.rr_valid_s)} s`, 'RR valid di R0 (syarat ≥ 60 s)'],
  [`${Math.round(r0.eeg_clean_s)} s`, 'EEG bersih di R0 (syarat ≥ 40 s)'],
].map(([b, s]) => `<div class="stat"><b>${esc(b)}</b><span>${esc(s)}</span></div>`).join('');
$('warnings').innerHTML = R.warnings.map((w) => `<li>${esc(w)}</li>`).join('');

// ---------------------------------------------------------------- shared
const NS = 'http://www.w3.org/2000/svg';
function markShape(pid, x, y, r, extra = '') {
  const c = color(pid);
  if (square(pid)) return `<rect x="${x - r}" y="${y - r}" width="${2 * r}" height="${2 * r}" rx="1.5" ${extra.replace('FILL', c)}/>`;
  return `<circle cx="${x}" cy="${y}" r="${r}" ${extra.replace('FILL', c)}/>`;
}
function swatch(pid, r = 6) {
  return `<svg class="sw" viewBox="0 0 ${2 * r + 4} ${2 * r + 4}" width="${2 * r + 4}" height="${2 * r + 4}" aria-hidden="true">${markShape(pid, r + 2, r + 2, r, 'fill="FILL" stroke="var(--surface-1)" stroke-width="1.5"')}</svg>`;
}
const tip = $('tip');
function showTip(html, ev) {
  tip.innerHTML = html; tip.style.display = 'block';
  const w = tip.offsetWidth, h = tip.offsetHeight;
  let x = ev.clientX + 14, y = ev.clientY + 14;
  if (x + w > innerWidth - 8) x = ev.clientX - w - 14;
  if (y + h > innerHeight - 8) y = ev.clientY - h - 14;
  tip.style.left = x + 'px'; tip.style.top = y + 'px';
}
const hideTip = () => { tip.style.display = 'none'; };
function winTip(w) {
  const p = SPEC[w.phase_id];
  return `<b>${esc(p ? p.num + ' · ' + p.name : 'di luar protokol')}</b>${ft(w.t0)}–${ft(w.t1)}${w.analysed ? '' : ' · stabilisasi'}<br>`
    + `X ${fz(w.x_z)} · Y ${fz(w.y_z)}<br>${esc(cellName(w.code))}`
    + (w.rmssd_ms != null ? `<br><span class="muted">RMSSD ${w.rmssd_ms.toFixed(1)} ms</span>` : '');
}

// ---------------------------------------------------------------- legend + chips
$('legend').innerHTML = D.protocol.map((p) => {
  const rec = PH[p.id] && PH[p.id].recorded;
  return `<div class="row">${swatch(p.id)}<span><b>${p.num}</b> ${esc(p.name)}${rec ? '' : ' <span class="muted">(tidak direkam)</span>'}</span></div>`;
}).join('') + `<div class="muted small" style="margin-top:6px">Warna = napas (biru biasa, oranye dalam 6/menit), bentuk = mata (● terbuka, ■ tertutup), abu-abu = baseline R0. Pita tengah berarsir abu = sel Netral (|z| &lt; ${String(THR).replace('.', ',')} di kedua sumbu); garis putus = batas zona.</div>`;
function renderChips() {
  $('chips').innerHTML = [`<button class="chip" data-p="" aria-pressed="${focus === null}">Semua fase</button>`]
    .concat(D.protocol.map((p) => `<button class="chip" data-p="${p.id}" aria-pressed="${focus === p.id}">${p.num} · ${esc(p.name)}</button>`)).join('');
}
$('chips').addEventListener('click', (e) => {
  const b = e.target.closest('.chip'); if (!b) return;
  focus = b.dataset.p || null; renderChips(); drawMap();
});

// ---------------------------------------------------------------- map
const pts = R.windows.filter((w) => w.x_z != null && w.y_z != null);
const medians = R.phases.filter((p) => p.recorded && p.adequate && p.medians);
let L = 2.5;
{
  const vals = pts.filter((w) => w.analysed).flatMap((w) => [Math.abs(w.x_z), Math.abs(w.y_z)]).sort((a, b) => a - b);
  const q = vals.length ? vals[Math.floor(vals.length * 0.97)] : 0;
  const m = Math.max(0, ...medians.flatMap((p) => [Math.abs(p.medians.x_z), Math.abs(p.medians.y_z)]));
  L = Math.min(8, Math.max(2.5, Math.ceil(Math.max(q, m * 1.15) * 2) / 2));
}
const MW = 560, MH = 520, pl = 46, pr = 12, pt = 12, pb = 42;
const sx = (z) => pl + (Math.max(-L, Math.min(L, z)) + L) / (2 * L) * (MW - pl - pr);
const sy = (z) => pt + (L - Math.max(-L, Math.min(L, z))) / (2 * L) * (MH - pt - pb);
let hitList = [];
function drawMap() {
  const showSettle = $('showSettle').checked;
  const o = [];
  o.push(`<rect x="${sx(-THR)}" y="${sy(THR)}" width="${sx(THR) - sx(-THR)}" height="${sy(-THR) - sy(THR)}" fill="var(--surface-2)"/>`);
  for (let t = Math.ceil(-L); t <= L; t++) {
    o.push(`<line x1="${sx(t)}" x2="${sx(t)}" y1="${pt}" y2="${MH - pb}" stroke="var(--grid)"/>`);
    o.push(`<line y1="${sy(t)}" y2="${sy(t)}" x1="${pl}" x2="${MW - pr}" stroke="var(--grid)"/>`);
    o.push(`<text x="${sx(t)}" y="${MH - pb + 15}" text-anchor="middle">${t > 0 ? '+' + t : t < 0 ? '−' + -t : 0}</text>`);
    o.push(`<text x="${pl - 6}" y="${sy(t) + 4}" text-anchor="end">${t > 0 ? '+' + t : t < 0 ? '−' + -t : 0}</text>`);
  }
  for (const v of [-THR, THR]) {
    o.push(`<line x1="${sx(v)}" x2="${sx(v)}" y1="${pt}" y2="${MH - pb}" stroke="var(--axis)" stroke-dasharray="4 4"/>`);
    o.push(`<line y1="${sy(v)}" y2="${sy(v)}" x1="${pl}" x2="${MW - pr}" stroke="var(--axis)" stroke-dasharray="4 4"/>`);
  }
  // cell names sit at the outer edge of each cell, away from where the points gather
  const lx = { low: [pl + 8, 'start'], neutral: [sx(0), 'middle'], high: [MW - pr - 8, 'end'] };
  const ly = { high: pt + 16, neutral: sy(THR) - 18, low: MH - pb - 22 };
  const zones = { low: 'low', neutral: 'neutral', high: 'high' };
  const cellOf = { 'high,high': 'Q1', 'low,high': 'Q2', 'low,low': 'Q3', 'high,low': 'Q4', 'high,neutral': 'X_HIGH',
    'low,neutral': 'X_LOW', 'neutral,high': 'Y_HIGH', 'neutral,low': 'Y_LOW', 'neutral,neutral': 'NEUTRAL' };
  for (const zx in zones) for (const zy in zones) {
    const code = cellOf[zx + ',' + zy];
    if (code === 'NEUTRAL') continue;  // the shaded centre band is the neutral cell (named in the legend)
    const [x, anchor] = lx[zx], y = ly[zy];
    o.push(`<text class="cell-code" x="${x}" y="${y}" text-anchor="${anchor}">${code}</text>`);
    o.push(`<text class="cell-name" x="${x}" y="${y + 13}" text-anchor="${anchor}">${esc(cellName(code))}</text>`);
  }
  o.push(`<text class="axis-title" x="${(pl + MW - pr) / 2}" y="${MH - 6}" text-anchor="middle">X kortikal · z log(β/α) →</text>`);
  o.push(`<text class="axis-title" transform="translate(12 ${(pt + MH - pb) / 2}) rotate(-90)" text-anchor="middle">Y vagal · z lnRMSSD →</text>`);
  hitList = [];
  for (const w of pts) {
    if (!w.analysed && !showSettle) continue;
    const dim = focus && w.phase_id !== focus;
    const x = sx(w.x_z), y = sy(w.y_z);
    const style = w.analysed ? `fill="FILL" fill-opacity="${dim ? 0.08 : 0.55}" stroke="var(--surface-1)" stroke-width="1"`
      : `fill="none" stroke="FILL" stroke-opacity="${dim ? 0.12 : 0.7}" stroke-width="1.2"`;
    o.push(markShape(w.phase_id, x, y, 4, style));
    if (!dim) hitList.push({ x, y, html: winTip(w) });
  }
  for (const p of medians) {
    const s = SPEC[p.id], dim = focus && p.id !== focus;
    const x = sx(p.medians.x_z), y = sy(p.medians.y_z);
    o.push(`<g opacity="${dim ? 0.25 : 1}">${markShape(p.id, x, y, 10, 'fill="FILL" stroke="var(--surface-1)" stroke-width="2.5"')}`
      + `<text class="num" x="${x}" y="${y + 4}" text-anchor="middle">${s.num}</text></g>`);
    hitList.push({ x, y, r: 12, html: `<b>${s.num} · ${esc(p.name)} (median)</b>X ${fz(p.medians.x_z)} · Y ${fz(p.medians.y_z)}<br>${esc(p.label.label)} · ${esc(p.comparison || '')}` });
  }
  $('map').innerHTML = `<svg id="mapSvg" viewBox="0 0 ${MW} ${MH}" role="img" aria-label="Peta CorVa Space: median fase dan jendela pada grid 3 kali 3">${o.join('')}</svg>`;
  const svg = $('mapSvg');
  svg.addEventListener('mousemove', (ev) => {
    const b = svg.getBoundingClientRect(), k = MW / b.width;
    const mx = (ev.clientX - b.left) * k, my = (ev.clientY - b.top) * k;
    let best = null, bd = 14 * k;
    for (const h of hitList) { const d = Math.hypot(h.x - mx, h.y - my) - (h.r || 0); if (d < bd) { bd = d; best = h; } }
    best ? showTip(best.html, ev) : hideTip();
  });
  svg.addEventListener('mouseleave', hideTip);
}
$('showSettle').addEventListener('change', drawMap);
renderChips();
drawMap();

// ---------------------------------------------------------------- phase cards
const cmpClass = { 'sesuai harapan': ['good', '✓'], 'berbeda dari harapan': ['warning', '≠'], 'acuan (R0)': ['ref', '◎'] };
const citeList = (keys) => keys.filter((k) => D.cites[k]).map((k) => esc(D.cites[k].cite) + (D.cites[k].ok ? '' : ' ⚠')).join('; ');
$('cards').innerHTML = R.phases.map((p) => {
  const s = SPEC[p.id], lab = p.label;
  const [cls, icon] = cmpClass[p.comparison] || ['none', '—'];
  const exp = p.expected.map((c) => `${esc(cellName(c))} <span class="code">${c}</span>`).join(' atau ');
  const time = p.recorded ? `${ft(p.start)}–${ft(p.end)} · dianalisis ${ft(p.analysis_start)}–${ft(p.analysis_end)}` : 'tidak direkam';
  let body = `<div class="lab">${esc(lab.label)}<span class="code">${lab.code}</span></div><p class="meaning">${esc(lab.meaning)}</p>`;
  if (lab.phase_reading) body += `<p class="reading">Bacaan saat istirahat: <b>${esc(lab.phase_reading)}</b></p>`;
  if (lab.qualifier) body += `<p class="reading">Penanda tambahan: <b>${esc(lab.qualifier)}</b></p>`;
  body += `<div class="cmp ${cls}"><span aria-hidden="true">${icon}</span>${esc(p.comparison || 'tidak dibandingkan')}</div>`;
  body += `<p class="muted small" style="margin:2px 0 0">Harapan: ${p.reference ? 'acuan R0 (netral)' : exp}</p>`;
  if (p.recorded) {
    const m = p.medians, d = p.data;
    const occ = Object.entries(p.occupancy).sort((a, b) => b[1] - a[1]).slice(0, 3)
      .map(([c, v]) => `${esc(cellName(c))} ${Math.round(v * 100)} %`).join(' · ') || '–';
    body += `<dl><dt>X kortikal</dt><dd>${fz(m.x_z)}${lab.x_magnitude ? ' · ' + esc(lab.x_magnitude) : ''}</dd>`
      + `<dt>Y vagal</dt><dd>${fz(m.y_z)}${lab.y_magnitude ? ' · ' + esc(lab.y_magnitude) : ''}</dd>`
      + `<dt>θ/β · β/(α+θ)</dt><dd>${fz(m.theta_beta_z)} · ${fz(m.engagement_z)}</dd>`
      + `<dt>RMSSD ruas</dt><dd>${p.segment_rmssd_ms != null ? p.segment_rmssd_ms.toFixed(1) + ' ms' : '–'}</dd>`
      + `<dt>Keyakinan</dt><dd>${d.n_windows} jendela, ${Math.round(d.valid_fraction * 100)} % valid<br>RR valid ${Math.round(d.rr_valid_s)} s · EEG bersih ${Math.round(d.eeg_clean_s)} s</dd>`
      + `<dt>Okupansi</dt><dd>${occ}</dd></dl>`;
  }
  if (p.reasons && p.reasons.length) body += `<p class="reasons">✕ ${p.reasons.map(esc).join('; ')}</p>`;
  if (lab.alternatives.length) body += `<p class="alts">Juga disebut: ${lab.alternatives.map((a) => esc(a.name) + (a.kind === 'analogi' ? ' (analogi)' : '')).join('; ')}</p>`;
  const refs = citeList([...new Set([...lab.refs, ...p.expected_refs])]);
  if (refs) body += `<p class="refs">Rujukan: ${refs}</p>`;
  return `<article class="card"><div class="card-head">${swatch(p.id, 8)}<div><h3>${s.num} · ${esc(p.name)}</h3><div class="time">${time}</div></div></div>${body}</article>`;
}).join('');

// ---------------------------------------------------------------- timelines (one axis each)
const TW = 1100, TH = 150, tl = 46, tr = 12, tt = 16, tb = 22;
const dur = R.duration_s || 1;
const tx = (t) => tl + t / dur * (TW - tl - tr);
function timeline(el, key) {
  const vals = R.windows.map((w) => w[key]).filter((v) => v != null);
  const lim = Math.min(8, Math.max(2, Math.ceil(Math.max(...vals.map(Math.abs), 1) * 1.1)));
  const ty = (z) => tt + (lim - Math.max(-lim, Math.min(lim, z))) / (2 * lim) * (TH - tt - tb);
  const o = [`<defs><pattern id="hatch-${key}" width="6" height="6" patternUnits="userSpaceOnUse" patternTransform="rotate(45)"><rect width="6" height="6" fill="var(--settle)"/><line x1="0" y1="0" x2="0" y2="6" stroke="var(--grid)" stroke-width="2"/></pattern></defs>`];
  for (const p of R.phases.filter((p) => p.recorded)) {
    o.push(`<rect x="${tx(p.start)}" y="${tt}" width="${Math.max(0, tx(Math.min(p.analysis_start, p.end)) - tx(p.start))}" height="${TH - tt - tb}" fill="url(#hatch-${key})"/>`);
  }
  o.push(`<rect x="${tl}" y="${ty(THR)}" width="${TW - tl - tr}" height="${ty(-THR) - ty(THR)}" fill="var(--surface-2)" fill-opacity="0.9"/>`);
  for (const t of [-lim, 0, lim]) {
    o.push(`<line x1="${tl}" x2="${TW - tr}" y1="${ty(t)}" y2="${ty(t)}" stroke="${t === 0 ? 'var(--axis)' : 'var(--grid)'}"/>`);
    o.push(`<text x="${tl - 6}" y="${ty(t) + 4}" text-anchor="end">${t > 0 ? '+' + t : t < 0 ? '−' + -t : 0}</text>`);
  }
  for (const p of R.phases.filter((p) => p.recorded)) {
    o.push(`<line x1="${tx(p.start)}" x2="${tx(p.start)}" y1="${tt - 4}" y2="${TH - tb}" stroke="var(--axis)"/>`);
    o.push(`<text x="${tx(p.start) + 4}" y="${tt - 4}">${SPEC[p.id].num}</text>`);
  }
  for (let m = 0; m <= dur / 60; m += (dur > 1200 ? 5 : dur > 300 ? 2 : 1)) o.push(`<text x="${tx(m * 60)}" y="${TH - 6}" text-anchor="middle">${m}′</text>`);
  let d = '', pen = false;
  for (const w of R.windows) {
    if (w[key] == null) { pen = false; continue; }
    d += `${pen ? 'L' : 'M'}${tx(w.tm).toFixed(1)},${ty(w[key]).toFixed(1)}`; pen = true;
  }
  o.push(`<path d="${d}" fill="none" stroke="var(--series-1)" stroke-width="2" stroke-linejoin="round"/>`);
  o.push(`<line id="cross-${key}" y1="${tt}" y2="${TH - tb}" stroke="var(--text-muted)" visibility="hidden"/><circle id="dot-${key}" r="4" fill="var(--series-1)" stroke="var(--surface-1)" stroke-width="2" visibility="hidden"/>`);
  el.innerHTML = `<svg viewBox="0 0 ${TW} ${TH}" role="img" aria-label="Lintasan ${key} per jendela">${o.join('')}</svg>`;
  const svg = el.firstChild, cross = svg.querySelector(`#cross-${key}`), dot = svg.querySelector(`#dot-${key}`);
  svg.addEventListener('mousemove', (ev) => {
    const b = svg.getBoundingClientRect(), t = ((ev.clientX - b.left) * TW / b.width - tl) / (TW - tl - tr) * dur;
    let best = null, bd = Infinity;
    for (const w of R.windows) { const dd = Math.abs(w.tm - t); if (dd < bd) { bd = dd; best = w; } }
    if (!best) return;
    cross.setAttribute('x1', tx(best.tm)); cross.setAttribute('x2', tx(best.tm)); cross.setAttribute('visibility', 'visible');
    if (best[key] != null) { dot.setAttribute('cx', tx(best.tm)); dot.setAttribute('cy', ty(best[key])); dot.setAttribute('visibility', 'visible'); }
    else dot.setAttribute('visibility', 'hidden');
    showTip(winTip(best), ev);
  });
  svg.addEventListener('mouseleave', () => { cross.setAttribute('visibility', 'hidden'); dot.setAttribute('visibility', 'hidden'); hideTip(); });
}
timeline($('tlx'), 'x_z');
timeline($('tly'), 'y_z');

// ---------------------------------------------------------------- table view
$('table').innerHTML = `<table><thead><tr><th>Fase</th><th>Label</th><th>Perbandingan</th><th>X z</th><th>Y z</th><th>θ/β z</th><th>RR valid</th><th>EEG bersih</th></tr></thead><tbody>`
  + R.phases.map((p) => `<tr><td>${SPEC[p.id].num} · ${esc(p.name)}</td><td>${esc(p.label.label)} <span class="code">${p.label.code}</span></td>`
    + `<td>${esc(p.comparison || (p.reasons || []).join('; '))}</td>`
    + `<td class="num">${fz(p.medians && p.medians.x_z)}</td><td class="num">${fz(p.medians && p.medians.y_z)}</td><td class="num">${fz(p.medians && p.medians.theta_beta_z)}</td>`
    + `<td class="num">${p.data ? Math.round(p.data.rr_valid_s) + ' s' : '–'}</td><td class="num">${p.data ? Math.round(p.data.eeg_clean_s) + ' s' : '–'}</td></tr>`).join('')
  + `</tbody></table>`;

// ---------------------------------------------------------------- method + references
const M = R.method;
$('method').innerHTML = [
  ['Sumbu X', M.x], ['Sumbu Y', M.y], ['Penanda Q3', M.q3_marker], ['Pembanding X', M.comparison_x],
  ['Normalisasi', M.normalization], ['Syarat label fase', `≥ ${M.min_rr_s} s RR valid dan ≥ ${M.min_eeg_s} s EEG bersih per ruas analisis`],
  ['Jendela', `${M.window_s} s, RMSSD dari rentang RR ${M.rr_span_s} s`], ['Artefak EEG', M.eeg_artifact], ['Versi mesin', R.version],
].map(([k, v]) => `<dt>${esc(k)}</dt><dd>${esc(v)}</dd>`).join('');
$('refs').innerHTML = Object.entries(D.cites).map(([k, c]) => `<li>${esc(c.cite)}${c.ok ? '' : ' ⚠'}. ${esc(c.title)}.${c.doi ? ` <a href="https://doi.org/${encodeURIComponent(c.doi).replace(/%2F/g, '/')}" target="_blank" rel="noopener">doi:${esc(c.doi)}</a>` : ''}</li>`).join('');
})();
</script>
</body>
</html>
"""
