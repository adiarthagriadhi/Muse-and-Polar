'use strict';

const $ = (id) => document.getElementById(id);
const STATE_LABEL = {
  disconnected: 'terputus', scanning: 'mencari…', not_found: 'tidak ditemukan',
  connecting: 'menghubungkan…', streaming: 'streaming', error: 'error', stale: 'tanpa data',
};
const QUICK_MARKERS = ['Baseline mulai', 'Mata tertutup', 'Mata terbuka', 'Tugas mulai', 'Tugas selesai'];
const BANDS = [['delta', 'Delta'], ['theta', 'Theta'], ['alpha', 'Alfa'], ['beta', 'Beta'], ['gamma', 'Gamma']];
const EEG_CH = ['TP9', 'AF7', 'AF8', 'TP10'];

// ---------------------------------------------------------------- colours
let css = {};
function readColors() {
  const s = getComputedStyle(document.documentElement);
  const get = (n) => s.getPropertyValue(n).trim();
  css = {
    s1: get('--series-1'), s2: get('--series-2'), s3: get('--series-3'), s4: get('--series-4'),
    grid: get('--grid'), axis: get('--axis'), text: get('--text-secondary'), muted: get('--text-muted'),
    primary: get('--text-primary'), marker: get('--marker'), surface: get('--surface-1'),
  };
}
readColors();
matchMedia('(prefers-color-scheme: dark)').addEventListener('change', readColors);

// ---------------------------------------------------------------- buffers
class Ring {
  constructor(cap, ncol) {
    this.cap = cap; this.n = 0; this.i = 0; this.total = 0;
    this.t = new Float64Array(cap);
    this.v = Array.from({ length: ncol }, () => new Float64Array(cap));
  }
  push(t, row) {
    const i = this.i;
    this.t[i] = t;
    for (let c = 0; c < this.v.length; c++) this.v[c][i] = row[c];
    this.i = (i + 1) % this.cap;
    if (this.n < this.cap) this.n++;
    this.total++;
  }
  idx(k) { return (this.i - 1 - k + this.cap) % this.cap; } // k = 0 is newest
  clear() { this.n = 0; this.i = 0; }
}

// RBJ biquads; `dc` = steady-state gain for a constant input (for clean start-up)
class Biquad {
  constructor(b0, b1, b2, a0, a1, a2, dc) {
    this.b0 = b0 / a0; this.b1 = b1 / a0; this.b2 = b2 / a0; this.a1 = a1 / a0; this.a2 = a2 / a0;
    this.dc = dc; this.ready = false;
  }
  step(x) {
    if (!this.ready) { this.x1 = this.x2 = x; this.y1 = this.y2 = x * this.dc; this.ready = true; }
    const y = this.b0 * x + this.b1 * this.x1 + this.b2 * this.x2 - this.a1 * this.y1 - this.a2 * this.y2;
    this.x2 = this.x1; this.x1 = x; this.y2 = this.y1; this.y1 = y;
    return y;
  }
}
function highpass(fs, f0, q = Math.SQRT1_2) {
  const w = 2 * Math.PI * f0 / fs, c = Math.cos(w), a = Math.sin(w) / (2 * q);
  return new Biquad((1 + c) / 2, -(1 + c), (1 + c) / 2, 1 + a, -2 * c, 1 - a, 0);
}
function notch(fs, f0, q = 30) {
  const w = 2 * Math.PI * f0 / fs, c = Math.cos(w), a = Math.sin(w) / (2 * q);
  return new Biquad(1, -2 * c, 1, 1 + a, -2 * c, 1 - a, 1);
}

const settings = { eegScale: 100, notch: 50, hpf: true };
const streams = {};
function defineStream(name, rate, ncol, seconds, makeChain) {
  const cap = rate ? Math.ceil(rate * seconds) : seconds; // irregular streams: `seconds` = max points
  streams[name] = { name, rate, raw: new Ring(cap, ncol), disp: new Ring(cap, ncol), makeChain, chains: null, last: 0 };
}
defineStream('muse_eeg', 256, 4, 12, () => {
  const ch = [];  // same chain on every EEG channel
  if (settings.hpf) ch.push(highpass(256, 1));
  if (settings.notch) ch.push(notch(256, settings.notch));
  return ch;
});
defineStream('muse_ppg', 64, 3, 12, () => [highpass(64, 0.5)]);
defineStream('muse_acc', 52, 3, 12, null);
defineStream('polar_ecg', 130, 2, 12, (c) => (c === 0 ? [highpass(130, 0.5)] : []));
defineStream('polar_acc', 200, 4, 12, null);
defineStream('polar_rr', 0, 1, 1000, null);
defineStream('polar_hr', 0, 2, 1000, null);
const markers = [];

