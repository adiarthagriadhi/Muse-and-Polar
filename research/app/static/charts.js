// Small dependency-free canvas charts for Research View: time series with shared zoom,
// crosshair + tooltip, overlays (segments, markers, map window) and a head topomap.

export const css = (name) => getComputedStyle(document.documentElement).getPropertyValue(name).trim();
export const isDark = () => {
  const t = document.documentElement.dataset.theme;
  return t ? t === 'dark' : matchMedia('(prefers-color-scheme: dark)').matches;
};

const tooltip = () => document.getElementById('tooltip');

export function fmtTime(t, span = 0) {
  if (!Number.isFinite(t)) return '–';
  if (span < 120 && Math.abs(t) < 600) return `${+t.toFixed(span < 5 ? 2 : span < 30 ? 1 : 0)} s`;
  const s = Math.round(t), m = Math.floor(s / 60);
  return `${m}:${String(s - m * 60).padStart(2, '0')}`;
}

export function fmtTick(v) {
  if (!Number.isFinite(v)) return '';
  const a = Math.abs(v);
  if (a >= 1e4) return v.toExponential(0).replace('+', '');
  return String(+v.toPrecision(3));
}

export function fmtNum(v, digits = 3) {
  if (v === null || v === undefined || !Number.isFinite(v)) return '–';
  const a = Math.abs(v);
  if (a >= 1000) return v.toFixed(0);
  if (a >= 100) return v.toFixed(digits > 2 ? 1 : 0);
  if (a >= 10) return v.toFixed(Math.min(digits - 1, 2));
  if (a >= 1) return v.toFixed(Math.min(digits, 2));
  if (a === 0) return '0';
  return v.toPrecision(2);
}

function niceStep(span, target) {
  const raw = span / Math.max(1, target);
  const p = Math.pow(10, Math.floor(Math.log10(raw)));
  const m = raw / p;
  return (m < 1.5 ? 1 : m < 3.5 ? 2 : m < 7.5 ? 5 : 10) * p;
}
const TIME_STEPS = [0.1, 0.2, 0.5, 1, 2, 5, 10, 15, 30, 60, 120, 300, 600, 900, 1800, 3600];

function lowerBound(arr, x) {
  let lo = 0, hi = arr.length;
  while (lo < hi) { const mid = (lo + hi) >> 1; if (arr[mid] < x) lo = mid + 1; else hi = mid; }
  return lo;
}

// Keeps several charts on one x range and one hover position.
export class ChartGroup {
  constructor() { this.charts = []; this.x0 = 0; this.x1 = 1; this.hoverX = null; }
  add(c) { this.charts.push(c); c.group = this; return c; }
  setView(x0, x1) { this.x0 = x0; this.x1 = x1; this.charts.forEach((c) => c.draw()); }
  hover(x, src, ev) {
    this.hoverX = x;
    this.charts.forEach((c) => c.drawOverlay());
    if (x === null) { tooltip().hidden = true; return; }
    src.showTooltip(x, ev);
  }
}

export class Chart {
  constructor(el, opt = {}) {
    this.el = el;
    this.opt = Object.assign({
      padL: 58, padR: 12, padT: 10, padB: 20, yLog: false, xFmt: fmtTime, interactive: true,
      yFmt: (v) => fmtNum(v), tickFmt: fmtTick, title: '', lanes: 0, laneScale: 100, legend: true, markerLabels: false,
    }, opt);
    this.base = document.createElement('canvas');
    this.over = document.createElement('canvas');
    el.append(this.base, this.over);
    this.series = [];
    this.ov = { segments: [], markers: [], window: null };
    this.group = null;
    this.drag = null;
    this.ownX = null; // [x0, x1] when the chart is not in a group
    new ResizeObserver(() => this.draw()).observe(el);
    this._events();
  }

  get x0() { return this.ownX ? this.ownX[0] : this.group.x0; }
  get x1() { return this.ownX ? this.ownX[1] : this.group.x1; }

  setSeries(series) { this.series = series; this.draw(); }
  setOverlays(ov) { Object.assign(this.ov, ov); this.draw(); }

