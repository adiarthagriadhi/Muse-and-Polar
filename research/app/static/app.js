import { Chart, ChartGroup, css, drawTopo, fmtNum, fmtTime, layeredCss } from './charts.js';

const $ = (id) => document.getElementById(id);
let CH = ['TP9', 'AF7', 'AF8', 'TP10']; // replaced by the session's channels (Muse 4, EDF 16, ...)
const SYM = { delta: 'δ', theta: 'θ', alpha: 'α', beta: 'β' };
// heart data label: Polar (musepolar session or joined Polar Sensor Logger files) or ECG from the file itself
const heartShort = () => (S.ov && (S.ov.kind === 'musepolar' || S.ov.polar_info) ? 'Polar' : 'EKG');
function polarNote(ov) {
  const p = ov.polar_info; if (!p) return '';
  const src = p.source === 'ECG' ? 'EKG .txt' : 'RR .txt';
  if (p.aligned !== 'clock') return ` · ${src}, disejajarkan di awal (EEG tanpa jam)`;
  const d = p.start_diff_s + (ov.pshift || 0);
  return ` · ${src}, mulai ${Math.abs(d).toFixed(1)} s ${d < 0 ? 'sebelum' : 'sesudah'} EEG`;
}
const KIND_LABEL = { edf: 'EDF', csv: 'CSV', lsl: 'CSV (format lama)' };
const mLabel = (m) => (S.res && S.res.measure_labels && S.res.measure_labels[m]) || m;
const store = {
  get(k) { try { return localStorage.getItem(k); } catch { return null; } },
  set(k, v) { try { localStorage.setItem(k, v); } catch { /* private mode */ } },
};

