import { Chart, ChartGroup, css, drawTopo, fmtNum, fmtTime, layeredCss } from './charts.js';

const $ = (id) => document.getElementById(id);
const CH = ['TP9', 'AF7', 'AF8', 'TP10'];
const SYM = { delta: 'δ', theta: 'θ', alpha: 'α', beta: 'β' };
const MEASURES = ['AF', 'AF7', 'AF8', 'TP9', 'TP10', 'Asimetri AF'];
const MEASURE_LABEL = { AF: 'AF rata-rata', 'Asimetri AF': 'Asimetri AF' };
const store = {
  get(k) { try { return localStorage.getItem(k); } catch { return null; } },
  set(k, v) { try { localStorage.setItem(k, v); } catch { /* private mode */ } },
};

const S = {
  root: '', sessions: [], sid: null, ov: null, res: null,
  set: { titik: '', band: 'alpha', metric: 'abs', ref: 0, art: 100 },
  mapT: 0, mapWin: 20, mapMode: 'value', measure: 'AF', psdCh: 'AF',
  anaReq: 0, sigReq: 0,
};

// --- tiny DOM helper (text is always set as text, never parsed as HTML) -----------
function h(tag, attrs = {}, ...kids) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v === null || v === undefined || v === false) continue;
    if (k === 'class') el.className = v;
    else if (k === 'style') el.style.cssText = v;
    else if (k.startsWith('on')) el.addEventListener(k.slice(2), v);
    else el.setAttribute(k, v === true ? '' : v);
  }
  for (const c of kids.flat(Infinity)) if (c !== null && c !== undefined && c !== false) el.append(c instanceof Node ? c : document.createTextNode(String(c)));
  return el;
}
const chColor = (i) => css(`--series-${i + 1}`);
const fin = (v) => v !== null && v !== undefined && Number.isFinite(v);
const median = (a) => {
  const x = a.filter(fin).sort((p, q) => p - q);
  if (!x.length) return null;
  const m = x.length >> 1;
  return x.length % 2 ? x[m] : (x[m - 1] + x[m]) / 2;
};
const fmtRange = (a, b) => (b < 600 ? `${Math.round(a)}–${Math.round(b)} s` : `${fmtTime(a, 999)}–${fmtTime(b, 999)}`);
const signed = (v, d = 2) => {
  if (!fin(v)) return '–';
  const t = Math.abs(v).toFixed(d);
  return (+t === 0 ? '' : v > 0 ? '+' : '−') + t;
};

// --- feedback -----------------------------------------------------------------------
let busyN = 0;
function busy(on) { busyN = Math.max(0, busyN + (on ? 1 : -1)); $('busy').hidden = busyN === 0; }
let toastTimer = null;
function toast(msg, kind = 'error') {
  const t = $('toast');
  t.textContent = msg; t.className = 'toast' + (kind === 'info' ? ' info' : ''); t.hidden = false;
  clearTimeout(toastTimer); toastTimer = setTimeout(() => { t.hidden = true; }, kind === 'info' ? 3500 : 7000);
}
async function api(path, opts) {
  busy(true);
  try {
    const r = await fetch(path, opts);
    if (!r.ok) {
      let msg = r.statusText;
      try { msg = (await r.json()).detail || msg; } catch { /* not json */ }
      throw new Error(msg);
    }
    return await r.json();
  } finally { busy(false); }
}
const debounce = (fn, ms) => { let t; return (...a) => { clearTimeout(t); t = setTimeout(() => fn(...a), ms); }; };

// --- charts -------------------------------------------------------------------------
const group = new ChartGroup();
const common = {
  onZoom: (a, b) => setView(a, b),
  onReset: () => setView(0, dur()),
  onPick: (t) => { S.mapT = clampMapT(t - S.mapWin / 2); $('mapT').value = S.mapT; updateMap(); },
};
const eegChart = group.add(new Chart($('chEeg'), { ...common, lanes: 4, laneScale: 100, markerLabels: true, emptyText: 'memuat EEG…' }));
const bandChart = group.add(new Chart($('chBand'), { ...common, yLog: true, title: 'Daya pita' }));
const heartChart = group.add(new Chart($('chHeart'), {
  ...common, title: 'Interval antar-denyut (ms)', yFmt: (v) => v.toFixed(0), emptyText: 'tidak ada data denyut',
  hoverInfo: (t) => { const s = segAt(t); return s ? `Ruas ${s.i + 1}${s.name ? ' · ' + s.name : ''}` : null; },
}));
const psdChart = new Chart($('chPsd'), {
  interactive: false, yLog: true, title: 'Daya spektral (µV²/Hz)', xFmt: (f) => `${+f.toFixed(1)} Hz`,
  xStep: (span) => ($('chPsd').clientWidth < 520 ? 10 : span > 20 ? 5 : 2), padL: 52, padR: 18,
});
psdChart.ownX = [1, 40];