  _size(cv) {
    const r = this.el.getBoundingClientRect(), d = window.devicePixelRatio || 1;
    const w = Math.max(10, Math.round(r.width * d)), h = Math.max(10, Math.round(r.height * d));
    if (cv.width !== w || cv.height !== h) { cv.width = w; cv.height = h; }
    const ctx = cv.getContext('2d');
    ctx.setTransform(d, 0, 0, d, 0, 0);
    return { ctx, W: r.width, H: r.height };
  }

  plotBox() {
    const r = this.el.getBoundingClientRect(), o = this.opt;
    return { L: o.padL, R: r.width - o.padR, T: o.padT + (this._extraT || 0), B: r.height - o.padB };
  }
  xTo(t) { const b = this.plotBox(); return b.L + (t - this.x0) / (this.x1 - this.x0 || 1) * (b.R - b.L); }
  xFrom(px) { const b = this.plotBox(); return this.x0 + (px - b.L) / (b.R - b.L || 1) * (this.x1 - this.x0); }

  // y scale ---------------------------------------------------------------
  _yDomain() {
    if (this.opt.lanes) return [0, 1];
    if (this.opt.yDomain) return this.opt.yDomain;
    let lo = Infinity, hi = -Infinity;
    for (const s of this.series) {
      const i0 = Math.max(0, lowerBound(s.t, this.x0) - 1), i1 = Math.min(s.t.length, lowerBound(s.t, this.x1) + 1);
      for (let i = i0; i < i1; i++) {
        const v = s.y[i];
        if (v === null || !Number.isFinite(v) || (this.opt.yLog && v <= 0)) continue;
        if (v < lo) lo = v; if (v > hi) hi = v;
      }
    }
    if (!Number.isFinite(lo)) return this.opt.yLog ? [1, 10] : [0, 1];
    if (this.opt.yLog) {
      const a = Math.log10(lo), b = Math.log10(hi), pad = Math.max(0.05, (b - a) * 0.08);
      return [Math.pow(10, a - pad), Math.pow(10, b + pad)];
    }
    if (hi === lo) { hi += 1; lo -= 1; }
    const pad = (hi - lo) * 0.08;
    return [lo - pad, hi + pad];
  }
  _yMap(dom) {
    const b = this.plotBox();
    if (this.opt.yLog) {
      const a = Math.log10(dom[0]), c = Math.log10(dom[1]);
      return (v) => b.B - (Math.log10(v) - a) / (c - a) * (b.B - b.T);
    }
    return (v) => b.B - (v - dom[0]) / (dom[1] - dom[0]) * (b.B - b.T);
  }