const S = {
  root: '', sessions: [], sid: null, ov: null, res: null,
  set: { titik: '', band: 'alpha', metric: 'abs', ref: 0, art: 100, chans: 'all', heart: 'all', pshift: 0 },
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
// Muse: one colour per channel. Many channels: colour by scalp region (at most 5 hues).
const regionOf = (c) => { const r = S.ov && S.ov.regions; if (!r) return null; return Object.keys(r).find((k) => r[k].includes(c)) || null; };
const chColor = (i) => {
  if (CH.length <= 4) return css(`--series-${i + 1}`);
  const keys = S.ov ? Object.keys(S.ov.regions) : [];
  const k = keys.indexOf(regionOf(CH[i]));
  return k >= 0 && k < 5 ? css(`--series-${k + 1}`) : css('--text-secondary');
};
const pairIdx = () => (S.res && S.res.pair ? S.res.pair.map((c) => CH.indexOf(c)) : CH.map((_, i) => i));
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
// Browser-only build (research/web): the engine computes everything locally, no server.
const WEB = typeof window !== 'undefined' && !!window.ENGINE;
const ARTIFACT = WEB && !!window.RV_ARTIFACT; // hosted page: no print dialog, no file downloads
async function api(path, opts) {
  busy(true);
  try {
    if (WEB) return await window.ENGINE.handle(path);
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
    const sig = await api(`/api/signal/${S.sid}?t0=${group.x0}&t1=${group.x1}&n=${n}&chans=${S.set.chans}`);
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
  if (WEB && !data.sessions.length) { loadDemo(); return; } // open in a working state with the example recordings
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
  const kind = s.kind !== 'musepolar' ? ` · ${KIND_LABEL[s.kind] || s.kind.toUpperCase()} ${s.n_channels} kanal` : '';
  return `${s.name}${date ? ' · ' + date : ''}${d}${kind}${s.has_polar ? (s.kind !== 'musepolar' ? ' · EKG' : ' · Polar') : ''}`;
}
function showEmpty(data) {
  $('segCards').replaceChildren(WEB
    ? h('div', { class: 'card empty', style: 'grid-column:1/-1' },
      h('p', {}, h('b', {}, 'Buka rekaman untuk mulai.')),
      h('p', {}, 'Pilih file EDF/BDF, CSV (Mind Monitor, muselsl, OpenBCI, atau CSV dengan kanal 10-20) atau ZIP lewat “Buka file”, atau folder rekaman lewat “Folder…”. '
        + 'Semua perhitungan berjalan di browser ini; data tidak dikirim ke mana pun.'),
      h('p', {}, h('button', { class: 'btn primary', onclick: loadDemo }, 'Coba data contoh')))
    : h('div', { class: 'card empty', style: 'grid-column:1/-1' },
      h('p', {}, h('b', {}, 'Belum ada rekaman untuk ditampilkan.')),
      h('p', {}, `Folder: ${data.root}`),
      h('p', {}, 'Rekam sesi dengan dashboard musepolar (python -m musepolar), pilih folder lain lewat “Folder…” (folder sesi musepolar atau file EDF), atau unggah ZIP / EDF.')));
  $('kpis').replaceChildren();
  eegChart.opt.emptyText = 'belum ada rekaman';
  for (const c of [eegChart, bandChart, heartChart]) c.setSeries([]);
  psdChart.setSeries([]);
  for (const id of ['segTable', 'testTable', 'mapTable']) $(id).replaceChildren();
  $('omnibus').textContent = ''; $('testNote').textContent = ''; $('mapTitle').textContent = '–';
  drawTopo($('mapBig'), {}, {});
}

// keep=true: same recording, only the channel mode / heart sources changed (keeps titik, zoom, map time)
async function selectSession(sid, keep = false) {
  S.sid = sid;
  store.set('sid', sid);
  let ov;
  if (!keep) { S.set.pshift = 0; $('pshift').value = 0; }
  const q = `chans=${S.set.chans}&heart=${S.set.heart}&pshift=${S.set.pshift}`;
  try { ov = await api(`/api/session/${sid}?${q}`); } catch (e) { toast(e.message); return; }
  if (S.sid !== sid) return;
  S.ov = ov;
  renderSourceControls();
  CH = ov.channels;
  S.measure = null; // first measure (frontal pair) once the analysis arrives
  S.psdCh = 'PAIR';
  eegChart.opt.lanes = CH.length;
  eegChart.opt.emptyText = 'memuat EEG…';
  $('chEeg').style.setProperty('--h', `${CH.length <= 4 ? 260 : Math.max(260, 22 * CH.length + 30)}px`);
  if (!keep) {
    const saved = store.get(`titik:${ov.folder}`);
    S.set.titik = saved !== null ? saved : (ov.marker_titik || '');
    S.set.ref = 0;
    $('titik').value = S.set.titik;
    S.mapT = 0;
  }
  $('sessionSub').textContent = [ov.name, (ov.start || '').replace('T', ' '), ov.note].filter(Boolean).join(' · ');
  document.title = `${ov.name} · Muse 2 Research View`;
  eegChart.setSeries([]);
  if (keep) { setView(group.x0, group.x1); } else setView(0, ov.duration);
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
  const ppg = mk(ov.ppg && ov.ppg.t.length ? ov.ppg : null, ov.kind !== 'musepolar' ? 'PPG' : 'PPG dahi', css('--series-1'));
  const pol = mk(ov.polar, ov.heart_name, css('--series-2'));
  if (ppg) series.push(ppg);
  if (pol) series.push(pol);
  heartChart.setSeries(series);
  syncMapSlider();
}

// --- channel mode & heart sources -------------------------------------------------------
function renderSourceControls() {
  const o = S.ov.options;
  const b16 = $('chansSeg').querySelector('[data-v=all]'), b4 = $('chansSeg').querySelector('[data-v=muse4]');
  b16.textContent = `Semua (${o.n_all} kanal)`;
  b16.disabled = o.n_all <= 4;
  b4.disabled = !o.muse4;
  b16.title = o.n_all <= 4 ? 'Rekaman ini hanya punya 4 kanal' : `Analisis semua ${o.n_all} kanal`;
  const desc = (m, c) => (m === c ? m : c.includes('+') ? `${m} = rata-rata ${c.replace('+', ' & ')}` : `${m} = ${c}`);
  const refTxt = o.muse_ref ? `dirujuk ulang ke ${o.muse_ref} seperti Muse` : 'referensi asli file (tidak ada kanal Fpz)';
  b4.title = o.muse4 ? `Meniru Muse 2: ${Object.entries(o.muse4).map(([m, c]) => desc(m, c)).join('; ')}; ${refTxt}`
    : 'Tidak ada kanal di sekitar posisi sensor Muse (AF7, AF8, TP9, TP10)';
  const eff = o.n_all <= 4 ? 'muse4' : S.set.chans;
  $('chansSeg').querySelectorAll('button').forEach((x) => x.classList.toggle('on', x.dataset.v === eff));
  const hs = $('heartSel');
  hs.querySelector('[value=ppg]').disabled = !o.ppg;
  hs.querySelector('[value=ecg]').disabled = !o.ecg;
  const hn = heartShort();
  hs.querySelector('[value=all]').textContent = `PPG + ${hn}`;
  hs.querySelector('[value=ecg]').textContent = `Hanya ${hn}`;
  hs.value = S.set.heart;
  $('pshiftField').hidden = !S.ov.polar_info;
  $('chansInfo').textContent = o.muse4 && eff === 'muse4' && o.n_all > 4
    ? `${Object.entries(o.muse4).map(([m, c]) => `${m}=${c}`).join(' · ')} · ref ${o.muse_ref || 'asli'}` : '';
}
$('chansSeg').addEventListener('click', (e) => {
  const b = e.target.closest('button[data-v]');
  if (!b || b.disabled || !S.sid || b.dataset.v === S.set.chans) return;
  S.set.chans = b.dataset.v; store.set('chans', S.set.chans);
  selectSession(S.sid, true);
});
$('pshift').addEventListener('change', (e) => {
  const v = Math.max(-600, Math.min(600, +e.target.value || 0));
  e.target.value = v; S.set.pshift = v;
  if (S.sid) selectSession(S.sid, true);
});
$('heartSel').addEventListener('change', (e) => {
  S.set.heart = e.target.value; store.set('heart', S.set.heart);
  if (S.sid) selectSession(S.sid, true);
});
S.set.chans = store.get('chans') === 'muse4' ? 'muse4' : 'all';
S.set.heart = ['ppg', 'ecg', 'none'].includes(store.get('heart')) ? store.get('heart') : 'all';

// --- analysis -----------------------------------------------------------------------
const runAnalysis = debounce(async () => {
  if (!S.sid) return;
  const req = ++S.anaReq;
  const q = new URLSearchParams({ titik: S.set.titik, band: S.set.band, metric: S.set.metric, ref: S.set.ref, art: S.set.art, chans: S.set.chans, heart: S.set.heart, pshift: S.set.pshift });
  try {
    const res = await api(`/api/analysis/${S.sid}?${q}`);
    if (req !== S.anaReq) return;
    S.res = res;
    S.set.ref = res.ref;
    renderAnalysis();
  } catch (e) { toast(e.message); }
}, 200);

const isBad = (w, c) => S.res.bad[w].charCodeAt(c) === 49; // '1'
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
  // Muse: one line per channel; many channels: mean of the clean channels in each scalp region
  const groups = CH.length <= 4 ? CH.map((c, i) => [c, [i]])
    : Object.entries(S.ov.regions).slice(0, 5).map(([r, cs]) => [r, cs.map((c) => CH.indexOf(c))]);
  bandChart.setSeries(groups.map(([name, idx], k) => ({
    name, color: css(`--series-${k + 1}`), t: S.ov.windows.t_mid, unit: unitTxt(),
    y: Array.from({ length: nW }, (_, w) => {
      const v = idx.filter((i) => !isBad(w, i)).map((i) => windowValue(w, i)).filter(fin);
      return v.length ? v.reduce((a, b) => a + b, 0) / v.length : null;
    }),
  })));
  if (CH.length > 4) bandChart.opt.title += ' · rata-rata per area';

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
  let clean = res.clean_frac.map((f, i) => `${CH[i]} ${fin(f) ? Math.round(f * 100) : '–'}%`).join(' · ');
  if (CH.length > 4) {
    const fr = res.clean_frac.map((f) => (fin(f) ? f : 0));
    const worst = fr.indexOf(Math.min(...fr));
    clean = `rata-rata ${Math.round((fr.reduce((a, b) => a + b, 0) / fr.length) * 100)}% · terendah ${CH[worst]} ${Math.round(fr[worst] * 100)}%`;
  }
  const mk = ov.markers.filter((m) => !String(m.label).startsWith('SYNC'));
  $('kpis').replaceChildren(
    kpi('Durasi', fmtTime(ov.duration, ov.duration), ov.start ? `mulai ${ov.start.replace('T', ' ')}` : ov.label),
    kpi('Mutu EEG', statusEl(q.eeg && q.eeg.status), `jendela bersih: ${clean}`),
    kpi('Denyut dahi (PPG)', hp.ok ? [Math.round(hp.hr), h('small', {}, 'bpm')] : '–',
      hp.ok ? `PRV-RMSSD ${fmtNum(hp.rmssd, 2)} ms · valid ${Math.round((hp.valid_frac || 0) * 100)}%`
        : (['ecg', 'none'].includes(ov.heart) && ov.options.ppg ? 'tidak dipakai (pilihan Data jantung)'
          : q.ppg && q.ppg.status !== '-' ? 'denyut tidak terdeteksi' : 'PPG tidak direkam')),
    kpi(heartShort() === 'Polar' ? 'Polar H10' : 'Denyut EKG', hpo && hpo.ok ? [Math.round(hpo.hr), h('small', {}, 'bpm')] : '–',
      hpo && hpo.ok ? `HRV-RMSSD ${fmtNum(hpo.rmssd, 2)} ms · SDNN ${fmtNum(hpo.sdnn, 2)} ms${polarNote(ov)}`
        : (['ppg', 'none'].includes(ov.heart) && ov.options.ecg ? 'tidak dipakai (pilihan Data jantung)' : 'tidak direkam')),
    ov.kind !== 'musepolar'
      ? kpi('Kanal EEG', [String(CH.length), h('small', {}, `dari ${ov.options.n_all} @ ${fmtNum(ov.fs, 3)} Hz`)],
        ov.chans === 'muse4' && ov.options.n_all > 4
          ? `disesuaikan Muse · ${ov.options.muse_ref ? 'ref Fpz' : 'ref asli file'}` : `${KIND_LABEL[ov.kind] || ov.kind} · pasangan frontal ${ov.pair_label}`)
      : kpi('Sinkronisasi Muse−Polar', fin(ov.sync_offset_ms) ? [signed(ov.sync_offset_ms, 0), h('small', {}, 'ms')] : '–',
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
  drawTopo($('mapBig'), drawn, { ...sc, showValues: true, fmt, pos: S.ov.positions });
  const T1 = Math.min(dur(), S.mapT + S.mapWin);
  $('mapTLabel').textContent = `Mulai jendela: ${fmtTime(S.mapT, 100)}`;
  const seg = segAt(S.mapT + S.mapWin / 2);
  $('mapTitle').textContent = `${fmtRange(S.mapT, T1)} · ${SYM[res.band]} ${res.band}`
    + (seg ? ` · Ruas ${seg.i + 1}` : '') + ` · ${Math.min(...pairIdx().map((i) => n[i]))} jendela bersih ${res.pair_label}`;
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
    h('th', {}, CH.length <= 4 ? h('i', { class: 'sw', style: `background:${chColor(i)}` }) : null, c),
    h('td', {}, valFmt(values[c])), h('td', {}, signed(zOf(values[c], c), 2)), h('td', {}, String(n[i])))));
  $('mapTable').replaceChildren(...rows);

  renderSegCards(segDrawn, sc, fmt);
}