const dur = () => (S.ov ? S.ov.duration : 1);
function setView(a, b) {
  const d = dur();
  let x0 = Math.max(0, Math.min(a, b)), x1 = Math.min(d, Math.max(a, b));
  if (x1 - x0 < 2) { const c = (x0 + x1) / 2; x0 = Math.max(0, c - 1); x1 = Math.min(d, c + 1); }
  group.setView(x0, x1);
  $('viewInfo').textContent = x0 <= 0.01 && x1 >= d - 0.01 ? `· seluruh sesi (${fmtTime(d, d)})` : `· ${fmtTime(x0, x1 - x0)} – ${fmtTime(x1, x1 - x0)}`;
  loadSignal();
}
const loadSignal = debounce(async () => {
  if (!S.sid) return;
  const req = ++S.sigReq;
  const n = Math.round(($('chEeg').clientWidth || 800) * 1.5);
  try {
    const sig = await api(`/api/signal/${S.sid}?t0=${group.x0}&t1=${group.x1}&n=${n}`);
    if (req !== S.sigReq) return;
    eegChart.setSeries(CH.map((c, i) => (sig.kind === 'env'
      ? { name: c, color: chColor(i), lane: i, t: sig.t, lo: sig.lo[i], hi: sig.hi[i] }
      : { name: c, color: chColor(i), lane: i, t: sig.t, y: sig.y[i] })));
  } catch (e) { toast(`EEG: ${e.message}`); }
}, 120);

// --- sessions -----------------------------------------------------------------------
async function loadSessions(root) {
  let data;
  try { data = await api(`/api/sessions?root=${encodeURIComponent(root || '')}`); } catch (e) { toast(e.message); return; }
  applySessionList(data);
}
function applySessionList(data, preferFirst = false) {
  S.root = data.root;
  S.sessions = data.sessions || [];
  const sel = $('sessionSel');
  sel.replaceChildren(...S.sessions.map((s) => h('option', { value: s.id }, sessionText(s))));
  if (!S.sessions.length) {
    S.sid = null; S.ov = null; S.res = null;
    $('sessionSub').textContent = data.exists === false ? `Folder tidak ditemukan: ${data.root}` : `Belum ada sesi di ${data.root}`;
    showEmpty(data);
    return;
  }
  const saved = store.get('sid');
  const pick = !preferFirst && S.sessions.some((s) => s.id === saved) ? saved : S.sessions[0].id;
  sel.value = pick;
  selectSession(pick);
}
function sessionText(s) {
  const d = fin(s.duration) ? ` · ${fmtTime(s.duration, s.duration)}` : '';
  const date = (s.start || '').replace('T', ' ').slice(0, 16);
  return `${s.name}${date ? ' · ' + date : ''}${d}${s.has_polar ? ' · Polar' : ''}`;
}
function showEmpty(data) {
  $('segCards').replaceChildren(h('div', { class: 'card empty', style: 'grid-column:1/-1' },
    h('p', {}, h('b', {}, 'Belum ada rekaman untuk ditampilkan.')),
    h('p', {}, `Folder: ${data.root}`),
    h('p', {}, 'Rekam sesi dengan dashboard musepolar (python -m musepolar), pilih folder lain lewat “Folder…”, atau unggah ZIP berisi folder sesi.')));
  $('kpis').replaceChildren();
  for (const c of [eegChart, bandChart, heartChart]) c.setSeries([]);
  psdChart.setSeries([]);
  for (const id of ['segTable', 'testTable', 'mapTable']) $(id).replaceChildren();
  $('omnibus').textContent = ''; $('testNote').textContent = ''; $('mapTitle').textContent = '–';
  drawTopo($('mapBig'), {}, {});
}