  draw() {
    const { ctx, W, H } = this._size(this.base);
    ctx.clearRect(0, 0, W, H);
    if (!this.group && !this.ownX) return;
    const o = this.opt;
    // legend goes on its own line when it would collide with the title
    this._extraT = 0;
    if (o.title && o.legend && !o.lanes) {
      ctx.font = '600 11px system-ui, sans-serif';
      const tw = ctx.measureText(o.title).width;
      ctx.font = '11px system-ui, sans-serif';
      const lw = this.series.filter((s) => !s.noLegend).reduce((a, s) => a + ctx.measureText(s.name).width + 23, 0);
      if (tw + lw + 16 > W - o.padR) this._extraT = 14;
    }
    const b = this.plotBox();
    ctx.font = '11px system-ui, sans-serif';
    ctx.textBaseline = 'middle';

    // overlays behind data: segments, reference, map window
    for (const s of this.ov.segments || []) {
      const xa = Math.max(b.L, this.xTo(s.a)), xb = Math.min(b.R, this.xTo(s.b));
      if (xb <= xa) continue;
      ctx.fillStyle = s.ref ? css('--ref-fill') : (s.i % 2 ? css('--seg-fill') : 'transparent');
      ctx.fillRect(xa, b.T, xb - xa, b.B - b.T);
    }
    if (this.ov.window) {
      const xa = Math.max(b.L, this.xTo(this.ov.window.a)), xb = Math.min(b.R, this.xTo(this.ov.window.b));
      if (xb > xa) { ctx.fillStyle = css('--win-fill'); ctx.fillRect(xa, b.T, xb - xa, b.B - b.T); }
    }

    // grid + axes
    const dom = this._yDomain();
    const ymap = this._yMap(dom);
    ctx.strokeStyle = css('--grid'); ctx.lineWidth = 1; ctx.fillStyle = css('--text-muted');
    ctx.textAlign = 'right';
    if (o.lanes) {
      const lh = (b.B - b.T) / o.lanes;
      for (let j = 0; j < o.lanes; j++) {
        const yc = b.T + lh * (j + 0.5);
        ctx.beginPath(); ctx.moveTo(b.L, Math.round(yc) + 0.5); ctx.lineTo(b.R, Math.round(yc) + 0.5); ctx.stroke();
        const s = this.series.find((x) => x.lane === j);
        if (s) {
          ctx.fillStyle = s.color; ctx.fillRect(6, yc - 1.5, 10, 3);
          ctx.fillStyle = css('--text-secondary'); ctx.textAlign = 'left'; ctx.fillText(s.name, 20, yc);
        }
      }
    } else {
      const ticks = this._yTicks(dom);
      for (const v of ticks) {
        const y = Math.round(ymap(v)) + 0.5;
        if (y < b.T - 1 || y > b.B + 1) continue;
        ctx.beginPath(); ctx.moveTo(b.L, y); ctx.lineTo(b.R, y); ctx.stroke();
        ctx.fillText(o.tickFmt(v), b.L - 6, y);
      }
    }
    // x ticks
    const span = this.x1 - this.x0;
    const step = o.xStep ? o.xStep(span) : (TIME_STEPS.find((s) => span / s <= Math.max(3, (b.R - b.L) / 90)) || 3600);
    ctx.textAlign = 'center'; ctx.textBaseline = 'top'; ctx.fillStyle = css('--text-muted');
    for (let t = Math.ceil(this.x0 / step) * step; t <= this.x1 + 1e-9; t += step) {
      const x = Math.round(this.xTo(t)) + 0.5;
      ctx.strokeStyle = css('--grid');
      ctx.beginPath(); ctx.moveTo(x, b.T); ctx.lineTo(x, b.B); ctx.stroke();
      const lab = o.xFmt(t, span), lw = ctx.measureText(lab).width;
      ctx.fillText(lab, Math.min(x, W - lw / 2 - 1), b.B + 4);
    }
    ctx.strokeStyle = css('--axis');
    ctx.beginPath(); ctx.moveTo(b.L, b.B + 0.5); ctx.lineTo(b.R, b.B + 0.5); ctx.stroke();

    // data
    ctx.save();
    ctx.beginPath(); ctx.rect(b.L, b.T - 2, b.R - b.L, b.B - b.T + 4); ctx.clip();
    for (const s of this.series) this._drawSeries(ctx, s, ymap, b);
    ctx.restore();

    // boundaries + markers on top of data
    ctx.setLineDash([4, 3]); ctx.strokeStyle = css('--text-secondary'); ctx.lineWidth = 1;
    for (const s of this.ov.segments || []) {
      if (s.i === 0) continue;
      const x = Math.round(this.xTo(s.a)) + 0.5;
      if (x < b.L || x > b.R) continue;
      ctx.beginPath(); ctx.moveTo(x, b.T); ctx.lineTo(x, b.B); ctx.stroke();
    }
    ctx.setLineDash([]);
    ctx.strokeStyle = css('--marker'); ctx.fillStyle = css('--marker');
    ctx.textAlign = 'left'; ctx.textBaseline = 'top';
    let lastLabelEnd = -Infinity;
    for (const m of this.ov.markers || []) {
      const x = Math.round(this.xTo(m.t)) + 0.5;
      if (x < b.L || x > b.R) continue;
      ctx.lineWidth = 1.5;
      ctx.beginPath(); ctx.moveTo(x, b.T); ctx.lineTo(x, b.B); ctx.stroke();
      ctx.beginPath(); ctx.moveTo(x - 4, b.T); ctx.lineTo(x + 4, b.T); ctx.lineTo(x, b.T + 5); ctx.fill();
      if (o.markerLabels && x > lastLabelEnd + 6) {
        const txt = m.label.length > 26 ? m.label.slice(0, 25) + '…' : m.label;
        const w = ctx.measureText(txt).width;
        if (x + 4 + w < b.R) {
          ctx.fillStyle = css('--surface-1'); ctx.globalAlpha = 0.85; ctx.fillRect(x + 3, b.T + 5, w + 4, 14); ctx.globalAlpha = 1;
          ctx.fillStyle = css('--marker'); ctx.fillText(txt, x + 5, b.T + 6);
          lastLabelEnd = x + 4 + w;
        }
      }
    }
    // title + legend
    ctx.textBaseline = 'top'; ctx.textAlign = 'left';
    ctx.fillStyle = css('--text-secondary'); ctx.font = '600 11px system-ui, sans-serif';
    if (o.title) ctx.fillText(o.title, 2, 0);
    if (o.legend && !o.lanes) {
      ctx.font = '11px system-ui, sans-serif'; ctx.textAlign = 'right';
      let x = b.R - 4;
      for (const s of [...this.series].reverse()) {
        if (s.noLegend) continue;
        const w = ctx.measureText(s.name).width;
        const ly = this._extraT ? 13 : 0;
        ctx.fillStyle = css('--text-secondary'); ctx.fillText(s.name, x, ly);
        x -= w + 5; ctx.fillStyle = s.color; ctx.fillRect(x - 10, ly + 5, 10, 3); x -= 18;
      }
    }
    if (!this.series.length || (this.series.every((s) => !s.t.length))) {
      ctx.fillStyle = css('--text-muted'); ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
      ctx.fillText(this.opt.emptyText || 'tidak ada data', (b.L + b.R) / 2, (b.T + b.B) / 2);
    }
    this.drawOverlay();
  }