function filterRow(st, row) {
  if (!st.makeChain) return row;
  if (!st.chains) st.chains = row.map((_, c) => st.makeChain(c));
  return row.map((v, c) => st.chains[c].reduce((x, f) => f.step(x), v));
}
function ingest(name, t, v) {
  const st = streams[name];
  if (!st) return;
  // a gap > 1 s restarts the filters so old state doesn't ring into new data
  if (st.rate && t.length && st.raw.n && t[0] - st.raw.t[st.raw.idx(0)] > 1) st.chains = null;
  for (let k = 0; k < t.length; k++) {
    st.raw.push(t[k], v[k]);
    st.disp.push(t[k], filterRow(st, v[k]));
  }
  st.last = performance.now();
}
function refilter(name) {
  const st = streams[name];
  st.chains = null;
  st.disp.clear();
  for (let k = st.raw.n - 1; k >= 0; k--) {
    const i = st.raw.idx(k);
    const row = st.raw.v.map((col) => col[i]);
    st.disp.push(st.raw.t[i], filterRow(st, row));
  }
}

// ---------------------------------------------------------------- time
let clockOffset = 0; // server_time - browser time (s)
const nowServer = () => Date.now() / 1000 + clockOffset;
function syncClock(serverTime) {
  if (typeof serverTime !== 'number') return;
  const off = serverTime - Date.now() / 1000;
  clockOffset = clockOffset === 0 ? off : clockOffset * 0.9 + off * 0.1;
}

// ---------------------------------------------------------------- charts
const tooltip = document.createElement('div');
tooltip.className = 'tooltip';
document.body.appendChild(tooltip);

function niceStep(range, target) {
  const raw = range / target, p = Math.pow(10, Math.floor(Math.log10(raw))), r = raw / p;
  return (r < 1.5 ? 1 : r < 3 ? 2 : r < 7 ? 5 : 10) * p;
}
function fmt(v, unit) {
  const a = Math.abs(v);
  const s = a >= 1000 ? v.toFixed(0) : a >= 10 ? v.toFixed(1) : a >= 1 ? v.toFixed(2) : v.toFixed(3);
  return unit ? `${s} ${unit}` : s;
}

class StripChart {
  constructor(canvas, opt) {
    this.c = canvas; this.ctx = canvas.getContext('2d'); this.o = opt;
    this.hover = null;
    canvas.addEventListener('mousemove', (e) => { this.hover = { x: e.offsetX, cx: e.clientX, cy: e.clientY }; });
    canvas.addEventListener('mouseleave', () => { this.hover = null; tooltip.style.display = 'none'; });
  }
  get ring() { return (this.o.raw ? streams[this.o.stream].raw : streams[this.o.stream].disp); }

  draw(now) {
    const { c, ctx, o } = this;
    const dpr = window.devicePixelRatio || 1;
    const W = c.clientWidth, H = c.clientHeight;
    if (!W || !H) return;
    if (c.width !== Math.round(W * dpr) || c.height !== Math.round(H * dpr)) {
      c.width = Math.round(W * dpr); c.height = Math.round(H * dpr);
    }
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, W, H);
    const L = o.lanes ? 56 : 52, R = 8, T = 8, B = 18;
    const pw = W - L - R, ph = H - T - B;
    const t1 = now, t0 = now - o.window;
    const X = (t) => L + (t - t0) / o.window * pw;
    const ring = this.ring;
    const cols = o.cols;

    // visible index range (newest -> oldest)
    let kEnd = 0;
    while (kEnd < ring.n && ring.t[ring.idx(kEnd)] >= t0) kEnd++;
    const kStart = Math.min(kEnd, ring.n); // number of visible points