async function selectSession(sid) {
  S.sid = sid;
  store.set('sid', sid);
  let ov;
  try { ov = await api(`/api/session/${sid}`); } catch (e) { toast(e.message); return; }
  if (S.sid !== sid) return;
  S.ov = ov;
  const saved = store.get(`titik:${ov.folder}`);
  S.set.titik = saved !== null ? saved : (ov.marker_titik || '');
  S.set.ref = 0;
  $('titik').value = S.set.titik;
  S.mapT = 0;
  $('sessionSub').textContent = [ov.name, (ov.start || '').replace('T', ' '), ov.note].filter(Boolean).join(' · ');
  document.title = `${ov.name} · Muse 2 Research View`;
  eegChart.setSeries([]);
  setView(0, ov.duration);
  renderStatic();
  await runAnalysis();
}

function renderStatic() {
  const ov = S.ov;
  const markers = ov.markers.filter((m) => fin(m.t)).map((m) => ({ t: m.t, label: m.label }));
  for (const c of [eegChart, bandChart, heartChart]) c.setOverlays({ markers });
  const series = [];
  const mk = (src, name, color) => (src ? {
    name, color, t: src.t, y: src.ibi.map((v, i) => (src.valid[i] ? v : null)), unit: 'ms', gap: 4,
  } : null);
  const ppg = mk(ov.ppg && ov.ppg.t.length ? ov.ppg : null, 'PPG dahi', chColor(0));
  const pol = mk(ov.polar, 'Polar RR', chColor(1));
  if (ppg) series.push(ppg);
  if (pol) series.push(pol);
  heartChart.setSeries(series);
  syncMapSlider();
}

// --- analysis -----------------------------------------------------------------------
const runAnalysis = debounce(async () => {
  if (!S.sid) return;
  const req = ++S.anaReq;
  const q = new URLSearchParams({ titik: S.set.titik, band: S.set.band, metric: S.set.metric, ref: S.set.ref, art: S.set.art });
  try {
    const res = await api(`/api/analysis/${S.sid}?${q}`);
    if (req !== S.anaReq) return;
    S.res = res;
    S.set.ref = res.ref;
    renderAnalysis();
  } catch (e) { toast(e.message); }
}, 200);

const isBad = (w, c) => (S.res.bad[w] >> c) & 1;
function windowValue(w, c) {
  const W = S.res.windows, p = W.power[S.res.band][c][w];
  if (!fin(p)) return null;
  if (S.res.metric === 'rel') { const t = W.total[c][w]; return fin(t) && t > 0 ? (100 * p) / t : null; }
  return p;
}
const unitTxt = () => (S.res.metric === 'rel' ? '%' : 'µV²');
const valFmt = (v) => (S.res && S.res.metric === 'rel' ? fmtNum(v, 3) : fmtNum(v, 3));
const segAt = (t) => (S.res ? S.res.segments.find((s) => t >= s.t0 && t < s.t1) || null : null);

function renderAnalysis() {
  const res = S.res;
  const segs = res.segments.map((s) => ({ a: s.t0, b: s.t1, i: s.i, ref: s.i === res.ref }));
  for (const c of [eegChart, bandChart, heartChart]) c.setOverlays({ segments: segs });

  $('refSel').replaceChildren(...res.segments.map((s) => h('option', { value: s.i },
    `Ruas ${s.i + 1} · ${fmtRange(s.t0, s.t1)}${s.name ? ' · ' + s.name : ''}`)));
  $('refSel').value = res.ref;
  $('refSel').disabled = res.segments.length < 2;

  bandChart.opt.yLog = res.metric === 'abs';
  bandChart.opt.title = `Daya ${SYM[res.band]} ${res.band} (${unitTxt()}${res.metric === 'abs' ? ', log' : ''})`;
  bandChart.opt.yFmt = (v) => fmtNum(v, 3);
  const nW = S.ov.windows.t_mid.length;
  bandChart.setSeries(CH.map((c, i) => ({
    name: c, color: chColor(i), t: S.ov.windows.t_mid, unit: unitTxt(),
    y: Array.from({ length: nW }, (_, w) => (isBad(w, i) ? null : windowValue(w, i))),
  })));

  renderKpis();
  syncMapSlider();
  updateMap();
  renderSegTable();
  renderTests();
  renderPsd();
}