  _yTicks(dom) {
    if (this.opt.yLog) {
      const a = Math.floor(Math.log10(dom[0])), c = Math.ceil(Math.log10(dom[1]));
      const out = [];
      const mult = c - a <= 3 ? [1, 2, 5] : [1];
      for (let e = a; e <= c; e++) for (const m of mult) out.push(m * Math.pow(10, e));
      return out.filter((v) => v >= dom[0] && v <= dom[1]);
    }
    const step = niceStep(dom[1] - dom[0], 4);
    const out = [];
    for (let v = Math.ceil(dom[0] / step) * step; v <= dom[1]; v += step) out.push(+v.toPrecision(10));
    return out;
  }

  _drawSeries(ctx, s, ymap, b) {
    const o = this.opt;
    const i0 = Math.max(0, lowerBound(s.t, this.x0) - 1), i1 = Math.min(s.t.length, lowerBound(s.t, this.x1) + 1);
    ctx.strokeStyle = s.color; ctx.fillStyle = s.color; ctx.lineWidth = s.width || 1.5; ctx.lineJoin = 'round';
    if (o.lanes) {
      const lh = (b.B - b.T) / o.lanes, yc = b.T + lh * (s.lane + 0.5), k = (lh / 2) / o.laneScale;
      if (s.lo) { // min/max envelope
        ctx.lineWidth = 1;
        ctx.beginPath();
        for (let i = i0; i < i1; i++) {
          if (s.lo[i] === null) continue;
          const x = Math.round(this.xTo(s.t[i])) + 0.5;
          ctx.moveTo(x, yc - s.hi[i] * k); ctx.lineTo(x, yc - s.lo[i] * k + 0.8);
        }
        ctx.stroke();
      } else {
        ctx.lineWidth = 1;
        ctx.beginPath();
        let pen = false;
        for (let i = i0; i < i1; i++) {
          if (s.y[i] === null) { pen = false; continue; }
          const x = this.xTo(s.t[i]), y = yc - s.y[i] * k;
          pen ? ctx.lineTo(x, y) : ctx.moveTo(x, y); pen = true;
        }
        ctx.stroke();
      }
      return;
    }
    const gapDt = s.gap || Infinity;
    ctx.beginPath();
    let pen = false, prevT = null, n = 0;
    for (let i = i0; i < i1; i++) {
      const v = s.y[i];
      if (v === null || !Number.isFinite(v) || (o.yLog && v <= 0)) { pen = false; continue; }
      if (prevT !== null && s.t[i] - prevT > gapDt) pen = false;
      const x = this.xTo(s.t[i]), y = ymap(v);
      pen ? ctx.lineTo(x, y) : ctx.moveTo(x, y);
      pen = true; prevT = s.t[i]; n++;
    }
    ctx.stroke();
    // isolated points (surrounded by gaps) would be invisible as a line: draw dots
    if (s.dots || n < 60) {
      for (let i = i0; i < i1; i++) {
        const v = s.y[i];
        if (v === null || !Number.isFinite(v) || (o.yLog && v <= 0)) continue;
        ctx.beginPath(); ctx.arc(this.xTo(s.t[i]), ymap(v), 2, 0, Math.PI * 2); ctx.fill();
      }
    }
  }