    // y mapping
    let Y, lanes = null, lo = 0, hi = 1;
    if (o.lanes) {
      const half = o.scale();
      const lh = ph / cols.length;
      lanes = cols.map((_, j) => T + lh * (j + 0.5));
      Y = (v, j) => lanes[j] - Math.max(-1, Math.min(1, v / half)) * lh / 2;
    } else {
      lo = Infinity; hi = -Infinity;
      for (let k = 0; k < kStart; k++) {
        const i = ring.idx(k);
        for (const cI of cols) { const v = ring.v[cI][i]; if (v < lo) lo = v; if (v > hi) hi = v; }
      }
      if (!isFinite(lo)) { lo = 0; hi = 1; }
      if (o.minRange && hi - lo < o.minRange) { const m = (hi + lo) / 2; lo = m - o.minRange / 2; hi = m + o.minRange / 2; }
      const pad = (hi - lo) * 0.1 || 1; lo -= pad; hi += pad;
      Y = (v) => T + (1 - (v - lo) / (hi - lo)) * ph;
    }

    // grid + axes
    ctx.lineWidth = 1; ctx.font = '11px -apple-system, system-ui, sans-serif';
    ctx.strokeStyle = css.grid; ctx.fillStyle = css.muted; ctx.textAlign = 'center'; ctx.textBaseline = 'top';
    const xs = niceStep(o.window, Math.max(2, Math.min(8, pw / 70)));
    for (let s = 0; s <= o.window + 1e-9; s += xs) {
      const x = L + pw - s / o.window * pw;
      ctx.beginPath(); ctx.moveTo(x + 0.5, T); ctx.lineTo(x + 0.5, T + ph); ctx.stroke();
      ctx.fillText(s === 0 ? 'kini' : `−${s} s`, Math.max(L + 12, Math.min(W - 14, x)), T + ph + 4);
    }
    ctx.textAlign = 'right'; ctx.textBaseline = 'middle';
    if (o.lanes) {
      const half = o.scale();
      cols.forEach((cI, j) => {
        ctx.strokeStyle = css.grid;
        ctx.beginPath(); ctx.moveTo(L, lanes[j] + 0.5); ctx.lineTo(L + pw, lanes[j] + 0.5); ctx.stroke();
        ctx.fillStyle = css.text; ctx.font = '600 11px -apple-system, system-ui, sans-serif';
        ctx.fillText(o.labels[j], L - 8, lanes[j]);
        ctx.fillStyle = o.colors[j]; ctx.fillRect(L - 8 - ctx.measureText(o.labels[j]).width - 12, lanes[j] - 1, 8, 3);
      });
      ctx.fillStyle = css.muted; ctx.font = '11px -apple-system, system-ui, sans-serif';
      ctx.textAlign = 'left'; ctx.textBaseline = 'top';
      ctx.fillText(`±${half} µV / lajur`, L + 4, T);
    } else {
      const ys = niceStep(hi - lo, Math.max(2, Math.min(5, ph / 35)));
      const dec = Math.max(0, -Math.floor(Math.log10(ys) + 1e-9));
      for (let v = Math.ceil(lo / ys) * ys; v <= hi; v += ys) {
        const y = Y(v);
        ctx.strokeStyle = css.grid; ctx.beginPath(); ctx.moveTo(L, y + 0.5); ctx.lineTo(L + pw, y + 0.5); ctx.stroke();
        ctx.fillStyle = css.muted; ctx.fillText((Math.abs(v) < ys / 1e6 ? 0 : v).toFixed(dec).replace('-', '−'), L - 6, y);
      }
    }
    ctx.strokeStyle = css.axis; ctx.beginPath(); ctx.moveTo(L, T + ph + 0.5); ctx.lineTo(L + pw, T + ph + 0.5); ctx.stroke();