// --- KPI tiles ----------------------------------------------------------------------
function statusEl(st) {
  const cls = st === 'VALID' ? 'ok' : st === 'WARNING' ? 'warn' : st === 'INVALID' ? 'bad' : 'none';
  const txt = { VALID: 'Baik', WARNING: 'Perlu dicek', INVALID: 'Buruk' }[st] || 'Tidak ada';
  return h('span', { class: `status ${cls}` }, h('i'), txt);
}
function kpi(k, v, d) { return h('div', { class: 'card kpi' }, h('div', { class: 'k' }, k), h('div', { class: 'v' }, v), h('div', { class: 'd' }, d)); }
function renderKpis() {
  const ov = S.ov, res = S.res, q = ov.quality;
  const hp = ov.hrv.ppg, hpo = ov.hrv.polar;
  const clean = res.clean_frac.map((f, i) => `${CH[i]} ${fin(f) ? Math.round(f * 100) : '–'}%`).join(' · ');
  const mk = ov.markers.filter((m) => !String(m.label).startsWith('SYNC'));
  $('kpis').replaceChildren(
    kpi('Durasi', fmtTime(ov.duration, ov.duration), ov.start ? `mulai ${ov.start.replace('T', ' ')}` : ov.label),
    kpi('Mutu EEG', statusEl(q.eeg && q.eeg.status), `jendela bersih: ${clean}`),
    kpi('Denyut dahi (PPG)', hp.ok ? [Math.round(hp.hr), h('small', {}, 'bpm')] : '–',
      hp.ok ? `PRV-RMSSD ${fmtNum(hp.rmssd, 2)} ms · valid ${Math.round((hp.valid_frac || 0) * 100)}%`
        : (q.ppg && q.ppg.status !== '-' ? 'denyut tidak terdeteksi' : 'PPG tidak direkam')),
    kpi('Polar H10', hpo && hpo.ok ? [Math.round(hpo.hr), h('small', {}, 'bpm')] : '–',
      hpo && hpo.ok ? `HRV-RMSSD ${fmtNum(hpo.rmssd, 2)} ms · SDNN ${fmtNum(hpo.sdnn, 2)} ms` : 'tidak direkam'),
    kpi('Sinkronisasi Muse−Polar', fin(ov.sync_offset_ms) ? [signed(ov.sync_offset_ms, 0), h('small', {}, 'ms')] : '–',
      fin(ov.sync_offset_ms) ? 'diterapkan ke data Polar' : (ov.polar ? 'belum ada; Polar memakai jam Mac' : 'tidak diperlukan')),
    kpi('Penanda', String(mk.length), mk.length ? mk.slice(0, 3).map((m) => `${fmtTime(m.t, 100)} ${m.label}`).join(' · ') : 'tidak ada'),
  );
}

// --- head maps ----------------------------------------------------------------------
function syncMapSlider() {
  const max = Math.max(0, Math.floor(dur() - S.mapWin));
  const sl = $('mapT');
  sl.max = max;
  S.mapT = clampMapT(S.mapT);
  sl.value = S.mapT;
}
const clampMapT = (t) => Math.max(0, Math.min(Math.floor(dur() - S.mapWin), Math.round(t)));

function currentWindowValues() {
  const T0 = S.mapT, T1 = S.mapT + S.mapWin, W = S.ov.windows;
  const out = {}, n = [];
  CH.forEach((c, i) => {
    const vals = [];
    W.t_mid.forEach((t, w) => { if (t >= T0 && t < T1 && !isBad(w, i)) vals.push(windowValue(w, i)); });
    out[c] = median(vals); n.push(vals.length);
  });
  return { values: out, n };
}
const toLog = (v) => (fin(v) && v > 0 ? Math.log10(v) : null);
function zOf(v, c) {
  const i = CH.indexOf(c), m = S.res.ref_mean[i], sd = S.res.ref_sd[i];
  const tv = S.res.metric === 'abs' ? toLog(v) : v;
  return fin(tv) && fin(m) && fin(sd) ? (tv - m) / sd : null;
}