  drawOverlay() {
    const { ctx, W, H } = this._size(this.over);
    ctx.clearRect(0, 0, W, H);
    const b = this.plotBox();
    const hx = this.group ? this.group.hoverX : this.hoverX;
    if (this.drag && Math.abs(this.drag.x1 - this.drag.x0) > 2) {
      const xa = Math.min(this.drag.x0, this.drag.x1), xb = Math.max(this.drag.x0, this.drag.x1);
      ctx.fillStyle = css('--win-fill'); ctx.fillRect(xa, b.T, xb - xa, b.B - b.T);
      ctx.strokeStyle = css('--accent'); ctx.strokeRect(xa + 0.5, b.T + 0.5, xb - xa, b.B - b.T);
    }
    if (hx === null || hx === undefined || hx < this.x0 || hx > this.x1) return;
    const x = Math.round(this.xTo(hx)) + 0.5;
    ctx.strokeStyle = css('--axis'); ctx.lineWidth = 1;
    ctx.beginPath(); ctx.moveTo(x, b.T); ctx.lineTo(x, b.B); ctx.stroke();
    if (this.opt.lanes) return;
    const ymap = this._yMap(this._yDomain());
    for (const s of this.series) {
      const i = this._nearest(s, hx);
      if (i < 0) continue;
      const v = s.y[i];
      if (v === null || !Number.isFinite(v) || (this.opt.yLog && v <= 0)) continue;
      ctx.fillStyle = s.color; ctx.strokeStyle = css('--surface-1'); ctx.lineWidth = 2;
      ctx.beginPath(); ctx.arc(this.xTo(s.t[i]), ymap(v), 4, 0, Math.PI * 2); ctx.fill(); ctx.stroke();
    }
  }

  _nearest(s, x) {
    if (!s.t.length) return -1;
    let i = lowerBound(s.t, x);
    if (i >= s.t.length) i = s.t.length - 1;
    if (i > 0 && Math.abs(s.t[i - 1] - x) < Math.abs(s.t[i] - x)) i--;
    const tol = (this.x1 - this.x0) * 0.03 + (s.tol || 0);
    return Math.abs(s.t[i] - x) <= tol ? i : -1;
  }

  showTooltip(x, ev) {
    const tt = tooltip();
    tt.replaceChildren();
    const h = document.createElement('div');
    h.className = 'tt-h'; h.textContent = this.opt.xFmt(x, this.x1 - this.x0) + (this.opt.xUnit || '');
    tt.append(h);
    const extra = this.opt.hoverInfo ? this.opt.hoverInfo(x) : null;
    if (extra) { const e = document.createElement('div'); e.className = 'tt-h'; e.textContent = extra; tt.append(e); }
    for (const s of this.series) {
      if (s.noTooltip) continue;
      const i = this._nearest(s, x);
      let txt = '–';
      if (i >= 0) {
        if (s.lo) txt = `${fmtNum(s.lo[i])} … ${fmtNum(s.hi[i])} µV`;
        else if (s.y[i] !== null && Number.isFinite(s.y[i])) txt = this.opt.yFmt(s.y[i]) + (s.unit ? ' ' + s.unit : '');
      }
      const r = document.createElement('div'); r.className = 'tt-r';
      const a = document.createElement('span'); const sw = document.createElement('i');
      sw.className = 'sw'; sw.style.background = s.color; a.append(sw, document.createTextNode(s.name));
      const v = document.createElement('b'); v.textContent = txt;
      r.append(a, v); tt.append(r);
    }
    tt.hidden = false;
    const w = tt.offsetWidth, hgt = tt.offsetHeight;
    let left = ev.clientX + 14, top = ev.clientY + 14;
    if (left + w > innerWidth - 8) left = ev.clientX - w - 14;
    if (top + hgt > innerHeight - 8) top = ev.clientY - hgt - 14;
    tt.style.left = left + 'px'; tt.style.top = top + 'px';
  }