    // markers
    ctx.save(); ctx.setLineDash([4, 4]); ctx.strokeStyle = css.marker; ctx.fillStyle = css.marker;
    ctx.textAlign = 'left'; ctx.textBaseline = 'top';
    const placed = []; // label boxes already drawn, to stack overlapping labels
    for (let n = markers.length - 1; n >= 0; n--) {
      const m = markers[n];
      if (m.t < t0 || m.t > t1 + 1) continue;
      const x = X(m.t);
      ctx.beginPath(); ctx.moveTo(x + 0.5, T); ctx.lineTo(x + 0.5, T + ph); ctx.stroke();
      if (pw < 260 || ph < 110) continue; // small charts: line only, label lives in the marker log
      const w = ctx.measureText(m.label).width;
      const lx = x + 4 + w > L + pw ? x - 4 - w : x + 4;
      let row = 0;
      while (placed.some((p) => p.row === row && lx < p.r + 6 && lx + w > p.l - 6)) row++;
      placed.push({ l: lx, r: lx + w, row });
      ctx.fillText(m.label, lx, T + ph - 14 - row * 13);
    }
    ctx.restore();

    // series
    const gapMax = o.rate ? 5 / o.rate : 3;
    ctx.save(); ctx.beginPath(); ctx.rect(L, T - 2, pw, ph + 4); ctx.clip();
    ctx.lineWidth = o.lineWidth || 1.5; ctx.lineJoin = 'round';
    cols.forEach((cI, j) => {
      ctx.strokeStyle = o.colors[j]; ctx.beginPath();
      let prevT = null;
      for (let k = 0; k < kStart; k++) {
        const i = ring.idx(k), t = ring.t[i];
        const x = X(t), y = Y(ring.v[cI][i], j);
        if (prevT === null || prevT - t > gapMax) ctx.moveTo(x, y); else ctx.lineTo(x, y);
        prevT = t;
      }
      ctx.stroke();
      if (o.points) {
        ctx.fillStyle = o.colors[j];
        for (let k = 0; k < kStart; k++) {
          const i = ring.idx(k);
          ctx.beginPath(); ctx.arc(X(ring.t[i]), Y(ring.v[cI][i], j), 2.5, 0, 2 * Math.PI); ctx.fill();
        }
      }
    });
    ctx.restore();

    if (!kStart) {
      ctx.fillStyle = css.muted; ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
      ctx.font = '12px -apple-system, system-ui, sans-serif';
      ctx.fillText('menunggu data…', L + pw / 2, T + ph / 2);
    }

    // hover crosshair + tooltip
    if (this.hover && kStart && this.hover.x >= L && this.hover.x <= L + pw) {
      const th = t0 + (this.hover.x - L) / pw * o.window;
      let best = -1, bd = Infinity;
      for (let k = 0; k < kStart; k++) {
        const i = ring.idx(k), d = Math.abs(ring.t[i] - th);
        if (d < bd) { bd = d; best = i; }
      }
      const x = X(ring.t[best]);
      ctx.strokeStyle = css.axis; ctx.lineWidth = 1;
      ctx.beginPath(); ctx.moveTo(x + 0.5, T); ctx.lineTo(x + 0.5, T + ph); ctx.stroke();
      let html = `<div class="muted">${(ring.t[best] - now).toFixed(2)} s</div>`;
      cols.forEach((cI, j) => {
        const v = ring.v[cI][best];
        ctx.fillStyle = o.colors[j]; ctx.strokeStyle = css.surface; ctx.lineWidth = 2;
        ctx.beginPath(); ctx.arc(x, Y(v, j), 4, 0, 2 * Math.PI); ctx.fill(); ctx.stroke();
        html += `<div class="row"><span class="sw" style="background:${o.colors[j]}"></span>${o.labels[j]}: <b>${fmt(v, o.unit)}</b></div>`;
      });
      tooltip.innerHTML = html;
      tooltip.style.display = 'block';
      tooltip.style.left = Math.min(window.innerWidth - 160, this.hover.cx + 14) + 'px';
      tooltip.style.top = Math.min(window.innerHeight - tooltip.offsetHeight - 8, this.hover.cy + 14) + 'px';
    }
  }
}