// Each head map uses its own colour range (as the original app), so every map shows
// its full set of layers; the numbers at the electrodes carry the actual values.
function mapScale(drawn) {
  const all = Object.values(drawn).filter(fin);
  if (!all.length) return { vmin: 0, vmax: 1 };
  let lo = Math.min(...all), hi = Math.max(...all);
  if (hi - lo < 1e-6) { const pad = S.mapMode === 'change' ? 0.25 : 0.5; lo -= pad; hi += pad; }
  return { vmin: lo, vmax: hi };
}
function mapInput(valuesByCh) {
  // values as drawn: z (change), log10 power (absolute) or percent (relative)
  const out = {};
  for (const c of CH) {
    const v = valuesByCh[c];
    out[c] = S.mapMode === 'change' ? zOf(v, c) : (S.res.metric === 'abs' ? toLog(v) : (fin(v) ? v : null));
  }
  return out;
}
const labelFmt = () => (S.mapMode === 'change' ? (v) => signed(v, 1) : S.res.metric === 'abs' ? (v) => fmtNum(10 ** v, 3) : (v) => fmtNum(v, 3));

function updateMap() {
  if (!S.res) return;
  const res = S.res;
  const { values, n } = currentWindowValues();
  const drawn = mapInput(values);
  const segDrawn = res.segments.map((s) => (S.mapMode === 'change'
    ? Object.fromEntries(CH.map((c, i) => [c, s.z[i]]))
    : mapInput(Object.fromEntries(CH.map((c, i) => [c, s.values[i]])))));
  const sc = mapScale(drawn);
  const fmt = labelFmt();
  drawTopo($('mapBig'), drawn, { ...sc, showValues: true, fmt });
  const T1 = Math.min(dur(), S.mapT + S.mapWin);
  $('mapTLabel').textContent = `Mulai jendela: ${fmtTime(S.mapT, 100)}`;
  const seg = segAt(S.mapT + S.mapWin / 2);
  $('mapTitle').textContent = `${fmtRange(S.mapT, T1)} · ${SYM[res.band]} ${res.band}`
    + (seg ? ` · Ruas ${seg.i + 1}` : '') + ` · ${Math.min(n[1], n[2])} jendela bersih AF`;
  for (const c of [eegChart, bandChart, heartChart]) c.setOverlays({ window: { a: S.mapT, b: T1 } });

  const cb = $('colorbar');
  cb.querySelector('.bar').style.background = layeredCss();
  const ticks = cb.querySelectorAll('.ticks span');
  [sc.vmin, (sc.vmin + sc.vmax) / 2, sc.vmax].forEach((v, i) => { ticks[i].textContent = fmt(v); });
  cb.querySelector('.cap').textContent = S.mapMode === 'change'
    ? 'z terhadap ruas acuan · skala per peta: biru = terendah, merah = tertinggi di peta ini'
    : `${res.band} (${unitTxt()})${res.metric === 'abs' ? ' · lapisan pada skala log' : ''} · skala per peta: biru = terendah, merah = tertinggi`;

  const rows = [h('tr', {}, h('th', {}, 'Kanal'), h('th', { style: 'text-align:right' }, unitTxt()), h('th', { style: 'text-align:right' }, 'z vs acuan'), h('th', { style: 'text-align:right' }, 'jendela'))];
  CH.forEach((c, i) => rows.push(h('tr', {},
    h('th', {}, h('i', { class: 'sw', style: `background:${chColor(i)}` }), c),
    h('td', {}, valFmt(values[c])), h('td', {}, signed(zOf(values[c], c), 2)), h('td', {}, String(n[i])))));
  $('mapTable').replaceChildren(...rows);

  renderSegCards(segDrawn, sc, fmt);
}