  _events() {
    const el = this.over;
    const localX = (ev) => ev.clientX - this.el.getBoundingClientRect().left;
    const inPlot = (px) => { const b = this.plotBox(); return px >= b.L && px <= b.R; };
    const hover = (x, ev) => {
      if (this.group) this.group.hover(x, this, ev);
      else { this.hoverX = x; this.drawOverlay(); if (x === null) tooltip().hidden = true; else this.showTooltip(x, ev); }
    };
    el.addEventListener('pointermove', (ev) => {
      const px = localX(ev);
      if (this.drag) { this.drag.x1 = Math.max(this.plotBox().L, Math.min(this.plotBox().R, px)); this.drawOverlay(); }
      if (!inPlot(px)) { hover(null, ev); return; }
      hover(this.xFrom(px), ev);
    });
    el.addEventListener('pointerleave', (ev) => { if (!this.drag) hover(null, ev); });
    if (!this.opt.interactive) return;
    el.style.cursor = 'crosshair';
    el.addEventListener('pointerdown', (ev) => {
      const px = localX(ev);
      if (!inPlot(px) || ev.button !== 0) return;
      el.setPointerCapture(ev.pointerId);
      this.drag = { x0: px, x1: px };
    });
    el.addEventListener('pointerup', (ev) => {
      if (!this.drag) return;
      const { x0, x1 } = this.drag;
      this.drag = null;
      this.drawOverlay();
      if (Math.abs(x1 - x0) > 6) {
        const a = this.xFrom(Math.min(x0, x1)), c = this.xFrom(Math.max(x0, x1));
        this.opt.onZoom && this.opt.onZoom(a, c);
      } else if (this.opt.onPick) this.opt.onPick(this.xFrom(x0));
    });
    el.addEventListener('dblclick', () => this.opt.onReset && this.opt.onReset());
  }
}

// --- colour scales -----------------------------------------------------------------

const SEQ_LIGHT = ['#cde2fb', '#9ec5f4', '#6da7ec', '#3987e5', '#256abf', '#184f95', '#0d366b'];
const SEQ_DARK = ['#0d366b', '#184f95', '#256abf', '#3987e5', '#6da7ec', '#9ec5f4', '#cde2fb'];
const DIV_LIGHT = ['#1c5cab', '#5598e7', '#b7d3f6', '#f0efec', '#f4b8b0', '#e66767', '#b82d2d'];
const DIV_DARK = ['#9ec5f4', '#5598e7', '#1c5cab', '#383835', '#b82d2d', '#e66767', '#f4b8b0'];

export function scaleStops(scheme) {
  const d = isDark();
  return scheme === 'div' ? (d ? DIV_DARK : DIV_LIGHT) : (d ? SEQ_DARK : SEQ_LIGHT);
}
const hexRgb = (h) => [1, 3, 5].map((i) => parseInt(h.slice(i, i + 2), 16));
function colorAt(u, stops) {
  u = Math.max(0, Math.min(1, u));
  const p = u * (stops.length - 1), i = Math.min(stops.length - 2, Math.floor(p)), f = p - i;
  const a = hexRgb(stops[i]), b = hexRgb(stops[i + 1]);
  return [0, 1, 2].map((k) => Math.round(a[k] + (b[k] - a[k]) * f));
}
export const gradientCss = (scheme) => `linear-gradient(90deg, ${scaleStops(scheme).join(', ')})`;

// --- topomap ---------------------------------------------------------------------

export const POS = { AF7: [-0.5, 0.48], AF8: [0.5, 0.48], TP9: [-0.82, -0.2], TP10: [0.82, -0.2] };