const charts = [];
function makeCharts() {
  charts.length = 0;
  charts.push(new StripChart($('eegChart'), {
    stream: 'muse_eeg', cols: [0, 1, 2, 3], labels: EEG_CH, rate: 256, window: 6, lanes: true, unit: 'µV',
    scale: () => settings.eegScale, get colors() { return [css.s1, css.s2, css.s3, css.s4]; },
  }));
  charts.push(new StripChart($('ecgChart'), {
    stream: 'polar_ecg', cols: [0], labels: ['EKG'], rate: 130, window: 6, unit: 'µV', minRange: 200,
    get colors() { return [css.s1]; },
  }));
  charts.push(new StripChart($('rrChart'), {
    stream: 'polar_rr', raw: true, cols: [0], labels: ['RR'], rate: 0, window: 120, unit: 'ms', points: true,
    minRange: 100, lineWidth: 2, get colors() { return [css.s1]; },
  }));
  charts.push(new StripChart($('polarAccChart'), {
    stream: 'polar_acc', raw: true, cols: [0, 1, 2], labels: ['x', 'y', 'z'], rate: 200, window: 10, unit: 'g',
    minRange: 0.2, get colors() { return [css.s1, css.s2, css.s3]; },
  }));
  charts.push(new StripChart($('ppgChart'), {
    stream: 'muse_ppg', cols: [1], labels: ['IR'], rate: 64, window: 8, unit: '',
    get colors() { return [css.s1]; },
  }));
  charts.push(new StripChart($('accChart'), {
    stream: 'muse_acc', raw: true, cols: [0, 1, 2], labels: ['x', 'y', 'z'], rate: 52, window: 10, unit: 'g',
    minRange: 0.2, get colors() { return [css.s1, css.s2, css.s3]; },
  }));
}
makeCharts();

function frame() {
  const now = nowServer() - 0.1;
  for (const ch of charts) ch.draw(now);
  requestAnimationFrame(frame);
}
requestAnimationFrame(frame);

// ---------------------------------------------------------------- UI state
let status = {};
let recording = null;

function renderStatus() {
  for (const dev of ['muse', 'polar']) {
    const s = status[dev] || { state: 'disconnected' };
    const root = $(`dev-${dev}`);
    let state = s.state;
    const stream = dev === 'muse' ? streams.muse_eeg : streams.polar_hr;
    if (state === 'streaming' && stream.last && performance.now() - stream.last > 4000) state = 'stale';
    const chip = root.querySelector('[data-role=state]');
    chip.className = `chip ${state}`;
    chip.textContent = STATE_LABEL[state] || state;
    chip.title = s.message || '';
    const meta = root.querySelector('[data-role=name]');
    meta.textContent = s.message && s.state !== 'streaming' ? s.message : (s.name || '—');
    meta.title = meta.textContent;
    root.querySelector('[data-role=battery]').textContent = s.battery != null ? `baterai ${s.battery}%` : 'baterai —';
    root.querySelector('[data-role=toggle]').textContent = s.state === 'disconnected' ? 'Hubungkan' : 'Putuskan';
  }
}
setInterval(renderStatus, 1000);

function hms(sec) {
  sec = Math.max(0, Math.floor(sec));
  return [sec / 3600, (sec % 3600) / 60, sec % 60].map((x) => String(Math.floor(x)).padStart(2, '0')).join(':');
}
function renderRecording() {
  const active = recording && recording.active;
  $('recBtn').classList.toggle('active', !!active);
  $('recLabel').textContent = active ? 'Stop rekam' : 'Mulai rekam';
  $('sessionName').disabled = !!active;
  if (recording) {
    $('recTimer').textContent = hms(recording.elapsed);
    const p = recording.dir;
    $('recPath').textContent = active ? `→ ${p}` : `Tersimpan: ${p}`;
    $('recPath').title = p;
  }
}