// --- segment cards ------------------------------------------------------------------
function heartOf(s) {
  if (s.polar && s.polar.ok) return { src: 'Polar', ...s.polar };
  if (s.ppg && s.ppg.ok) return { src: 'PPG', ...s.ppg };
  return null;
}
function renderSegCards(segDrawn, sc, fmt) {
  const res = S.res;
  const cards = res.segments.map((s, k) => {
    const v = [s.values[1], s.values[2]].filter(fin);
    const af = v.length ? v.reduce((a, b) => a + b, 0) / v.length : null;
    const zz = [s.z[1], s.z[2]].filter(fin);
    const zaf = zz.length ? zz.reduce((a, b) => a + b, 0) / zz.length : null;
    const hr = heartOf(s);
    const cv = h('canvas', { width: 84, height: 84, 'aria-label': `Peta ruas ${s.i + 1}` });
    const isRef = s.i === res.ref;
    const card = h('div', { class: `card seg-card${isRef ? ' ref' : ''}`, title: 'Klik untuk memperbesar ruas ini di grafik' },
      h('div', { class: 't' }, `Ruas ${s.i + 1} · ${fmtRange(s.t0, s.t1)}`),
      s.name ? h('div', { class: 'nm', title: s.name }, s.name) : null,
      h('div', {}, h('span', { class: `label-chip ${s.code}` }, h('i'), s.label)),
      h('div', { class: 'facts' },
        `${SYM[res.band]} AF `, h('b', {}, `${valFmt(af)} ${unitTxt()}`), isRef ? '' : ` (z ${signed(zaf, 1)})`, h('br'),
        hr ? ['Denyut ', h('b', {}, Math.round(hr.hr)), ` (${hr.src})`, fin(hr.rmssd) ? [' · RMSSD ', h('b', {}, Math.round(hr.rmssd)), ' ms'] : ''] : 'Denyut –',
        h('br'), `${s.n_af}/${s.n_win} jendela bersih AF`,
        isRef ? '' : [' · ', h('button', { class: 'btn sm', style: 'min-height:22px;padding:0 7px;font-size:11px', onclick: (e) => { e.stopPropagation(); setRef(s.i); } }, 'jadikan acuan')]),
      cv,
      h('div', { class: 'arti' }, s.arti));
    card.addEventListener('click', () => {
      setView(s.t0, s.t1);
      S.mapT = clampMapT(s.t0); $('mapT').value = S.mapT; updateMap();
    });
    requestAnimationFrame(() => drawTopo(cv, segDrawn[k], { ...mapScale(segDrawn[k]), labels: false, fmt }));
    return card;
  });
  $('segCards').replaceChildren(...cards);
}
function setRef(i) { S.set.ref = i; $('refSel').value = i; runAnalysis(); }

// --- tables -------------------------------------------------------------------------
function td(v, cls) { return h('td', { class: cls || (v === '–' ? 'na' : null) }, v); }
function renderSegTable() {
  const res = S.res;
  $('segUnit').textContent = `nilai kanal = median daya ${SYM[res.band]} ${res.band} (${unitTxt()}) pada jendela bersih`;
  const head = h('tr', {}, ...['Ruas', 'Nama', 'Jendela bersih AF', 'TP9', 'AF7', 'AF8', 'TP10', 'Asimetri AF', 'Denyut PPG', 'PRV-RMSSD', 'Denyut Polar', 'HRV-RMSSD', 'Kondisi']
    .map((t, i) => h('th', { class: i === 1 || i === 12 ? 'l' : null }, t)));
  const rows = res.segments.map((s) => h('tr', { class: s.i === res.ref ? 'ref' : null },
    td(`${s.i + 1} · ${fmtRange(s.t0, s.t1)}`),
    td(s.name || '–', 'l'),
    td(`${s.n_af}/${s.n_win}`),
    ...s.values.map((v) => td(fin(v) ? valFmt(v) : '–')),
    td(fin(s.asym) ? signed(s.asym, 3) : '–'),
    td(s.ppg && s.ppg.ok ? Math.round(s.ppg.hr) : '–'),
    td(s.ppg && fin(s.ppg.rmssd) ? Math.round(s.ppg.rmssd) : '–'),
    td(s.polar && s.polar.ok ? Math.round(s.polar.hr) : '–'),
    td(s.polar && fin(s.polar.rmssd) ? Math.round(s.polar.rmssd) : '–'),
    h('td', { class: 'l' }, h('span', { class: `label-chip ${s.code}` }, h('i'), s.label))));
  $('segTable').replaceChildren(h('thead', {}, head), h('tbody', {}, ...rows));
}