// --- segment cards ------------------------------------------------------------------
function heartOf(s) {
  if (s.polar && s.polar.ok) return { src: heartShort(), ...s.polar };
  if (s.ppg && s.ppg.ok) return { src: 'PPG', ...s.ppg };
  return null;
}
function renderSegCards(segDrawn, sc, fmt) {
  const res = S.res;
  const cards = res.segments.map((s, k) => {
    const v = pairIdx().map((i) => s.values[i]).filter(fin);
    const af = v.length ? v.reduce((a, b) => a + b, 0) / v.length : null;
    const zz = pairIdx().map((i) => s.z[i]).filter(fin);
    const zaf = zz.length ? zz.reduce((a, b) => a + b, 0) / zz.length : null;
    const hr = heartOf(s);
    const cv = h('canvas', { width: 84, height: 84, 'aria-label': `Peta ruas ${s.i + 1}` });
    const isRef = s.i === res.ref;
    const card = h('div', { class: `card seg-card${isRef ? ' ref' : ''}`, title: 'Klik untuk memperbesar ruas ini di grafik' },
      h('div', { class: 't' }, `Ruas ${s.i + 1} · ${fmtRange(s.t0, s.t1)}`),
      s.name ? h('div', { class: 'nm', title: s.name }, s.name) : null,
      isRef ? h('div', {}, h('span', { class: 'label-chip REFERENCE' }, h('i'), 'Acuan')) : null,
      h('div', { class: 'facts' },
        `${SYM[res.band]} ${res.pair_label} `, h('b', {}, `${valFmt(af)} ${unitTxt()}`), isRef ? '' : ` (z ${signed(zaf, 1)})`, h('br'),
        hr ? ['Denyut ', h('b', {}, Math.round(hr.hr)), ` (${hr.src})`, fin(hr.rmssd) ? [' · RMSSD ', h('b', {}, Math.round(hr.rmssd)), ' ms'] : ''] : 'Denyut –',
        h('br'), `${s.n_pair}/${s.n_win} jendela bersih ${res.pair_label}`,
        isRef ? '' : [' · ', h('button', { class: 'btn sm', style: 'min-height:22px;padding:0 7px;font-size:11px', onclick: (e) => { e.stopPropagation(); setRef(s.i); } }, 'jadikan acuan')]),
      cv);
    card.addEventListener('click', () => {
      setView(s.t0, s.t1);
      S.mapT = clampMapT(s.t0); $('mapT').value = S.mapT; updateMap();
    });
    requestAnimationFrame(() => drawTopo(cv, segDrawn[k], { ...mapScale(segDrawn[k]), labels: false, fmt, pos: S.ov.positions }));
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
  const hn = heartShort();
  const cols = ['Ruas', 'Nama', `Jendela bersih ${res.pair_label}`, ...CH, ...(res.pair ? [`Asimetri ${res.pair_label}`] : []),
    'Denyut PPG', 'PRV-RMSSD', `Denyut ${hn}`, 'HRV-RMSSD', 'Acuan'];
  const head = h('tr', {}, ...cols.map((t, i) => h('th', { class: i === 1 || i === cols.length - 1 ? 'l' : null }, t)));
  const rows = res.segments.map((s) => h('tr', { class: s.i === res.ref ? 'ref' : null },
    td(`${s.i + 1} · ${fmtRange(s.t0, s.t1)}`),
    td(s.name || '–', 'l'),
    td(`${s.n_pair}/${s.n_win}`),
    ...s.values.map((v) => td(fin(v) ? valFmt(v) : '–')),
    res.pair ? td(fin(s.asym) ? signed(s.asym, 3) : '–') : null,
    td(s.ppg && s.ppg.ok ? Math.round(s.ppg.hr) : '–'),
    td(s.ppg && fin(s.ppg.rmssd) ? Math.round(s.ppg.rmssd) : '–'),
    td(s.polar && s.polar.ok ? Math.round(s.polar.hr) : '–'),
    td(s.polar && fin(s.polar.rmssd) ? Math.round(s.polar.rmssd) : '–'),
    h('td', { class: 'l' }, s.is_ref ? h('span', { class: 'label-chip REFERENCE' }, h('i'), 'Acuan') : '')));
  $('segTable').replaceChildren(h('thead', {}, head), h('tbody', {}, ...rows));
}

function renderMeasureSeg() {
  const seg = $('measureSeg');
  const list = ['Semua', ...S.res.measures];
  if (!list.includes(S.measure)) S.measure = S.res.measures[0];
  if (list.length > 8) { // many channels: a drop-down instead of a long row of buttons
    const sel = h('select', { 'aria-label': 'Ukuran uji', onchange: (e) => { S.measure = e.target.value; renderTests(); } },
      ...list.map((m) => h('option', { value: m }, m === 'Semua' ? 'Semua ukuran' : mLabel(m))));
    sel.value = S.measure;
    seg.className = 'measure-pick';
    seg.replaceChildren(sel);
    return;
  }
  seg.className = 'seg sm';
  seg.replaceChildren(...list.map((m) => h('button', { 'data-v': m, class: m === S.measure ? 'on' : null }, mLabel(m))));
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
    const asym = r.measure.startsWith('Asimetri');
    const change = fin(r.med_a) && fin(r.med_b)
      ? (asym ? signed(r.med_b - r.med_a, 3) : (r.med_a !== 0 ? `${signed(((r.med_b - r.med_a) / Math.abs(r.med_a)) * 100, 0)}%` : '–')) : '–';
    const result = r.p === null ? h('span', { class: 'badge' }, 'data kurang')
      : r.sig ? h('span', { class: 'badge sig' }, 'berbeda') : h('span', { class: 'badge' }, 'tidak berbeda');
    return h('tr', {},
      all ? td(mLabel(r.measure), 'l') : null,
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
    ? 'Kruskal–Wallis (semua ruas): ' + om.map((o) => `${mLabel(o.measure)} ${pStr(o.p)}`).join(' · ')
    : '';
}
const fmtP = (p) => (p < 0.001 ? '< 0,001' : p.toFixed(3).replace('.', ','));
const pStr = (p) => (p < 0.001 ? 'p < 0,001' : `p = ${fmtP(p)}`);

// --- spectrum -----------------------------------------------------------------------
function fillPsdSelect() {
  const sel = $('psdCh');
  const key = S.ov.label + '|' + CH.length;
  if (sel.dataset.key !== key) {
    const muse = CH.length <= 4;
    const opts = [h('option', { value: 'PAIR' }, muse ? 'AF7 + AF8 (dahi)' : `${S.res.pair_label} (frontal)`)];
    if (muse) opts.push(h('option', { value: 'R:Temporal' }, 'TP9 + TP10 (telinga)'));
    else for (const r of Object.keys(S.ov.regions)) opts.push(h('option', { value: `R:${r}` }, `Area ${r.toLowerCase()}`));
    for (const c of CH) opts.push(h('option', { value: c }, c));
    sel.replaceChildren(...opts);
    sel.dataset.key = key;
  }
  if (![...sel.options].some((o) => o.value === S.psdCh)) S.psdCh = 'PAIR';
  sel.value = S.psdCh;
}
function renderPsd() {
  const res = S.res;
  fillPsdSelect();
  const idx = S.psdCh === 'PAIR' ? pairIdx()
    : S.psdCh.startsWith('R:') ? (S.ov.regions[S.psdCh.slice(2)] || []).map((c) => CH.indexOf(c))
      : [CH.indexOf(S.psdCh)];
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

$('folderBtn').addEventListener('click', () => {
  if (WEB) { $('dirInput').click(); return; } // browser: pick a local folder
  $('rootInput').value = S.root; $('folderDlg').showModal();
});
async function openLocal(files, what) {
  if (!files || !files.length) return;
  busy(true);
  try {
    const data = await window.ENGINE.addFiles(files, S.sid);
    if (data.attachedTo) { // only Polar files: joined to the open recording
      toast('Data Polar digabung ke rekaman yang sedang dibuka.' + (data.errors.length ? ` ${data.errors.join('; ')}` : ''), 'info');
      await selectSession(data.attachedTo, true);
      return;
    }
    toast(`${data.added.length} rekaman dimuat dari ${what}.` + (data.polarJoined.length ? ` Data Polar digabung ke ${data.polarJoined.length} rekaman.` : '')
      + (data.errors.length ? ` Dilewati: ${data.errors.join('; ')}` : ''), 'info');
    applySessionList(data, true);
    const first = data.sessions.find((x) => x.id === data.added[0]);
    if (first) { $('sessionSel').value = first.id; selectSession(first.id); }
  } catch (err) { toast(err.message); } finally { busy(false); }
}
async function loadDemo() {
  busy(true);
  try { const data = await window.ENGINE.loadDemo(); applySessionList(data, true); } catch (err) { toast(err.message); } finally { busy(false); }
}
if (WEB) {
  document.querySelectorAll('.server-only').forEach((el) => { el.hidden = true; });
  document.querySelectorAll('.web-only').forEach((el) => { el.hidden = false; });
  $('zipInput').multiple = true;
  $('dirInput').addEventListener('change', (e) => { const f = [...e.target.files]; e.target.value = ''; openLocal(f, 'folder'); });
  $('demoBtn').addEventListener('click', loadDemo);
  if (ARTIFACT) {
    $('printBtn').hidden = true;
    const b = document.querySelector('[data-export=export]');
    b.textContent = 'Salin tabel';
    b.title = 'Salin tabel per ruas dan hasil uji (tempel ke Excel / Google Sheets)';
  }
}
function showCopyFallback(text) {
  const box = h('div', { class: 'copy-fallback card' },
    h('p', {}, h('b', {}, 'Salin manual: '), 'teks sudah dipilih, tekan Ctrl/⌘ + C lalu tempel ke spreadsheet.'),
    h('textarea', { id: 'copyText', readonly: true, rows: 10 }),
    h('div', { class: 'row end' }, h('button', { class: 'btn', onclick: () => box.remove() }, 'Tutup')));
  box.querySelector('textarea').value = text;
  document.body.append(box);
  box.querySelector('textarea').select();
}
$('folderDlg').addEventListener('close', () => {
  const rv = $('folderDlg').returnValue;
  if (rv === 'ok') loadSessions($('rootInput').value.trim());
  else if (rv === 'default') loadSessions('');
});
$('zipInput').addEventListener('change', async (e) => {
  if (WEB) { const fl = [...e.target.files]; e.target.value = ''; openLocal(fl, fl.length === 1 ? fl[0].name : `${fl.length} file`); return; }
  const f = e.target.files[0];
  e.target.value = '';
  if (!f) return;
  const fd = new FormData();
  fd.append('file', f);
  try {
    const data = await api('/api/upload', { method: 'POST', body: fd });
    toast(`${data.sessions.length} rekaman dari ${f.name} dimuat.`, 'info');
    applySessionList(data, true);
  } catch (err) { toast(err.message); }
});
document.querySelectorAll('[data-export]').forEach((b) => b.addEventListener('click', () => {
  if (!S.sid) return;
  const q = new URLSearchParams({ titik: S.set.titik, band: S.set.band, metric: S.set.metric, ref: S.set.ref, art: S.set.art, chans: S.set.chans, heart: S.set.heart, pshift: S.set.pshift });
  if (ARTIFACT) {
    busy(true);
    window.ENGINE.exportText(S.sid, Object.fromEntries(q)).then(async (text) => {
      try { await navigator.clipboard.writeText(text); toast('Tabel disalin. Tempel ke Excel atau Google Sheets.', 'info'); }
      catch { showCopyFallback(text); }
    }).catch((err) => toast(err.message)).finally(() => busy(false));
    return;
  }
  if (WEB) {
    busy(true);
    window.ENGINE.exportZip(S.sid, Object.fromEntries(q)).then(({ name, blob }) => {
      const a = h('a', { href: URL.createObjectURL(blob), download: name }); document.body.append(a); a.click(); a.remove();
    }).catch((err) => toast(err.message)).finally(() => busy(false));
    return;
  }
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