function renderMetrics(m) {
  if (m.hrv) {
    $('rmssd').textContent = m.hrv.rmssd.toFixed(1);
    $('sdnn').textContent = m.hrv.sdnn.toFixed(1);
    $('pnn50').textContent = m.hrv.pnn50.toFixed(0);
    $('hrvNote').textContent = `HRV dari ${m.hrv.n} RR, ${m.hrv.window_sec} s terakhir`;
  }
  const bands = $('bands');
  if (m.eeg) {
    bands.innerHTML = BANDS.map(([k, name]) => {
      const v = m.eeg.relative[k] * 100;
      return `<div class="band"><span class="name">${name}</span><div class="bar"><div class="fill" style="width:${v.toFixed(1)}%"></div></div><span class="val">${v.toFixed(0)}%</span></div>`;
    }).join('');
    $('quality').innerHTML = EEG_CH.map((ch, j) => {
      const n = m.eeg.noise_uV[ch];
      const [cls, label] = n < 1 ? ['critical', '✕ datar'] : n < 30 ? ['good', '✓ baik'] : n < 80 ? ['warning', '! sedang'] : ['critical', '✕ buruk'];
      const col = [css.s1, css.s2, css.s3, css.s4][j];
      return `<span class="q" title="Deviasi standar 1 s: ${n.toFixed(1)} µV"><span class="sw" style="background:${col}"></span>${ch} <span class="st ${cls}">${label}</span></span>`;
    }).join('');
  } else {
    // no fresh EEG: don't leave the last values on screen
    bands.innerHTML = '<p class="muted small">Menunggu 2 detik data EEG…</p>';
    $('quality').innerHTML = EEG_CH.map((ch, j) =>
      `<span class="q"><span class="sw" style="background:${[css.s1, css.s2, css.s3, css.s4][j]}"></span>${ch} <span class="st muted">—</span></span>`).join('');
  }
  if (m.recording) { recording = m.recording; renderRecording(); }
}

function updateRates() {
  const nowMs = performance.now();
  document.querySelectorAll('[data-rate]').forEach((el) => {
    const st = streams[el.dataset.rate];
    if (!st) return;
    if (st.rate) {
      const prev = st._rate;
      st._rate = { total: st.raw.total, ms: nowMs };
      if (!prev || !st.raw.total) { el.textContent = ''; return; }
      const hz = (st.raw.total - prev.total) / ((nowMs - prev.ms) / 1000);
      el.textContent = `${hz.toFixed(0)} Hz (nominal ${st.rate})`;
    } else {
      el.textContent = st.raw.n ? `${Math.min(st.raw.n, 999)} denyut` : '';
    }
  });
}
setInterval(updateRates, 2000);

function addMarker(t, label) {
  markers.push({ t, label });
  if (markers.length > 500) markers.shift();
  const li = document.createElement('li');
  li.innerHTML = `<span class="mono">${new Date(t * 1000).toLocaleTimeString('id-ID')}</span><span></span>`;
  li.lastChild.textContent = label;
  $('markerLog').prepend(li);
}

function onData(streamsMsg) {
  for (const [name, d] of Object.entries(streamsMsg)) {
    if (name === 'marker') { d.t.forEach((t, k) => addMarker(t, d.v[k][0])); continue; }
    ingest(name, d.t, d.v);
    if (name === 'polar_hr' && d.v.length) {
      const [hr, contact] = d.v[d.v.length - 1];
      $('hrValue').textContent = hr;
      $('contact').textContent = `kontak kulit: ${contact === 1 ? 'ya' : contact === 0 ? 'TIDAK — basahi elektroda' : 'n/a'}`;
    }
    if (name === 'polar_rr' && d.v.length) $('rrLast').textContent = Math.round(d.v[d.v.length - 1][0]);
  }
}

// ---------------------------------------------------------------- sync
let syncTimer = null;
function renderSync(sync) {
  const btn = $('syncBtn'), box = $('syncResult');
  clearInterval(syncTimer);
  if (sync.active) {
    btn.disabled = true;
    const tick = () => {
      const left = Math.max(0, sync.start + sync.duration - nowServer());
      btn.textContent = left > 0 ? `Loncat sekarang… ${left.toFixed(0)} s` : 'Menghitung…';
    };
    tick();
    syncTimer = setInterval(tick, 250);
    return;
  }
  btn.disabled = false;
  btn.textContent = 'Mulai sinkronisasi (10 s)';
  const r = sync.result;
  if (!r) { box.innerHTML = ''; return; }
  const when = new Date(r.start_unix * 1000).toLocaleTimeString('id-ID');
  if (!('muse_minus_polar_s' in r)) {
    box.innerHTML = `<span class="st critical">✕ Gagal</span> <span class="muted">(${when})</span><div class="small"></div>`;
    box.querySelector('div').textContent = r.reason;
    return;
  }
  const ms = r.muse_minus_polar_s * 1000;
  const [cls, label] = r.ok ? ['good', '✓ Berhasil'] : ['warning', '! Ragu'];
  box.innerHTML = `<span class="st ${cls}">${label}</span> <span class="muted">(${when})</span>
    <div class="sync-val"><b class="mono">${ms >= 0 ? '+' : '−'}${Math.abs(ms).toFixed(0)} ms</b>
    <span class="muted small">Muse − Polar</span></div>
    <div class="small muted">korelasi ${r.correlation.toFixed(2)} · kejadian terdeteksi Muse ${r.events_a}, Polar ${r.events_b}</div>
    <div class="small"></div>`;
  box.lastElementChild.textContent = r.ok
    ? (ms >= 0 ? 'Kejadian yang sama tercatat lebih lambat di Muse.' : 'Kejadian yang sama tercatat lebih lambat di Polar.')
    : r.reason;
}