function renderMeasureSeg() {
  const seg = $('measureSeg');
  seg.replaceChildren(...['Semua', ...MEASURES].map((m) => h('button', { 'data-v': m, class: m === S.measure ? 'on' : null }, MEASURE_LABEL[m] || m)));
}
function renderTests() {
  const res = S.res, t = res.tests;
  renderMeasureSeg();
  if (res.segments.length < 2) {
    $('testNote').textContent = 'Isi titik observasi (atau klik “Pakai penanda”) untuk membagi sesi menjadi beberapa ruas dan membandingkannya.';
    $('testTable').replaceChildren(); $('omnibus').textContent = '';
    return;
  }
  $('testNote').textContent = `Mann–Whitney dua sisi pada jendela ${S.ov.windows.win_s} s yang tidak tumpang tindih (min. 5 per ruas); `
    + `p dikoreksi Holm per ukuran; δ Cliff > 0 berarti ruas kedua lebih tinggi. Pita ${SYM[res.band]} ${res.band}, ${res.metric === 'rel' ? 'daya relatif' : 'daya absolut'}.`;
  const rows = t.pairs.filter((r) => S.measure === 'Semua' || r.measure === S.measure);
  const all = S.measure === 'Semua';
  const head = h('tr', {}, ...[all ? 'Ukuran' : null, 'Perbandingan', 'n', 'Median', 'Perubahan', 'p', 'p Holm', 'δ Cliff', 'Hasil'].filter(Boolean)
    .map((x, i) => h('th', { class: i === 0 || (all && i === 1) ? 'l' : null }, x)));
  const body = rows.map((r) => {
    const asym = r.measure === 'Asimetri AF';
    const change = fin(r.med_a) && fin(r.med_b)
      ? (asym ? signed(r.med_b - r.med_a, 3) : (r.med_a !== 0 ? `${signed(((r.med_b - r.med_a) / Math.abs(r.med_a)) * 100, 0)}%` : '–')) : '–';
    const result = r.p === null ? h('span', { class: 'badge' }, 'data kurang')
      : r.sig ? h('span', { class: 'badge sig' }, 'berbeda') : h('span', { class: 'badge' }, 'tidak berbeda');
    return h('tr', {},
      all ? td(MEASURE_LABEL[r.measure] || r.measure, 'l') : null,
      td(r.pair, all ? 'l' : null),
      td(`${r.n_a} / ${r.n_b}`),
      td(`${asym ? signed(r.med_a, 3) : valFmt(r.med_a)} → ${asym ? signed(r.med_b, 3) : valFmt(r.med_b)}`),
      td(change),
      td(fin(r.p) ? fmtP(r.p) : '–'),
      td(fin(r.p_holm) ? fmtP(r.p_holm) : '–'),
      td(fin(r.delta) ? `${signed(r.delta, 2)} (${r.effect})` : '–'),
      h('td', {}, result));
  });
  $('testTable').replaceChildren(h('thead', {}, head), h('tbody', {}, ...body));
  const om = t.omnibus.filter((o) => all || o.measure === S.measure);
  $('omnibus').textContent = om.length
    ? 'Kruskal–Wallis (semua ruas): ' + om.map((o) => `${MEASURE_LABEL[o.measure] || o.measure} ${pStr(o.p)}`).join(' · ')
    : '';
}
const fmtP = (p) => (p < 0.001 ? '< 0,001' : p.toFixed(3).replace('.', ','));
const pStr = (p) => (p < 0.001 ? 'p < 0,001' : `p = ${fmtP(p)}`);

// --- spectrum -----------------------------------------------------------------------
function renderPsd() {
  const res = S.res;
  const idx = S.psdCh === 'AF' ? [1, 2] : S.psdCh === 'TP' ? [0, 3] : [CH.indexOf(S.psdCh)];
  const f = res.freqs;
  const series = res.segments.slice(0, 8).map((s, k) => ({
    name: `Ruas ${s.i + 1}`, color: css(`--series-${k + 1}`), t: f, unit: 'µV²/Hz',
    y: f.map((_, j) => { const v = idx.map((c) => s.psd[c][j]).filter(fin); return v.length ? v.reduce((a, b) => a + b, 0) / v.length : null; }),
  }));
  psdChart.opt.yFmt = (v) => fmtNum(v, 2);
  const bands = S.ov.bands;
  psdChart.setOverlays({
    segments: Object.values(bands).map(([a, b], i) => ({ a, b, i })),
    window: { a: bands[res.band][0], b: bands[res.band][1] },
  });
  psdChart.opt.title = `Daya spektral (µV²/Hz) · pita ${SYM[res.band]} diarsir`;
  psdChart.setSeries(series);
}