export function drawTopo(canvas, values, { vmin, vmax, scheme = 'seq', labels = true, showValues = false, fmt = fmtNum } = {}) {
  const d = window.devicePixelRatio || 1;
  const size = canvas.getBoundingClientRect().width || canvas.width;
  const px = Math.max(40, Math.round(size * d));
  if (canvas.width !== px) { canvas.width = px; canvas.height = px; }
  const ctx = canvas.getContext('2d');
  ctx.setTransform(1, 0, 0, 1, 0, 0);
  ctx.clearRect(0, 0, px, px);
  const pad = px * (labels ? 0.1 : 0.06), R = px / 2 - pad, cx = px / 2, cy = px / 2 + (labels ? px * 0.02 : 0);
  const toPx = ([x, y]) => [cx + x * R, cy - y * R];
  const pts = Object.entries(POS).filter(([c]) => values[c] !== null && values[c] !== undefined && Number.isFinite(values[c]));
  const stops = scaleStops(scheme);
  const lw = Math.max(1, px / 160);
  if (pts.length >= 2 && Number.isFinite(vmin) && Number.isFinite(vmax)) {
    const n = Math.min(110, Math.round(R));
    const img = ctx.createImageData(2 * n, 2 * n);
    const span = vmax - vmin || 1;
    for (let j = 0; j < 2 * n; j++) {
      for (let i = 0; i < 2 * n; i++) {
        const x = (i + 0.5) / n - 1, y = 1 - (j + 0.5) / n;
        if (x * x + y * y > 1) continue;
        let ws = 0, vs = 0;
        for (const [c, [px0, py0]] of pts) {
          const dd = Math.hypot(x - px0, y - py0) + 1e-6, w = 1 / (dd * dd * dd);
          ws += w; vs += w * values[c];
        }
        const [r, g, b] = colorAt((vs / ws - vmin) / span, stops);
        const k = (j * 2 * n + i) * 4;
        img.data[k] = r; img.data[k + 1] = g; img.data[k + 2] = b; img.data[k + 3] = 255;
      }
    }
    const tmp = document.createElement('canvas');
    tmp.width = tmp.height = 2 * n;
    tmp.getContext('2d').putImageData(img, 0, 0);
    ctx.imageSmoothingEnabled = true;
    ctx.save();
    ctx.beginPath(); ctx.arc(cx, cy, R, 0, Math.PI * 2); ctx.clip();
    ctx.drawImage(tmp, cx - R, cy - R, 2 * R, 2 * R);
    ctx.restore();
  } else {
    ctx.fillStyle = css('--surface-2');
    ctx.beginPath(); ctx.arc(cx, cy, R, 0, Math.PI * 2); ctx.fill();
    ctx.fillStyle = css('--text-muted'); ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
    ctx.font = `${Math.max(9, px / 16)}px system-ui, sans-serif`;
    ctx.fillText('data kurang', cx, cy);
  }
  // head outline, nose, ears
  ctx.strokeStyle = css('--text-secondary'); ctx.lineWidth = lw;
  ctx.beginPath(); ctx.arc(cx, cy, R, 0, Math.PI * 2); ctx.stroke();
  ctx.beginPath(); ctx.moveTo(cx - R * 0.1, cy - R * 0.995); ctx.lineTo(cx, cy - R * 1.1); ctx.lineTo(cx + R * 0.1, cy - R * 0.995); ctx.stroke();
  for (const s of [-1, 1]) {
    ctx.beginPath(); ctx.ellipse(cx + s * R * 1.03, cy, R * 0.05, R * 0.16, 0, 0, Math.PI * 2); ctx.stroke();
  }
  // electrodes
  const fs = Math.max(9, Math.min(13 * d, px / 22));
  ctx.font = `600 ${fs}px system-ui, sans-serif`; ctx.textAlign = 'center';
  for (const [c, p] of Object.entries(POS)) {
    const [x, y] = toPx(p);
    const has = values[c] !== null && values[c] !== undefined && Number.isFinite(values[c]);
    ctx.fillStyle = has ? css('--text-primary') : css('--surface-1');
    ctx.strokeStyle = css('--surface-1'); ctx.lineWidth = Math.max(1.5, px / 120);
    ctx.beginPath(); ctx.arc(x, y, Math.max(2.5, px / 55), 0, Math.PI * 2); ctx.fill(); ctx.stroke();
    if (!has) { ctx.strokeStyle = css('--text-muted'); ctx.lineWidth = 1; ctx.stroke(); }
    if (labels) {
      const txt = showValues && has ? `${c} ${fmt(values[c])}` : c;
      ctx.textBaseline = 'top';
      const w = ctx.measureText(txt).width;
      const lx = Math.max(w / 2 + 4, Math.min(px - w / 2 - 4, x));
      ctx.fillStyle = css('--surface-1'); ctx.globalAlpha = 0.85;
      ctx.fillRect(lx - w / 2 - 3, y + px / 40, w + 6, fs + 4); ctx.globalAlpha = 1;
      ctx.fillStyle = css('--text-primary'); ctx.fillText(txt, lx, y + px / 40 + 2);
    }
  }
}