// ---------------------------------------------------------------- socket
let ws = null;
function send(obj) { if (ws && ws.readyState === 1) ws.send(JSON.stringify(obj)); }
function connect() {
  ws = new WebSocket(`${location.protocol === 'https:' ? 'wss' : 'ws'}://${location.host}/ws`);
  ws.onopen = () => { $('liveDot').classList.add('on'); $('serverInfo').textContent = `Terhubung ke ${location.host}`; };
  ws.onclose = () => {
    $('liveDot').classList.remove('on');
    $('serverInfo').textContent = 'Server terputus — mencoba lagi…';
    setTimeout(connect, 1500);
  };
  ws.onmessage = (ev) => {
    const m = JSON.parse(ev.data);
    switch (m.type) {
      case 'hello':
        syncClock(m.server_time); status = m.status; renderStatus();
        if (m.recording) { recording = m.recording; renderRecording(); }
        if (m.sync) renderSync(m.sync);
        break;
      case 'status': status = m.status; renderStatus(); break;
      case 'data': onData(m.streams); break;
      case 'metrics': syncClock(m.server_time); renderMetrics(m); break;
      case 'recording': recording = m.recording; renderRecording(); break;
      case 'sync': renderSync(m.sync); break;
    }
  };
}
connect();

// ---------------------------------------------------------------- controls
document.querySelectorAll('[data-role=toggle]').forEach((btn) => {
  btn.addEventListener('click', () => {
    const dev = btn.dataset.device;
    const s = status[dev] || { state: 'disconnected' };
    send({ cmd: s.state === 'disconnected' ? 'connect' : 'disconnect', device: dev });
  });
});
$('recBtn').addEventListener('click', () => {
  if (recording && recording.active) send({ cmd: 'record_stop' });
  else send({ cmd: 'record_start', name: $('sessionName').value });
});
function sendMarker(label) { if (label) send({ cmd: 'marker', label }); }
$('markerBtn').addEventListener('click', () => { sendMarker($('markerInput').value.trim()); $('markerInput').value = ''; });
$('markerInput').addEventListener('keydown', (e) => { if (e.key === 'Enter') $('markerBtn').click(); });
$('quickMarkers').innerHTML = QUICK_MARKERS.map((m, i) => `<button class="btn" data-mk="${i}"><kbd>${i + 1}</kbd>${m}</button>`).join('');
$('quickMarkers').addEventListener('click', (e) => {
  const b = e.target.closest('[data-mk]');
  if (b) sendMarker(QUICK_MARKERS[+b.dataset.mk]);
});
document.addEventListener('keydown', (e) => {
  if (e.target.matches('input, select, textarea') || e.metaKey || e.ctrlKey || e.altKey) return;
  const n = parseInt(e.key, 10);
  if (n >= 1 && n <= QUICK_MARKERS.length) sendMarker(QUICK_MARKERS[n - 1]);
});
$('syncBtn').addEventListener('click', () => send({ cmd: 'sync', duration: 10 }));
$('eegScale').addEventListener('change', (e) => { settings.eegScale = +e.target.value; });
$('notch').addEventListener('change', (e) => { settings.notch = +e.target.value; refilter('muse_eeg'); });
$('hpf').addEventListener('change', (e) => { settings.hpf = e.target.checked; refilter('muse_eeg'); });
window.addEventListener('beforeunload', (e) => {
  if (recording && recording.active) { e.preventDefault(); e.returnValue = ''; }
});
renderStatus();
renderMetrics({});