// --- events -------------------------------------------------------------------------
function segControl(id, onPick) {
  $(id).addEventListener('click', (e) => {
    const b = e.target.closest('button[data-v]');
    if (!b) return;
    $(id).querySelectorAll('button').forEach((x) => x.classList.toggle('on', x === b));
    onPick(b.dataset.v);
  });
}
segControl('bandSeg', (v) => { S.set.band = v; runAnalysis(); });
segControl('metricSeg', (v) => { S.set.metric = v; runAnalysis(); });
segControl('mapModeSeg', (v) => { S.mapMode = v; updateMap(); });
segControl('measureSeg', (v) => { S.measure = v; renderTests(); });

function applyTitik() {
  const v = $('titik').value.trim();
  if (v === S.set.titik) return;
  S.set.titik = v;
  if (S.ov) store.set(`titik:${S.ov.folder}`, v);
  runAnalysis();
}
$('titik').addEventListener('change', applyTitik);
$('titik').addEventListener('keydown', (e) => { if (e.key === 'Enter') applyTitik(); });
$('useMarkers').addEventListener('click', () => {
  if (!S.ov) return;
  if (!S.ov.marker_titik) { toast('Sesi ini tidak punya penanda (selain SYNC).', 'info'); return; }
  $('titik').value = S.ov.marker_titik; applyTitik();
});
$('refSel').addEventListener('change', (e) => setRef(+e.target.value));
$('art').addEventListener('change', (e) => {
  const v = Math.max(20, Math.min(1000, +e.target.value || 100));
  e.target.value = v; S.set.art = v; runAnalysis();
});
$('eegScale').addEventListener('change', (e) => { eegChart.opt.laneScale = +e.target.value; eegChart.draw(); });
$('mapT').addEventListener('input', (e) => { S.mapT = +e.target.value; updateMap(); });
$('mapWin').addEventListener('change', (e) => { S.mapWin = +e.target.value; syncMapSlider(); updateMap(); });
$('psdCh').addEventListener('change', (e) => { S.psdCh = e.target.value; renderPsd(); });
$('zoomAll').addEventListener('click', () => setView(0, dur()));
$('zoomIn').addEventListener('click', () => { const c = (group.x0 + group.x1) / 2, s = (group.x1 - group.x0) / 4; setView(c - s, c + s); });
$('zoomOut').addEventListener('click', () => { const c = (group.x0 + group.x1) / 2, s = group.x1 - group.x0; setView(c - s, c + s); });
$('sessionSel').addEventListener('change', (e) => selectSession(e.target.value));

$('folderBtn').addEventListener('click', () => { $('rootInput').value = S.root; $('folderDlg').showModal(); });
$('folderDlg').addEventListener('close', () => {
  const rv = $('folderDlg').returnValue;
  if (rv === 'ok') loadSessions($('rootInput').value.trim());
  else if (rv === 'default') loadSessions('');
});
$('zipInput').addEventListener('change', async (e) => {
  const f = e.target.files[0];
  e.target.value = '';
  if (!f) return;
  const fd = new FormData();
  fd.append('file', f);
  try {
    const data = await api('/api/upload', { method: 'POST', body: fd });
    toast(`${data.sessions.length} sesi dari ${f.name} dimuat.`, 'info');
    applySessionList(data, true);
  } catch (err) { toast(err.message); }
});
document.querySelectorAll('[data-export]').forEach((b) => b.addEventListener('click', () => {
  if (!S.sid) return;
  const q = new URLSearchParams({ titik: S.set.titik, band: S.set.band, metric: S.set.metric, ref: S.set.ref, art: S.set.art });
  window.location.href = `/api/${b.dataset.export}/${S.sid}?${q}`;
}));
$('printBtn').addEventListener('click', () => window.print());

function redrawAll() {
  [eegChart, bandChart, heartChart, psdChart].forEach((c) => c.draw());
  if (S.res) { renderAnalysis(); loadSignal(); }
}
const theme = store.get('theme');
if (theme) document.documentElement.dataset.theme = theme;
$('themeBtn').addEventListener('click', () => {
  const dark = document.documentElement.dataset.theme
    ? document.documentElement.dataset.theme === 'dark' : matchMedia('(prefers-color-scheme: dark)').matches;
  document.documentElement.dataset.theme = dark ? 'light' : 'dark';
  store.set('theme', document.documentElement.dataset.theme);
  redrawAll();
});
matchMedia('(prefers-color-scheme: dark)').addEventListener('change', redrawAll);
window.addEventListener('resize', debounce(() => { if (S.res) updateMap(); loadSignal(); }, 200));

loadSessions('');
