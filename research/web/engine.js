// Research View engine for the browser: a JavaScript port of research/src/muse2_pipeline
// (EDF/CSV reading, filtering, spectra, artifact rejection, segment analysis, statistics,
// heart beats, Muse-like 4-channel view). It answers the same requests as app/server.py, so
// the same app.js runs with no Python: window.ENGINE.handle('/api/analysis/<id>?...').

const ENGINE = (() => {
  // ---------------------------------------------------------------- numbers
  const BANDS = { delta: [1, 4], theta: [4, 8], alpha: [8, 13], beta: [13, 30] };
  const BAND_NAMES = Object.keys(BANDS);
  const nan = NaN;
  const fin = (v) => v !== null && v !== undefined && Number.isFinite(v);
  const num = (v, d = 4) => (fin(v) ? (Math.abs(v) < 1e-9 ? 0 : +(+v).toPrecision(d)) : null);
  const arr = (a, d = 4) => Array.from(a, (v) => num(v, d));
  function sorted(a) { return Float64Array.from(a.filter(fin)).sort(); }
  function median(a) { const s = sorted(a); if (!s.length) return nan; const m = s.length >> 1; return s.length % 2 ? s[m] : (s[m - 1] + s[m]) / 2; }
  function percentile(a, q) {
    const s = sorted(a); if (!s.length) return nan;
    const p = (q / 100) * (s.length - 1), i = Math.floor(p), f = p - i;
    return i + 1 < s.length ? s[i] + (s[i + 1] - s[i]) * f : s[i];
  }
  function mean(a) { let s = 0, n = 0; for (const v of a) if (fin(v)) { s += v; n++; } return n ? s / n : nan; }
  function std(a, ddof = 0) {
    const m = mean(a); let s = 0, n = 0;
    for (const v of a) if (fin(v)) { s += (v - m) ** 2; n++; }
    return n - ddof > 0 ? Math.sqrt(s / (n - ddof)) : nan;
  }

  // ---------------------------------------------------------------- filters (zero phase)
  function butterBandSOS(order, f1, f2, fs) {
    // analog Butterworth prototype -> band-pass -> bilinear (like scipy.signal.butter(..., 'bandpass', output='sos'))
    const w1 = 2 * fs * Math.tan(Math.PI * f1 / fs), w2 = 2 * fs * Math.tan(Math.PI * f2 / fs);
    const bw = w2 - w1, w0sq = w1 * w2, K = 2 * fs;
    const poles = [];
    for (let k = 1; k <= order; k++) {
      const th = Math.PI * (2 * k + order - 1) / (2 * order);
      const pr = Math.cos(th) * bw / 2, pi = Math.sin(th) * bw / 2; // p*bw/2
      // sqrt((p bw/2)^2 - w0^2)
      const re = pr * pr - pi * pi - w0sq, im = 2 * pr * pi;
      const mag = Math.hypot(re, im), sr = Math.sqrt((mag + re) / 2), si = Math.sign(im || 1) * Math.sqrt((mag - re) / 2);
      for (const [a, b] of [[pr + sr, pi + si], [pr - sr, pi - si]]) {
        // bilinear z = (K + s) / (K - s)
        const dr = K - a, di = -b, nr = K + a, ni = b, d = dr * dr + di * di;
        poles.push([(nr * dr + ni * di) / d, (ni * dr - nr * di) / d]);
      }
    }
    const sos = poles.filter((p) => p[1] > 1e-12).map(([r, i]) => [1, 0, -1, -2 * r, r * r + i * i]);
    // unity gain at the geometric centre frequency
    const wc = 2 * Math.atan(Math.sqrt(w0sq) / K);
    let g = 1;
    for (const s of sos) g *= Math.hypot(...cplxResp(s, wc));
    sos[0] = sos[0].map((v, j) => (j < 3 ? v / g : v));
    return sos;
  }
  function cplxResp(s, w) {
    const c1 = Math.cos(w), s1 = -Math.sin(w), c2 = Math.cos(2 * w), s2 = -Math.sin(2 * w);
    const nr = s[0] + s[1] * c1 + s[2] * c2, ni = s[1] * s1 + s[2] * s2;
    const dr = 1 + s[3] * c1 + s[4] * c2, di = s[3] * s1 + s[4] * s2, d = dr * dr + di * di;
    return [(nr * dr + ni * di) / d, (ni * dr - nr * di) / d];
  }
  function notchSOS(f0, Q, fs) {
    const w0 = 2 * Math.PI * f0 / fs, bwr = w0 / Q, beta = Math.tan(bwr / 2), g = 1 / (1 + beta);
    return [[g, -2 * g * Math.cos(w0), g, -2 * g * Math.cos(w0), 2 * g - 1]];
  }
  function sosfilt(sos, x) {
    const y = Float64Array.from(x);
    for (const [b0, b1, b2, a1, a2] of sos) {
      let z1 = 0, z2 = 0;
      for (let n = 0; n < y.length; n++) {
        const xn = y[n], yn = b0 * xn + z1;
        z1 = b1 * xn - a1 * yn + z2; z2 = b2 * xn - a2 * yn; y[n] = yn;
      }
    }
    return y;
  }
  function filtfilt(sos, x, pad) {
    const n = x.length; pad = Math.min(pad, n - 1);
    if (pad < 1) return Float64Array.from(x);
    const ext = new Float64Array(n + 2 * pad);
    for (let i = 0; i < pad; i++) { ext[i] = 2 * x[0] - x[pad - i]; ext[n + pad + i] = 2 * x[n - 1] - x[n - 2 - i]; }
    ext.set(x, pad);
    let y = sosfilt(sos, ext); y.reverse(); y = sosfilt(sos, y); y.reverse();
    return y.subarray(pad, pad + n);
  }
  function filterEEG(x, fs, notch = 50) {
    let y = x;
    if (notch && notch < fs / 2) y = filtfilt(notchSOS(notch, 30, fs), y, Math.round(3 * fs));
    return Float64Array.from(filtfilt(butterBandSOS(4, 1, Math.min(40, 0.45 * fs), fs), y, Math.round(3 * fs)));
  }

  // ---------------------------------------------------------------- FFT (radix 2)
  const fftCache = {};
  function fftPlan(N) {
    if (fftCache[N]) return fftCache[N];
    const rev = new Uint32Array(N), bits = Math.log2(N);
    for (let i = 0; i < N; i++) { let r = 0; for (let b = 0; b < bits; b++) r |= ((i >> b) & 1) << (bits - 1 - b); rev[i] = r; }
    const cos = new Float64Array(N / 2), sin = new Float64Array(N / 2);
    for (let i = 0; i < N / 2; i++) { cos[i] = Math.cos(2 * Math.PI * i / N); sin[i] = -Math.sin(2 * Math.PI * i / N); }
    return (fftCache[N] = { rev, cos, sin });
  }
  function fft(re, im) {
    const N = re.length, { rev, cos, sin } = fftPlan(N);
    for (let i = 0; i < N; i++) { const j = rev[i]; if (j > i) { [re[i], re[j]] = [re[j], re[i]]; [im[i], im[j]] = [im[j], im[i]]; } }
    for (let size = 2; size <= N; size <<= 1) {
      const half = size >> 1, step = N / size;
      for (let s = 0; s < N; s += size) {
        for (let k = 0; k < half; k++) {
          const c = cos[k * step], si = sin[k * step], a = s + k, b = a + half;
          const tr = re[b] * c - im[b] * si, ti = re[b] * si + im[b] * c;
          re[b] = re[a] - tr; im[b] = im[a] - ti; re[a] += tr; im[a] += ti;
        }
      }
    }
  }

  // ---------------------------------------------------------------- spectra
  // Periodograms of 2 s Hann sub-segments (0.25 s hop); a 4 s window averages its clean ones.
  function subsegmentSpectra(t, xs, fs, segS = 2, hopS = 0.25) {
    const nch = xs.length, L = Math.round(segS * fs), hop = Math.max(1, Math.floor(hopS * fs + 1e-9)); // rounded down, as in Python
    const Lp = 1 << Math.ceil(Math.log2(L)), df = fs / Lp;
    const freqsAll = Array.from({ length: Lp / 2 + 1 }, (_, k) => k * df);
    const keepIdx = freqsAll.map((f, k) => (f >= 1 && f <= 40 ? k : -1)).filter((k) => k >= 0);
    const nf = keepIdx.length;
    const n = xs[0].length >= L ? Math.floor((xs[0].length - L) / hop) + 1 : 0;
    const win = Float64Array.from({ length: L }, (_, i) => 0.5 - 0.5 * Math.cos(2 * Math.PI * i / (L - 1)));
    const scale = 1 / (fs * win.reduce((a, v) => a + v * v, 0));
    const bandIdx = BAND_NAMES.map((b) => freqsAll.map((f, k) => (f >= BANDS[b][0] && f < BANDS[b][1] ? k : -1)).filter((k) => k >= 0));
    const totIdx = freqsAll.map((f, k) => (f >= 1 && f < 40 ? k : -1)).filter((k) => k >= 0);
    const psd = new Float32Array(n * nch * nf), total = new Float64Array(n * nch);
    const power = Object.fromEntries(BAND_NAMES.map((b) => [b, new Float64Array(n * nch)]));
    const maxAbs = new Float64Array(n * nch), sd = new Float64Array(n * nch), t0 = new Float64Array(n);
    const re = new Float64Array(Lp), im = new Float64Array(Lp), p = new Float64Array(Lp / 2 + 1);
    for (let s = 0; s < n; s++) {
      const a = s * hop; t0[s] = t[a];
      for (let c = 0; c < nch; c++) {
        const x = xs[c]; let m = 0, mx = 0;
        for (let i = 0; i < L; i++) { const v = x[a + i]; m += v; if (Math.abs(v) > mx) mx = Math.abs(v); }
        m /= L; let vv = 0;
        re.fill(0); im.fill(0);
        for (let i = 0; i < L; i++) { const d = x[a + i] - m; vv += d * d; re[i] = d * win[i]; }
        const q = s * nch + c; maxAbs[q] = mx; sd[q] = Math.sqrt(vv / L);
        fft(re, im);
        for (let k = 0; k <= Lp / 2; k++) p[k] = (re[k] * re[k] + im[k] * im[k]) * scale * (k === 0 || k === Lp / 2 ? 1 : 2);
        for (let j = 0; j < nf; j++) psd[q * nf + j] = p[keepIdx[j]];
        bandIdx.forEach((idx, bi) => { let sum = 0; for (const k of idx) sum += p[k]; power[BAND_NAMES[bi]][q] = sum * df; });
        let tot = 0; for (const k of totIdx) tot += p[k]; total[q] = tot * df;
      }
    }
    return { t0, n, nch, nf, psd, freqs: keepIdx.map((k) => freqsAll[k]), power, total, maxAbs, sd, segS, hopS: hop / fs };
  }
  function windowSpectra(sub, art = 100, flat = 0.5, winS = 4, stepS = 2) {
    const { n, nch } = sub, clean = new Uint8Array(n * nch);
    for (let q = 0; q < n * nch; q++) clean[q] = sub.maxAbs[q] <= art && sub.sd[q] >= flat ? 1 : 0;
    const perWin = Math.round((winS - sub.segS) / sub.hopS) + 1, stride = Math.round(stepS / sub.hopS);
    const nwin = n >= perWin ? Math.floor((n - perWin) / stride) + 1 : 0;
    const cum = (vals) => { // cumulative sums per channel over sub-segments of clean values
      const c = new Float64Array((n + 1) * nch);
      for (let s = 0; s < n; s++) for (let ch = 0; ch < nch; ch++) {
        const q = s * nch + ch; c[(s + 1) * nch + ch] = c[s * nch + ch] + (clean[q] ? (vals ? vals[q] : 1) : 0);
      }
      return c;
    };
    const cc = cum(null), cp = Object.fromEntries(BAND_NAMES.map((b) => [b, cum(sub.power[b])])), ct = cum(sub.total);
    const power = Object.fromEntries(BAND_NAMES.map((b) => [b, new Float64Array(nwin * nch)]));
    const total = new Float64Array(nwin * nch), cnt = new Float64Array(nwin * nch), bad = new Uint8Array(nwin * nch);
    const tStart = new Float64Array(nwin), tMid = new Float64Array(nwin);
    for (let w = 0; w < nwin; w++) {
      const i0 = w * stride, i1 = i0 + perWin;
      tStart[w] = sub.t0[i0]; tMid[w] = tStart[w] + winS / 2;
      for (let ch = 0; ch < nch; ch++) {
        const q = w * nch + ch, k = cc[i1 * nch + ch] - cc[i0 * nch + ch];
        cnt[q] = k; bad[q] = k < 1 ? 1 : 0;
        for (const b of BAND_NAMES) power[b][q] = k ? (cp[b][i1 * nch + ch] - cp[b][i0 * nch + ch]) / k : nan;
        total[q] = k ? (ct[i1 * nch + ch] - ct[i0 * nch + ch]) / k : nan;
      }
    }
    return { nwin, nch, tStart, tMid, power, total, cnt, bad, clean, winS, stepS };
  }

  // ---------------------------------------------------------------- montage
  const MUSE_CH = ['TP9', 'AF7', 'AF8', 'TP10'];
  const MUSE_POS = { AF7: [-0.5, 0.48], AF8: [0.5, 0.48], TP9: [-0.82, -0.2], TP10: [0.82, -0.2] };
  const ROWS = { FP: [90, 0], AF: [67.5, 0], F: [45, 0], FC: [22.5, 0], FT: [null, 0], C: [0, 0], T: [null, 0], CP: [22.5, 180],
    TP: [null, 180], P: [45, 180], PO: [67.5, 180], O: [90, 180], I: [112.5, 180] };
  const EQ_AZ = { FP: 18, AF: 36, F: 54, FT: 72, FC: 72, C: 90, T: 90, CP: 108, TP: 108, P: 126, PO: 144, O: 162, I: 162 };
  const OLD = { T3: 'T7', T4: 'T8', T5: 'P7', T6: 'P8' };
  const LABEL_RE = /^(FP|AF|FC|FT|CP|TP|PO|F|C|T|P|O|I)(Z|\d{1,2})$/;
  const REGIONS = { Frontal: ['FP', 'AF', 'F'], Sentral: ['FC', 'C', 'CP'], Temporal: ['FT', 'T', 'TP'], Parietal: ['P'], Oksipital: ['PO', 'O', 'I'] };
  const FRONTAL_PAIRS = [['F3', 'F4'], ['AF7', 'AF8'], ['AF3', 'AF4'], ['Fp1', 'Fp2'], ['F7', 'F8'], ['F1', 'F2']];
  const MUSE_SOURCES = {
    TP9: [['TP9'], ['T7', 'P7'], ['TP7'], ['T7'], ['P7']],
    AF7: [['AF7'], ['Fp1', 'F7'], ['AF3'], ['Fp1'], ['F7']],
    AF8: [['AF8'], ['Fp2', 'F8'], ['AF4'], ['Fp2'], ['F8']],
    TP10: [['TP10'], ['T8', 'P8'], ['TP8'], ['T8'], ['P8']],
  };
  function canonical(label) {
    let s = String(label).trim().toUpperCase().replace(/\s/g, '');
    if (s.startsWith('EEG')) s = s.slice(3);
    s = s.replace(/^[:_-]+/, '');
    const parts = s.split(/[-/:]/);
    if (!parts[0]) return null;
    if (parts.length > 1 && LABEL_RE.test(OLD[parts[1]] || parts[1])) return null; // bipolar
    const head = OLD[parts[0]] || parts[0], m = head.match(LABEL_RE);
    if (!m) return null;
    return (m[1] === 'FP' ? 'Fp' : m[1]) + (m[2] === 'Z' ? 'z' : m[2]);
  }
  function position(name) {
    const m = name.toUpperCase().match(LABEL_RE); if (!m) return null;
    const row = m[1], col = m[2];
    let k = col === 'Z' ? 0 : Math.floor((+col + 1) / 2);
    const side = col === 'Z' ? 0 : (+col % 2 ? -1 : 1);
    let [thMid, azMid] = ROWS[row]; const azEq = EQ_AZ[row];
    if (['FP', 'O', 'I'].includes(row) && k >= 1) k = 4;
    if (['T', 'FT', 'TP'].includes(row)) { thMid = 90; k = Math.max(k, 4); }
    let r, az;
    if (k <= 4) {
      const f = k / 4, rMid = thMid / 90 * 0.92;
      if (row === 'C') { r = f * 0.92; az = azEq; } else { r = rMid + (0.92 - rMid) * f; az = azMid + (azEq - azMid) * f; }
    } else { r = 112.5 / 90 * 0.92; az = azEq; }
    r = Math.min(r, 0.97);
    const a = az * Math.PI / 180 * (side || 1);
    return [+(r * Math.sin(a)).toFixed(4), +(r * Math.cos(a)).toFixed(4)];
  }
  function positions(ch) {
    if (ch.every((c) => MUSE_CH.includes(c))) return Object.fromEntries(ch.map((c) => [c, MUSE_POS[c]]));
    const out = {}; for (const c of ch) { const p = position(c); if (p) out[c] = p; } return out;
  }
  function frontalPair(ch) {
    const have = Object.fromEntries(ch.map((c) => [c.toUpperCase(), c]));
    for (const [a, b] of FRONTAL_PAIRS) if (have[a.toUpperCase()] && have[b.toUpperCase()]) return [have[a.toUpperCase()], have[b.toUpperCase()]];
    return null;
  }
  function regions(ch) {
    const out = {};
    for (const c of ch) {
      const m = c.toUpperCase().match(LABEL_RE); if (!m) continue;
      const reg = Object.keys(REGIONS).find((r) => REGIONS[r].includes(m[1]));
      if (reg) (out[reg] = out[reg] || []).push(c);
    }
    return out;
  }
  function museSources(ch) {
    const have = Object.fromEntries(ch.map((c) => [c.toUpperCase(), c]));
    const out = {};
    for (const [m, opts] of Object.entries(MUSE_SOURCES)) {
      const pick = opts.find((o) => o.every((c) => have[c.toUpperCase()]));
      if (!pick) return null;
      out[m] = pick.map((c) => have[c.toUpperCase()]);
    }
    return out;
  }
  const museRef = (ch) => ch.find((c) => c.toUpperCase() === 'FPZ') || null;
  const museEquivalent = (ch) => { const s = museSources(ch); return s ? Object.fromEntries(Object.entries(s).map(([m, c]) => [m, c.join('+')])) : null; };

  // ---------------------------------------------------------------- heart
  function findPeaks(x, { distance = 1, prominence = null, height = null } = {}) {
    let pk = [];
    for (let i = 1; i < x.length - 1;) {
      if (x[i - 1] < x[i]) {
        let j = i + 1; while (j < x.length - 1 && x[j] === x[i]) j++;
        if (x[j] < x[i]) pk.push((i + j - 1) >> 1);
        i = j;
      } else i++;
    }
    if (height !== null) pk = pk.filter((p) => x[p] >= height);
    if (distance > 1 && pk.length) {
      const keep = new Uint8Array(pk.length).fill(1);
      const order = pk.map((_, i) => i).sort((a, b) => x[pk[a]] - x[pk[b]] || a - b).reverse();
      for (const i of order) {
        if (!keep[i]) continue;
        for (let k = i - 1; k >= 0 && pk[i] - pk[k] < distance; k--) keep[k] = 0;
        for (let k = i + 1; k < pk.length && pk[k] - pk[i] < distance; k++) keep[k] = 0;
      }
      pk = pk.filter((_, i) => keep[i]);
    }
    if (prominence !== null) {
      pk = pk.filter((p) => {
        let lmin = x[p], rmin = x[p];
        for (let i = p - 1; i >= 0 && x[i] <= x[p]; i--) if (x[i] < lmin) lmin = x[i];
        for (let i = p + 1; i < x.length && x[i] <= x[p]; i++) if (x[i] < rmin) rmin = x[i];
        return x[p] - Math.max(lmin, rmin) >= prominence;
      });
    }
    return pk;
  }
  const IBI_MIN = 60 / 180, IBI_MAX = 60 / 35;
  function ppgBeats(sig, t, fs) {
    if (sig.length < 4 * fs) return [];
    const md = median(sig), x = filtfilt(butterBandSOS(2, 0.5, 3.5, fs), sig.map((v) => v - md), Math.round(3 * fs));
    const blk = Math.round(10 * fs), amps = [];
    for (let i = 0; i + blk <= x.length; i += blk) { const s = x.subarray(i, i + blk); amps.push(percentile(s, 95) - percentile(s, 5)); }
    if (!amps.length) amps.push(percentile(x, 95) - percentile(x, 5));
    const prom = 0.3 * median(amps);
    if (!(prom > 0)) return [];
    return findPeaks(x, { distance: Math.max(1, Math.round(IBI_MIN * fs)), prominence: prom }).map((p) => t[p]);
  }
  function ecgBeats(sig, t, fs) {
    if (sig.length < 4 * fs || fs < 50) return [];
    const md = median(sig), y = filtfilt(butterBandSOS(2, 5, Math.min(25, 0.45 * fs), fs), sig.map((v) => v - md), Math.round(3 * fs));
    const w = Math.max(1, Math.round(0.08 * fs)), e = new Float64Array(y.length);
    let acc = 0; const sq = y.map((v) => v * v);
    const h = (w - 1) >> 1; // centred moving average, as numpy.convolve(..., mode='same')
    for (let i = 0; i < y.length + h; i++) {
      if (i < y.length) acc += sq[i];
      if (i - w >= 0) acc -= sq[i - w];
      const c = i - h; if (c >= 0 && c < y.length) e[c] = acc / w;
    }
    const blk = Math.round(10 * fs), lv = [];
    for (let i = 0; i + blk <= e.length; i += blk) lv.push(percentile(e.subarray(i, i + blk), 98));
    if (!lv.length) lv.push(percentile(e, 98));
    const pk = findPeaks(e, { distance: Math.max(1, Math.round(IBI_MIN * fs)), height: 0.3 * median(lv) });
    const r = Math.max(1, Math.round(0.06 * fs)), out = new Set();
    for (const p of pk) {
      let best = Math.max(0, p - r);
      for (let i = Math.max(0, p - r); i <= Math.min(y.length - 1, p + r); i++) if (Math.abs(y[i]) > Math.abs(y[best])) best = i;
      out.add(best);
    }
    return [...out].sort((a, b) => a - b).map((i) => t[i]);
  }
  function cleanIbi(tb, ibi = null) {
    let t;
    if (ibi === null) { ibi = tb.slice(1).map((v, i) => v - tb[i]); t = tb.slice(1); } else t = tb;
    if (!ibi.length) return { t: [], ibi: [], valid: [] };
    const ok = ibi.map((v) => v >= IBI_MIN && v <= IBI_MAX);
    const good = ibi.filter((_, i) => ok[i]);
    const fillv = good.length ? median(good) : 1;
    const ref = ibi.map((v, i) => (ok[i] ? v : fillv));
    const med = ref.map((_, i) => median(ref.slice(Math.max(0, i - 3), i + 4).concat(
      Array(Math.max(0, 3 - i)).fill(ref[0]), Array(Math.max(0, i + 4 - ref.length)).fill(ref[ref.length - 1]))));
    return { t, ibi, valid: ibi.map((v, i) => ok[i] && Math.abs(v - med[i]) <= 0.25 * med[i]) };
  }
  function hrvStats(ser, t0 = null, t1 = null) {
    const m = ser.t.map((t) => (t0 === null || t >= t0) && (t1 === null || t < t1));
    const nAll = m.filter(Boolean).length, good = m.map((v, i) => v && ser.valid[i]);
    const x = ser.ibi.filter((_, i) => good[i]), d = [];
    for (let i = 1; i < good.length; i++) if (good[i] && good[i - 1]) d.push(ser.ibi[i] - ser.ibi[i - 1]);
    const out = { n: x.length, n_total: nAll, valid_frac: nAll ? x.length / nAll : null, hr: null, sdnn: null, rmssd: null, pnn50: null, ok: false };
    if (x.length >= 8) {
      Object.assign(out, {
        hr: 60 / mean(x), sdnn: std(x, 1) * 1000,
        rmssd: d.length >= 5 ? Math.sqrt(mean(d.map((v) => v * v))) * 1000 : null,
        pnn50: d.length >= 5 ? (d.filter((v) => Math.abs(v) > 0.05).length / d.length) * 100 : null, ok: true,
      });
    }
    return out;
  }
  function hrAt(ser, centers, half) {
    const t = ser.t.filter((_, i) => ser.valid[i]), ibi = ser.ibi.filter((_, i) => ser.valid[i]);
    return Array.from(centers, (c) => {
      let s = 0, n = 0; for (let i = 0; i < t.length; i++) if (t[i] >= c - half && t[i] < c + half) { s += ibi[i]; n++; }
      return n ? 60 / (s / n) : nan;
    });
  }

  // ---------------------------------------------------------------- statistics
  function erfc(x) { // Numerical Recipes erfcc, |error| < 1.2e-7
    const z = Math.abs(x), t = 1 / (1 + 0.5 * z);
    const r = t * Math.exp(-z * z - 1.26551223 + t * (1.00002368 + t * (0.37409196 + t * (0.09678418 + t * (-0.18628806 +
      t * (0.27886807 + t * (-1.13520398 + t * (1.48851587 + t * (-0.82215223 + t * 0.17087277)))))))));
    return x >= 0 ? r : 2 - r;
  }
  function gammaincc(a, x) { // regularized upper incomplete gamma Q(a, x)
    if (x <= 0) return 1;
    const gln = lgamma(a);
    if (x < a + 1) { let sum = 1 / a, del = sum, ap = a; for (let i = 0; i < 500; i++) { ap++; del *= x / ap; sum += del; if (Math.abs(del) < Math.abs(sum) * 1e-14) break; } return 1 - sum * Math.exp(-x + a * Math.log(x) - gln); }
    let b = x + 1 - a, c = 1e300, d = 1 / b, h = d;
    for (let i = 1; i < 500; i++) { const an = -i * (i - a); b += 2; d = an * d + b; if (Math.abs(d) < 1e-300) d = 1e-300; c = b + an / c; if (Math.abs(c) < 1e-300) c = 1e-300; d = 1 / d; const del = d * c; h *= del; if (Math.abs(del - 1) < 1e-14) break; }
    return Math.exp(-x + a * Math.log(x) - gln) * h;
  }
  function lgamma(z) {
    const g = [76.18009172947146, -86.50532032941677, 24.01409824083091, -1.231739572450155, 0.1208650973866179e-2, -0.5395239384953e-5];
    let x = z, y = z, tmp = x + 5.5; tmp -= (x + 0.5) * Math.log(tmp); let ser = 1.000000000190015;
    for (const c of g) ser += c / ++y;
    return -tmp + Math.log(2.5066282746310005 * ser / x);
  }
  function ranks(values) { // average ranks + tie counts
    const idx = values.map((v, i) => [v, i]).sort((a, b) => a[0] - b[0]), r = new Array(values.length), ties = [];
    for (let i = 0; i < idx.length;) {
      let j = i; while (j + 1 < idx.length && idx[j + 1][0] === idx[i][0]) j++;
      const avg = (i + j) / 2 + 1; for (let k = i; k <= j; k++) r[idx[k][1]] = avg;
      if (j > i) ties.push(j - i + 1); i = j + 1;
    }
    return { r, ties };
  }
  function mwTest(a, b) {
    a = a.filter(fin); b = b.filter(fin);
    const n1 = a.length, n2 = b.length;
    if (n1 < 5 || n2 < 5) return [null, null];
    const { r, ties } = ranks(a.concat(b));
    const R1 = r.slice(0, n1).reduce((s, v) => s + v, 0), U1 = R1 - n1 * (n1 + 1) / 2, U2 = n1 * n2 - U1;
    let p;
    if ((n1 <= 8 || n2 <= 8) && !ties.length) { // exact distribution
      const f = uDist(n1, n2), tot = f.reduce((s, v) => s + v, 0), u = Math.round(U1);
      let le = 0, ge = 0; for (let k = 0; k < f.length; k++) { if (k <= u) le += f[k]; if (k >= u) ge += f[k]; }
      p = Math.min(1, 2 * Math.min(le, ge) / tot);
    } else {
      const n = n1 + n2, tc = ties.reduce((s, t) => s + t ** 3 - t, 0);
      const sd = Math.sqrt(n1 * n2 / 12 * ((n + 1) - tc / (n * (n - 1))));
      const z = (Math.max(U1, U2) - n1 * n2 / 2 - 0.5) / sd;
      p = sd > 0 ? Math.min(1, erfc(z / Math.SQRT2)) : 1;
    }
    return [p, 2 * U2 / (n1 * n2) - 1];
  }
  function uDist(n1, n2) { // number of arrangements giving each U (dynamic programming)
    let f = [[1]];
    const memo = new Map(), get = (m, n) => {
      const key = m + ',' + n; if (memo.has(key)) return memo.get(key);
      let res;
      if (m === 0 || n === 0) res = [1];
      else { const a = get(m - 1, n), b = get(m, n - 1); res = new Array(m * n + 1).fill(0); a.forEach((v, k) => { res[k + n] += v; }); b.forEach((v, k) => { res[k] += v; }); }
      memo.set(key, res); return res;
    };
    f = get(n1, n2); return f;
  }
  function kruskal(groups) {
    const all = groups.flat(), n = all.length, { r, ties } = ranks(all);
    let off = 0, H = 0;
    for (const g of groups) { const R = r.slice(off, off + g.length).reduce((s, v) => s + v, 0); H += R * R / g.length; off += g.length; }
    H = 12 / (n * (n + 1)) * H - 3 * (n + 1);
    const tc = 1 - ties.reduce((s, t) => s + t ** 3 - t, 0) / (n ** 3 - n);
    H /= tc || 1;
    return gammaincc((groups.length - 1) / 2, H / 2);
  }
  function holm(ps) {
    const idx = ps.map((p, i) => i).filter((i) => ps[i] !== null).sort((a, b) => ps[a] - ps[b]);
    const out = ps.map(() => null); let run = 0;
    idx.forEach((i, rank) => { run = Math.max(run, Math.min(1, (idx.length - rank) * ps[i])); out[i] = run; });
    return out;
  }
  const cliffWord = (d) => (d === null ? '-' : Math.abs(d) < 0.147 ? 'sangat kecil' : Math.abs(d) < 0.33 ? 'kecil' : Math.abs(d) < 0.474 ? 'sedang' : 'besar');

  // ---------------------------------------------------------------- analysis
  const LABELS = {
    REFERENCE: ['Acuan', 'Ruas pembanding. Kondisi ruas lain dihitung relatif terhadap ruas ini.'],
    CALM_RELAXED: ['Tenang', 'Otak lebih pelan, denyut tidak naik: nuansa istirahat.'],
    FOCUSED_ENGAGED: ['Fokus', 'Otak lebih siaga, denyut biasa: nuansa memperhatikan.'],
    ACTIVATED_HIGH_AROUSAL: ['Teraktivasi', 'Otak dan/atau denyut lebih kencang: nuansa terpacu.'],
    INDETERMINATE: ['Indeterminan', 'Perubahan terlalu kecil atau bercampur; tidak memilih tiga label lain.'],
    NO_DATA: ['Data kurang', 'Kurang dari 3 jendela EEG bersih pada pasangan frontal.'],
  };
  const DOMAIN = { LOW_AROUSAL: 'CALM_RELAXED', ENGAGEMENT: 'FOCUSED_ENGAGED', AROUSAL: 'ACTIVATED_HIGH_AROUSAL' };
  const SD_FLOOR = { alpha: 0.05, beta: 0.05, theta: 0.05, tb: 0.05, ab: 0.05, ta: 0.05, hr: 2 };
  const EMPTY = { t: [], ibi: [], valid: [] };

  function parseMarks(text, tmax) {
    const v = String(text).replace(/;/g, ',').split(',').map((s) => s.trim()).filter(Boolean).map(Number).filter((x) => fin(x) && x > 0 && x < tmax);
    return [0, ...[...new Set(v)].sort((a, b) => a - b), tmax];
  }
  function markerTitik(markers) {
    return [...new Set(markers.filter((m) => !String(m.label).startsWith('SYNC') && m.t > 0).map((m) => Math.round(m.t).toFixed(0)))].join(', ');
  }

  class Session {
    constructor(rec) {
      this.rec = rec;
      this.ch = [...rec.channels]; this.allCh = [...rec.channels]; this.nch = this.ch.length; this.fs = rec.fs;
      this.t = rec.t; this.x = rec.x; this.tmax = rec.t[rec.t.length - 1];
      this.sub = subsegmentSpectra(this.t, this.x, this.fs);
      this.specs = {};
      this.grid = this.spec(100);
      this.ppg = rec.ppg ? cleanIbi(ppgBeats(rec.ppg.v, rec.ppg.t, rec.ppg.fs)) : EMPTY;
      this.polar = rec.rr ? cleanIbi(Array.from(rec.rr.t), Array.from(rec.rr.ms, (v) => v / 1000)) : EMPTY;
      this.hasPolar = this.polar.valid.filter(Boolean).length >= 20;
      this.hasPpgData = this.ppg.t.length > 0; this.hasHeartData = this.polar.t.length > 0;
      this.chans = 'all'; this.heart = 'all'; this.pshift = 0; this.museMap = null; this.museRefCh = null; this.views = {};
      this.setupChannels();
    }
    setupChannels() {
      this.pair = frontalPair(this.ch);
      if (this.pair) {
        this.pairIdx = this.pair.map((c) => this.ch.indexOf(c));
        const muse = this.pair.includes('AF7') && this.pair.includes('AF8') && this.ch.every((c) => MUSE_CH.includes(c));
        this.pairLabel = muse ? 'AF' : `${this.pair[0]}/${this.pair[1]}`;
        this.mPair = muse ? 'AF' : `${this.pair[0]}+${this.pair[1]}`;
        this.mAsym = `Asimetri ${this.pairLabel}`;
      } else { this.pairIdx = this.ch.map((_, i) => i); this.pairLabel = 'semua kanal'; this.mPair = 'Rata-rata'; this.mAsym = null; }
      this.measures = [this.mPair, ...this.ch, ...(this.mAsym ? [this.mAsym] : [])];
      this.measureLabels = { [this.mPair]: this.mPair === 'AF' ? 'AF rata-rata' : this.pair ? `${this.mPair} rata-rata` : 'Rata-rata semua kanal' };
      if (this.mAsym) this.measureLabels[this.mAsym] = this.mAsym;
    }
    spec(art) {
      const key = Math.round(art * 10) / 10;
      if (!this.specs[key]) { if (Object.keys(this.specs).length > 6) this.specs = {}; this.specs[key] = windowSpectra(this.sub, key); }
      return this.specs[key];
    }
    view(chans, heart, pshift = 0) {
      chans = chans === 'muse4' ? 'muse4' : 'all'; heart = ['ppg', 'ecg', 'none'].includes(heart) ? heart : 'all';
      pshift = Math.round((+pshift || 0) * 1000) / 1000;
      if (chans === 'all' && heart === 'all' && !pshift) return this;
      const key = chans + '|' + heart + '|' + pshift;
      if (this.views[key]) return this.views[key];
      const v = Object.assign(Object.create(Session.prototype), this);
      v.views = {}; v.chans = chans; v.heart = heart;
      if (chans === 'muse4') {
        const src = museSources(this.ch);
        if (src && this.ch.length > 4) {
          const ref = museRef(this.ch), xs = MUSE_CH.map((m) => {
            const idx = src[m].map((c) => this.ch.indexOf(c)), out = new Float64Array(this.t.length);
            for (let i = 0; i < out.length; i++) { let s = 0; for (const j of idx) s += this.x[j][i]; out[i] = s / idx.length - (ref ? this.x[this.ch.indexOf(ref)][i] : 0); }
            return out;
          });
          v.museMap = Object.fromEntries(Object.entries(src).map(([m, c]) => [m, c.join('+')]));
          v.museRefCh = ref; v.ch = [...MUSE_CH]; v.nch = 4; v.x = xs;
          v.sub = subsegmentSpectra(this.t, xs, this.fs); v.specs = {}; v.grid = v.spec(100);
          v.setupChannels();
        }
      }
      if (pshift && this.polar.t.length) v.polar = { ...this.polar, t: this.polar.t.map((x) => x + pshift) }; // Polar clock correction
      v.pshift = pshift;
      if (heart === 'ppg' || heart === 'none') { v.polar = EMPTY; v.hasPolar = false; }
      if (heart === 'ecg' || heart === 'none') v.ppg = EMPTY;
      return (this.views[key] = v);
    }
    overview() {
      const r = this.rec, g = this.grid, ser = (s) => ({ t: arr(s.t, 6), ibi: arr(s.ibi.map((v) => v * 1000), 5), valid: s.valid.map(Boolean) });
      return {
        name: r.participant, note: r.condition, folder: r.id, label: r.label, kind: r.kind, fs: this.fs,
        start: r.start, duration: num(this.tmax, 6), channels: this.ch, positions: positions(this.ch), regions: regions(this.ch),
        pair: this.pair, pair_label: this.pairLabel, heart_name: r.heartName, chans: this.chans, heart: this.heart,
        pshift: this.pshift, polar_info: r.polarInfo || null,
        options: {
          n_all: this.allCh.length,
          muse4: this.allCh.length > 4 ? museEquivalent(this.allCh) : Object.fromEntries(this.allCh.map((c) => [c, c])),
          muse_ref: this.allCh.length > 4 ? museRef(this.allCh) : 'Fpz', ppg: this.hasPpgData, ecg: this.hasHeartData,
        },
        bands: BANDS, quality: r.quality, sync_offset_ms: fin(r.syncOffset) ? num(r.syncOffset * 1000) : null,
        markers: r.markers.map((m) => ({ t: num(m.t, 6), label: m.label })), marker_titik: markerTitik(r.markers),
        windows: { win_s: g.winS, t_start: arr(g.tStart, 6), t_mid: arr(g.tMid, 6) },
        ppg: ser(this.ppg), polar: this.polar.t.length ? ser(this.polar) : null,
        hrv: { ppg: hrvStats(this.ppg), polar: this.hasPolar ? hrvStats(this.polar) : null },
      };
    }
    signal(t0, t1, n) {
      const t = this.t; let i0 = lb(t, t0), i1 = lb(t, t1);
      i0 = Math.max(0, i0 - 1); i1 = Math.min(t.length, i1 + 1);
      n = Math.max(50, Math.min(Math.round(n), 5000));
      const len = i1 - i0;
      if (len <= 2 * n) return { kind: 'raw', t: arr(t.subarray(i0, i1), 7), y: this.x.map((x) => arr(x.subarray(i0, i1), 4)) };
      const size = Math.floor(len / n), tb = new Array(n);
      for (let b = 0; b < n; b++) { let s = 0; for (let i = 0; i < size; i++) s += t[i0 + b * size + i]; tb[b] = num(s / size, 7); }
      const lo = [], hi = [];
      for (const x of this.x) {
        const l = new Array(n), h = new Array(n);
        for (let b = 0; b < n; b++) { let mn = Infinity, mx = -Infinity; for (let i = 0; i < size; i++) { const v = x[i0 + b * size + i]; if (v < mn) mn = v; if (v > mx) mx = v; } l[b] = num(mn); h[b] = num(mx); }
        lo.push(l); hi.push(h);
      }
      return { kind: 'env', t: tb, lo, hi };
    }
    windowValues(spec, band, metric) {
      const p = spec.power[band]; if (metric !== 'rel') return p;
      return p.map((v, q) => 100 * v / spec.total[q]);
    }
    analyze(titik = '', band = 'alpha', metric = 'abs', ref = 0, art = 100) {
      if (!BANDS[band]) band = 'alpha'; metric = metric === 'rel' ? 'rel' : 'abs';
      const spec = this.spec(art), nch = this.nch, nw = spec.nwin;
      const edges = parseMarks(titik, this.tmax), nseg = edges.length - 1;
      ref = ref >= 0 && ref < nseg ? +ref : 0;
      const bad = (w, c) => spec.bad[w * nch + c] === 1;
      const vals = this.windowValues(spec, band, metric), val = (w, c) => vals[w * nch + c];
      const segOf = Array.from(spec.tMid, (t) => Math.min(nseg - 1, lbR(edges, t) - 1));
      const af = this.pairIdx, afClean = Array.from({ length: nw }, (_, w) => af.every((c) => !bad(w, c)));
      const mval = (w, c) => { const v = val(w, c); return metric === 'abs' ? (v > 0 ? Math.log10(v) : nan) : v; };
      const refMean = [], refSd = [];
      for (let c = 0; c < nch; c++) {
        const v = []; for (let w = 0; w < nw; w++) if (segOf[w] === ref && !bad(w, c) && fin(mval(w, c))) v.push(mval(w, c));
        refMean.push(v.length >= 3 ? median(v) : nan);
        refSd.push(v.length >= 3 ? Math.max(std(v, 1), metric === 'abs' ? 0.05 : 0.5) : nan);
      }
      const [feats, hrSource] = this.features(spec, afClean);
      const zref = {};
      for (const [k, v] of Object.entries(feats)) {
        const x = v.filter((_, w) => segOf[w] === ref).filter(fin);
        zref[k] = x.length >= 3 ? [median(x), Math.max(std(x, 1), SD_FLOOR[k])] : [nan, nan];
      }
      const segs = [];
      for (let i = 0; i < nseg; i++) {
        const a = edges[i], b = edges[i + 1], ws = [];
        for (let w = 0; w < nw; w++) if (segOf[w] === i) ws.push(w);
        const chVals = [], chZ = [], chClean = [];
        for (let c = 0; c < nch; c++) {
          const good = ws.filter((w) => !bad(w, c));
          chVals.push(median(good.map((w) => val(w, c))));
          chZ.push((median(good.map((w) => mval(w, c))) - refMean[c]) / refSd[c]);
          chClean.push(good.length);
        }
        let asym = nan;
        if (this.pair) { const l = chVals[af[0]], r = chVals[af[1]]; asym = fin(l) && fin(r) && l + r ? (r - l) / (r + l) : nan; }
        const nAf = ws.filter((w) => afClean[w]).length;
        const z = Object.fromEntries(Object.entries(feats).map(([k, v]) => [k, (median(ws.filter((w) => afClean[w]).map((w) => v[w])) - zref[k][0]) / zref[k][1]]));
        const [code, scores] = classify(z, nAf, i === ref);
        let name = '';
        for (const m of this.rec.markers) if (Math.abs(m.t - a) <= 1.5 && !String(m.label).startsWith('SYNC')) name = String(m.label);
        segs.push({
          i, t0: num(a, 6), t1: num(b, 6), name, n_win: ws.length, n_clean: chClean, n_pair: nAf,
          values: arr(chVals), z: arr(chZ, 3), asym: num(asym, 3),
          ppg: hrvStats(this.ppg, a, b), polar: this.hasPolar ? hrvStats(this.polar, a, b) : null,
          code, label: LABELS[code][0], arti: code === 'NO_DATA' ? `Kurang dari 3 jendela EEG bersih pada ${this.pairLabel}.` : LABELS[code][1],
          feat_z: Object.fromEntries(Object.entries(z).map(([k, v]) => [k, num(v, 3)])),
          scores: Object.fromEntries(Object.entries(scores).map(([k, v]) => [k, num(v, 3)])),
          psd: Array.from({ length: nch }, (_, c) => arr(this.meanPsd(spec, a, b, c))),
        });
      }
      const cleanFrac = Array.from({ length: nch }, (_, c) => { let s = 0; for (let q = 0; q < this.sub.n; q++) s += spec.clean[q * nch + c]; return this.sub.n ? s / this.sub.n : null; });
      const chArr = (a) => Array.from({ length: nch }, (_, c) => arr(Array.from({ length: nw }, (_, w) => a[w * nch + c])));
      return {
        band, metric, ref, art_uv: art, channels: this.ch, pair: this.pair, pair_label: this.pairLabel,
        measures: this.measures, measure_labels: this.measureLabels, unit: metric === 'rel' ? '%' : 'µV²',
        edges: arr(edges, 6),
        bad: Array.from({ length: nw }, (_, w) => Array.from({ length: nch }, (_, c) => (bad(w, c) ? '1' : '0')).join('')),
        clean_frac: arr(cleanFrac, 3),
        windows: { power: Object.fromEntries(BAND_NAMES.map((bn) => [bn, chArr(spec.power[bn])])), total: chArr(spec.total) },
        ref_mean: arr(refMean), ref_sd: arr(refSd), hr_source: hrSource, freqs: arr(this.sub.freqs, 4),
        segments: segs, tests: this.tests(spec, val, bad, segOf, nseg, edges),
      };
    }
    features(spec, afClean) {
      const nch = this.nch, idx = this.pairIdx, nw = spec.nwin;
      const lm = (b) => Array.from({ length: nw }, (_, w) => { let s = 0; for (const c of idx) s += spec.power[b][w * nch + c]; return afClean[w] ? Math.log10(s / idx.length) : nan; });
      const al = lm('alpha'), be = lm('beta'), th = lm('theta');
      let src = this.hasPolar ? 'polar' : 'ppg';
      const hr = hrAt(this.hasPolar ? this.polar : this.ppg, spec.tMid, spec.winS / 2);
      if (!hr.some(fin)) src = null;
      return [{ alpha: al, beta: be, theta: th, tb: th.map((v, i) => v - be[i]), ab: al.map((v, i) => v - be[i]), ta: th.map((v, i) => v - al[i]), hr }, src];
    }
    meanPsd(spec, a, b, c) {
      const { n, nch, nf, psd, t0, segS } = this.sub, out = new Float64Array(nf); let k = 0;
      for (let s = 0; s < n; s++) {
        const mid = t0[s] + segS / 2;
        if (mid >= a && mid < b && spec.clean[s * nch + c]) { for (let j = 0; j < nf; j++) out[j] += psd[(s * nch + c) * nf + j]; k++; }
      }
      return k ? out.map((v) => v / k) : out.fill(nan);
    }
    tests(spec, val, bad, segOf, nseg, edges) {
      const k = Math.max(1, Math.round(spec.winS / spec.stepS)), idx = this.pairIdx, nw = spec.nwin;
      const names = edges.slice(0, -1).map((a, i) => `${a.toFixed(0)}–${edges[i + 1].toFixed(0)} s`);
      const pairs = [], omnibus = [];
      for (const meas of this.measures) {
        const groups = Array.from({ length: nseg }, () => []);
        for (let w = 0; w < nw; w += k) {
          let v, ok;
          if (this.ch.includes(meas)) { const c = this.ch.indexOf(meas); v = val(w, c); ok = !bad(w, c); }
          else {
            ok = idx.every((c) => !bad(w, c));
            if (meas === this.mAsym) { const l = val(w, idx[0]), r = val(w, idx[1]); v = (r - l) / (r + l); }
            else v = idx.reduce((s, c) => s + val(w, c), 0) / idx.length;
          }
          if (ok && fin(v)) groups[segOf[w]].push(v);
        }
        const rows = [];
        for (let i = 0; i < nseg - 1; i++) for (let j = i + 1; j < nseg; j++) {
          const [p, d] = mwTest(groups[i], groups[j]);
          rows.push({ measure: meas, a: i, b: j, pair: `${names[i]} vs ${names[j]}`, n_a: groups[i].length, n_b: groups[j].length,
            med_a: num(median(groups[i])), med_b: num(median(groups[j])), p, delta: num(d, 3), effect: cliffWord(d) });
        }
        holm(rows.map((r) => r.p)).forEach((ph, i) => { const r = rows[i]; r.p_holm = num(ph, 3); r.p = num(r.p, 3); r.sig = ph !== null && ph < 0.05; });
        pairs.push(...rows);
        const good = groups.filter((g) => g.length >= 5);
        if (nseg >= 3 && good.length >= 3) omnibus.push({ measure: meas, p: num(kruskal(good), 3), k: good.length });
      }
      return { pairs, omnibus, n_step: k };
    }
  }
  function classify(z, nAf, isRef) {
    const zz = (k) => (k in z ? z[k] : nan), nm = (a) => mean(a);
    const any = Object.values(z).some(fin);
    const dom = any ? { AROUSAL: nm([zz('beta'), zz('ab'), -zz('tb'), zz('hr')]), ENGAGEMENT: nm([zz('beta'), zz('alpha'), -zz('ta')]), LOW_AROUSAL: nm([zz('alpha'), zz('tb'), -zz('hr')]) }
      : { AROUSAL: nan, ENGAGEMENT: nan, LOW_AROUSAL: nan };
    if (isRef) return ['REFERENCE', dom];
    if (nAf < 3 || !Object.values(dom).every(fin)) return ['NO_DATA', dom];
    const rk = Object.entries(dom).sort((a, b) => b[1] - a[1]);
    if (rk[0][1] < 0.5 || rk[0][1] - rk[1][1] < 0.25) return ['INDETERMINATE', dom];
    return [DOMAIN[rk[0][0]], dom];
  }
  function lb(a, x) { let lo = 0, hi = a.length; while (lo < hi) { const m = (lo + hi) >> 1; if (a[m] < x) lo = m + 1; else hi = m; } return lo; }
  function lbR(a, x) { let lo = 0, hi = a.length; while (lo < hi) { const m = (lo + hi) >> 1; if (a[m] <= x) lo = m + 1; else hi = m; } return lo; }

  // ---------------------------------------------------------------- readers
  const UNIT = { UV: 1, 'µV': 1, 'ΜV': 1, MICROV: 1, MV: 1000, V: 1e6, NV: 1e-3 };
  function readEDF(buf, name) {
    const dv = new DataView(buf), dec = new TextDecoder('latin1'), txt = (o, n) => dec.decode(new Uint8Array(buf, o, n)).trim();
    const bdf = dv.getUint8(0) === 0xff, ns = parseInt(txt(252, 4), 10);
    if (!(ns > 0 && ns < 1024)) throw new Error(`${name}: bukan file EDF`);
    const f = (off, w) => Array.from({ length: ns }, (_, i) => txt(256 + off * ns + i * w, w));
    const labels = f(0, 16), o = 96, dims = f(o, 8), pmin = f(o + 8, 8).map(Number), pmax = f(o + 16, 8).map(Number);
    const dmin = f(o + 24, 8).map(Number), dmax = f(o + 32, 8).map(Number), nsamp = f(o + 120, 8).map((v) => parseInt(v, 10));
    const hb = parseInt(txt(184, 8), 10), recS = parseFloat(txt(244, 8)) || 1, bps = bdf ? 3 : 2;
    const recSamp = nsamp.reduce((a, b) => a + b, 0), recBytes = recSamp * bps;
    let nrec = Math.floor((buf.byteLength - hb) / recBytes); const hdrN = parseInt(txt(236, 8), 10); if (hdrN > 0) nrec = Math.min(nrec, hdrN);
    let start = null;
    try { const [dd, mm, yy] = txt(168, 8).split('.').map(Number), [H, M, S] = txt(176, 8).split('.').map(Number); start = `${yy < 85 ? 2000 + yy : 1900 + yy}-${String(mm).padStart(2, '0')}-${String(dd).padStart(2, '0')}T${String(H).padStart(2, '0')}:${String(M).padStart(2, '0')}:${String(S).padStart(2, '0')}`; if (start.includes('NaN')) start = null; } catch { start = null; }
    const sig = {}, ann = [];
    const offs = []; let acc = 0; for (const n of nsamp) { offs.push(acc); acc += n; }
    labels.forEach((lab, i) => {
      const n = nsamp[i], isAnn = /^(EDF|BDF) ANNOTATION/i.test(lab.replace('+', ''));
      if (isAnn) {
        const bytes = [];
        for (let r = 0; r < nrec; r++) { const base = hb + r * recBytes + offs[i] * bps; for (let k = 0; k < n * bps; k++) bytes.push(dv.getUint8(base + k)); }
        parseTAL(new Uint8Array(bytes), ann); return;
      }
      const g = (pmax[i] - pmin[i]) / ((dmax[i] - dmin[i]) || 1), out = new Float64Array(n * nrec);
      for (let r = 0; r < nrec; r++) {
        const base = hb + r * recBytes + offs[i] * bps;
        for (let k = 0; k < n; k++) {
          let d;
          if (bdf) { const p = base + 3 * k; d = dv.getUint8(p) | (dv.getUint8(p + 1) << 8) | (dv.getUint8(p + 2) << 16); if (d >= 1 << 23) d -= 1 << 24; }
          else d = dv.getInt16(base + 2 * k, true);
          out[r * n + k] = (d - dmin[i]) * g + pmin[i];
        }
      }
      sig[lab] = { fs: n / recS, v: out, dim: dims[i] };
    });
    const uniq = new Map(); for (const a of ann) uniq.set(a.t + '|' + a.label, a);
    return { labels, sig, ann: [...uniq.values()].sort((a, b) => a.t - b.t), start, patient: txt(8, 80), recording: txt(88, 80) };
  }
  function parseTAL(bytes, out) {
    const s = new TextDecoder('utf-8').decode(bytes);
    for (const tal of s.split('\x00')) {
      if (!tal || !'+-'.includes(tal[0])) continue;
      const parts = tal.split('\x14'), t = parseFloat(parts[0].split('\x15')[0]);
      if (!fin(t)) continue;
      for (const txt of parts.slice(1)) if (txt.trim()) out.push({ t, label: txt.trim() });
    }
  }
  function edfPatient(field) {
    const p = field.split(/\s+/);
    if (p.length >= 4 && ['M', 'F', 'X'].includes(p[1])) { const n = p.slice(3).join(' ').replace(/_/g, ' '); return n === 'X' ? '' : n; }
    return ['X', ''].includes(field) ? '' : field;
  }
  function resample(v, f, fs) { // linear interpolation to fs (only when a channel has another rate)
    const n = Math.floor(v.length * fs / f), out = new Float64Array(n);
    for (let i = 0; i < n; i++) { const p = i * f / fs, j = Math.floor(p), a = p - j; out[i] = j + 1 < v.length ? v[j] * (1 - a) + v[j + 1] * a : v[v.length - 1]; }
    return out;
  }
  function recordingFromEDF(buf, name, id) {
    const d = readEDF(buf, name), eeg = {}; let ecg = null, ppg = null;
    for (const [lab, s] of Object.entries(d.sig)) {
      const c = canonical(lab), up = lab.toUpperCase();
      if (c && !eeg[c]) eeg[c] = { fs: s.fs, v: s.v.map((x) => x * (UNIT[s.dim.replace(/\s/g, '').toUpperCase()] || 1)) };
      else if (!ecg && (up.includes('ECG') || up.includes('EKG'))) ecg = s;
      else if (!ppg && (up.includes('PPG') || up.includes('PLETH'))) ppg = s;
    }
    if (!Object.keys(eeg).length) for (const [lab, s] of Object.entries(d.sig)) {
      const dim = s.dim.replace(/\s/g, '').toUpperCase();
      if (['UV', 'µV', 'ΜV', 'MV', 'V'].includes(dim)) eeg[lab.trim()] = { fs: s.fs, v: s.v.map((x) => x * (UNIT[dim] || 1)) };
    }
    const chans = Object.keys(eeg);
    if (!chans.length) throw new Error(`${name}: tidak ada kanal EEG`);
    const rates = chans.map((c) => eeg[c].fs), fs = rates.sort((a, b) => rates.filter((r) => r === b).length - rates.filter((r) => r === a).length)[0];
    const cols = chans.map((c) => (eeg[c].fs === fs ? eeg[c].v : resample(eeg[c].v, eeg[c].fs, fs)));
    const n = Math.min(...cols.map((c) => c.length));
    const t = Float64Array.from({ length: n }, (_, i) => i / fs);
    let rr = null;
    if (ecg) {
      const et = Float64Array.from({ length: ecg.v.length }, (_, i) => i / ecg.fs), tb = ecgBeats(ecg.v, et, ecg.fs);
      if (tb.length > 1) rr = { t: Float64Array.from(tb.slice(1)), ms: Float64Array.from(tb.slice(1).map((v, i) => (v - tb[i]) * 1000)) };
    }
    return {
      id, kind: 'edf', label: name, participant: edfPatient(d.patient) || name.replace(/\.[^.]+$/, ''), condition: '',
      start: d.start, channels: chans, fs, t, x: cols.map((c) => filterEEG(c.subarray(0, n), fs)),
      ppg: ppg ? { t: Float64Array.from({ length: ppg.v.length }, (_, i) => i / ppg.fs), v: ppg.v, fs: ppg.fs } : null,
      rr, heartName: 'EKG (EDF)', markers: d.ann, syncOffset: null,
      quality: { eeg: { status: 'VALID', rate_hz: fs }, ppg: { status: ppg ? 'VALID' : '-', rate_hz: ppg ? ppg.fs : null } },
      nChannels: chans.length, duration: n / fs, hasPpg: !!ppg, hasHeart: !!ecg,
      absStart: d.start ? Date.parse(d.start) / 1000 : null, // EDF start is local clock time
    };
  }
  function parseCSV(text) {
    const lines = text.split(/\r?\n/).filter((l) => l.length), head = splitCSV(lines[0]);
    return { head, rows: lines.slice(1).map(splitCSV) };
  }
  function splitCSV(line) {
    if (!line.includes('"')) return line.split(',');
    const out = []; let cur = '', q = false;
    for (let i = 0; i < line.length; i++) {
      const ch = line[i];
      if (q) { if (ch === '"') { if (line[i + 1] === '"') { cur += '"'; i++; } else q = false; } else cur += ch; }
      else if (ch === '"') q = true; else if (ch === ',') { out.push(cur); cur = ''; } else cur += ch;
    }
    out.push(cur); return out;
  }
  function columns(csv, names) {
    const idx = names.map((n) => csv.head.indexOf(n));
    const cols = names.map(() => []);
    for (const r of csv.rows) {
      const v = idx.map((i) => parseFloat(r[i]));
      if (v.every(fin)) v.forEach((x, k) => cols[k].push(x));
    }
    return cols.map((c) => Float64Array.from(c));
  }
  function quality(ts, nominal) {
    if (ts.length < 2 || ts[ts.length - 1] <= ts[0]) return { status: '-', rate_hz: null };
    const rate = (ts.length - 1) / (ts[ts.length - 1] - ts[0]), r = rate / nominal;
    return { status: r >= 0.9 ? 'VALID' : r >= 0.5 ? 'WARNING' : 'INVALID', rate_hz: +rate.toFixed(2) };
  }
  async function recordingFromMusepolar(files, folder, id) { // files: {name: File|Blob-like with .text()}
    const text = async (n) => (files[n] ? files[n].text() : null);
    const meta = JSON.parse((await text('session.json')) || '{}');
    const [ts, ...eeg] = columns(parseCSV(await text('muse_eeg.csv')), ['timestamp', ...MUSE_CH]);
    const t0 = ts[0], t = ts.map((v) => v - t0);
    let ppg = null, rr = null, markers = [], pq = { status: '-', rate_hz: null };
    const ppgTxt = await text('muse_ppg.csv');
    if (ppgTxt) { const [pt, ir] = columns(parseCSV(ppgTxt), ['timestamp', 'ir']); if (pt.length) { ppg = { t: pt.map((v) => v - t0), v: ir, fs: 64 }; pq = quality(pt, 64); } }
    const good = (meta.sync || []).filter((s) => s.ok && s.muse_minus_polar_s !== null && s.muse_minus_polar_s !== undefined);
    const off = good.length ? good[0].muse_minus_polar_s : null;
    const rrTxt = await text('polar_rr.csv');
    if (rrTxt) { const [rt, ms] = columns(parseCSV(rrTxt), ['timestamp', 'rr_ms']); rr = { t: rt.map((v) => v + (off || 0) - t0), ms }; }
    const mk = await text('marker.csv');
    if (mk) { const c = parseCSV(mk), it = c.head.indexOf('timestamp'), il = c.head.indexOf('label'); markers = c.rows.map((r) => ({ t: parseFloat(r[it]) - t0, label: r[il] })).filter((m) => fin(m.t)); }
    return {
      id, kind: 'musepolar', label: folder, participant: meta.name || folder, condition: meta.note || '', start: meta.start_local || null,
      channels: [...MUSE_CH], fs: 256, t, x: eeg.map((c) => filterEEG(c, 256)), ppg, rr, heartName: 'Polar RR', markers, syncOffset: off,
      quality: { eeg: quality(ts, 256), ppg: pq }, nChannels: 4, duration: t[t.length - 1], hasPpg: !!ppg, hasHeart: !!rr,
      absStart: t0,
    };
  }

  // ---------------------------------------------------------------- other EEG CSV files
  // Same rules as src/muse2_pipeline/csvload.py: Mind Monitor, muselsl, earlier app (EEG_raw.csv),
  // OpenBCI GUI, or any CSV with a time column and 10-20 named channels.
  const TIME_NAMES = ['timestamp', 'timestamps', 'timestamp_lsl', 'time', 'time_s', 'time (s)', 't', 'timestamp (s)'];
  const MARKER_NAMES = ['marker', 'markers', 'label', 'event', 'events', 'annotation', 'annotations', 'elements'];
  const IGNORED_ELEMENTS = ['/muse/elements/blink', '/muse/elements/jaw_clench', '/muse/elements/touching_forehead', '/muse/elements/horseshoe', '/muse/elements/is_good'];
  const STANDARD_RATES = [128, 200, 250, 256, 500, 512, 1000, 1024, 2048];
  const eegName = (col) => canonical(col.trim().replace(/^(RAW|EEG)[_ ]/i, ''));
  const rawChannel = (col) => /^(EXG\s*Channel\s*\d+|CH(ANNEL)?[\s_]*\d+|EEG[\s_]*\d+)$/i.test(col.trim());
  function estimateRate(t) {
    const r = (t.length - 1) / (t[t.length - 1] - t[0]);
    const near = STANDARD_RATES.reduce((a, b) => (Math.abs(b - r) < Math.abs(a - r) ? b : a));
    return Math.abs(near - r) <= 0.03 * near ? near : Math.round(r);
  }
  function splitHeader(text) {
    const lines = text.split(/\r?\n/); let i = 0;
    while (i < lines.length && (lines[i].startsWith('%') || lines[i].startsWith('#') || !lines[i].trim())) i++;
    return [lines.slice(0, i), lines.slice(i)];
  }
  function detectSep(line) { return [',', ';', '\t'].reduce((a, b) => (line.split(b).length > line.split(a).length ? b : a)); }
  function splitSep(line, sep) { return sep === ',' ? splitCSV(line) : line.split(sep); }
  function numericUnit(name, t) { // same order as csvload.numeric_unit: name, epoch size, plausible rate
    const n = name.toLowerCase();
    if (/(^|[^a-z])ms([^a-z]|$)|millis/.test(n)) return 1000;
    if (/\(s\)|_s$|\bsec/.test(n)) return 1;
    const f = t.filter(fin);
    if (f.length < 2) return 1;
    const big = Math.max(...f.map(Math.abs));
    if (big > 1e11) return 1000;
    if (big > 1e8) return 1;
    const span = f[f.length - 1] - f[0];
    if (span <= 0) return 1;
    const rs = (f.length - 1) / span;
    return rs < 50 && rs * 1000 >= 100 && rs * 1000 <= 5000 ? 1000 : 1;
  }
  function toSeconds(vals, name = '') {
    const nums = vals.map((v) => (v.trim() === '' ? NaN : Number(v)));
    if (nums.filter(fin).length > 0.9 * vals.length) {
      const u = numericUnit(name, nums);
      return { t: nums.map((v) => v / u), start: null };
    }
    const ms = vals.map((v) => { const s = v.trim(); return s ? Date.parse(s.replace(' ', 'T')) : NaN; });
    if (ms.filter(fin).length > 0.9 * vals.length) {
      const i0 = ms.findIndex(fin);
      return { t: ms.map((v) => (v - ms[i0]) / 1000), start: vals[i0].trim().replace(' ', 'T').slice(0, 19), epoch0: ms[i0] / 1000 };
    }
    return null;
  }
  function recordingFromCSV(text, name, id, opt = {}) {
    const [comments, lines] = splitHeader(text);
    const body = lines.filter((l) => l.length);
    if (body.length < 2) throw new Error('file CSV kosong');
    const sep = detectSep(body[0]), cols = splitSep(body[0], sep).map((c) => c.trim().replace(/^"|"$/g, ''));
    const rows = body.slice(1).map((l) => splitSep(l, sep));
    let rate = null;
    for (const c of comments) { const m = c.match(/sample\s*rate\s*[=:]\s*([\d.]+)/i); if (m) { rate = parseFloat(m[1]); break; } }
    const low = cols.map((c) => c.toLowerCase());
    let ti = TIME_NAMES.map((n) => low.indexOf(n)).find((i) => i >= 0);
    if (ti === undefined) ti = low.findIndex((c) => c.includes('timestamp') || c.startsWith('time'));
    const eeg = []; const seen = new Set();
    cols.forEach((c, i) => { const n = eegName(c); if (n && !seen.has(n)) { seen.add(n); eeg.push([n, i]); } });
    if (!eeg.length) cols.forEach((c, i) => { if (rawChannel(c)) eeg.push([c.trim(), i]); });
    if (!eeg.length) throw new Error(`${name}: tidak ada kolom EEG (nama 10-20 seperti TP9/AF7/Fp1, RAW_TP9, EEG_TP9 atau EXG Channel)`);
    const mi = MARKER_NAMES.map((n) => low.indexOf(n)).find((i) => i >= 0);
    const ei = cols.findIndex((c) => /ECG|EKG/i.test(c)), pi = cols.findIndex((c) => /PPG|PLETH/i.test(c));
    const time = ti >= 0 ? toSeconds(rows.map((r) => r[ti] || ''), cols[ti]) : null;
    const markers = [];
    if (mi !== undefined && time) rows.forEach((r, k) => {
      const lab = (r[mi] || '').trim().replace(/^"|"$/g, '');
      if (lab && lab.toLowerCase() !== 'nan' && fin(time.t[k]) && !IGNORED_ELEMENTS.some((p) => lab.toLowerCase().startsWith(p))) markers.push({ t: time.t[k], label: lab });
    });
    const keep = [];
    rows.forEach((r, k) => { if (eeg.every(([, i]) => r[i] !== undefined && r[i].trim() !== '' && fin(Number(r[i])))) keep.push(k); });
    if (keep.length < 10) throw new Error(`${name}: terlalu sedikit baris EEG`);
    const t = time ? keep.map((k) => time.t[k]) : null;
    let fs = rate;
    if (!fs) fs = t && t.length > 2 && t[t.length - 1] > t[0] ? estimateRate(t) : 256;
    if (fs < 100) throw new Error(`${name}: frekuensi sampel ${fs} Hz terlalu rendah untuk analisis EEG (minimal 100 Hz); rekam dengan data mentah (mis. Mind Monitor: Recording Interval = Constant)`);
    const n = keep.length, t0 = t ? t[0] : 0;
    const x = eeg.map(([, i]) => Float64Array.from(keep, (k) => Number(rows[k][i])));
    let quality = { status: 'VALID', rate_hz: fs };
    if (t && n > 2 && t[n - 1] > t[0]) {
      const r = (n - 1) / (t[n - 1] - t[0]), ratio = r / fs;
      quality = { status: ratio >= 0.9 ? 'VALID' : ratio >= 0.5 ? 'WARNING' : 'INVALID', rate_hz: +r.toFixed(2) };
    }
    const tt = Float64Array.from({ length: n }, (_, i) => i / fs);
    let ppg = opt.ppg || null, rr = null;
    if (!ppg && pi >= 0) {
      const v = [], pt = [];
      keep.forEach((k, j) => { const val = Number(rows[k][pi]); if (fin(val)) { v.push(val); pt.push(j / fs); } });
      if (v.length) ppg = { t: Float64Array.from(pt), v: Float64Array.from(v), fs };
    }
    if (ei >= 0) {
      const raw = keep.map((k) => Number(rows[k][ei])), good = raw.filter(fin), md = good.length ? median(good) : 0;
      const tb = ecgBeats(Float64Array.from(raw, (v) => (fin(v) ? v : md)), tt, fs);
      if (tb.length > 1) rr = { t: Float64Array.from(tb.slice(1)), ms: Float64Array.from(tb.slice(1).map((v, i) => (v - tb[i]) * 1000)) };
    }
    const meta = opt.meta || {};
    return {
      id, kind: opt.kind || 'csv', label: opt.label || name, participant: meta.name || name.replace(/\.[^.]+$/, ''), condition: meta.note || '',
      start: meta.start || (time && time.start) || null, channels: eeg.map(([c]) => c), fs, t: tt, x: x.map((c) => filterEEG(c, fs)),
      ppg, rr, heartName: 'EKG (CSV)', markers: markers.map((m) => ({ t: m.t - t0, label: m.label })), syncOffset: null,
      quality: { eeg: quality, ppg: { status: ppg ? 'VALID' : '-', rate_hz: ppg ? ppg.fs : null } },
      nChannels: eeg.length, duration: n / fs, hasPpg: !!ppg, hasHeart: !!rr,
      absStart: time && fin(time.epoch0) ? time.epoch0 + t0 : (t0 > 1e8 ? t0 : null),
    };
  }
  async function recordingFromLSL(files, dir, id) { // earlier app: EEG_raw.csv + PPG_raw.csv + metadata json
    const txt = await files['EEG_raw.csv'].text();
    let meta = {};
    for (const nm of ['recording_metadata.json', 'baseline_metadata.json']) if (files[nm]) { try { meta = JSON.parse(await files[nm].text()); } catch { meta = {}; } break; }
    const parts = dir.split('/'), part = parts.length > 1 ? parts[parts.length - 2] : parts[0], cond = parts[parts.length - 1];
    let ppg = null;
    if (files['PPG_raw.csv']) {
      const e = parseCSV(txt), p = parseCSV(await files['PPG_raw.csv'].text());
      const [te] = columns(e, ['Timestamp_LSL']), [tp, v2] = columns(p, ['Timestamp_LSL', 'PPG_2']);
      if (tp.length) { const origin = te.length ? te[0] : tp[0]; ppg = { t: tp.map((x) => x - origin), v: v2, fs: 64 }; }
    }
    return recordingFromCSV(txt, 'EEG_raw.csv', id, { kind: 'lsl', label: `${part} / ${cond}`, ppg,
      meta: { name: part, note: cond, start: meta.start_iso || null } });
  }

  // ---------------------------------------------------------------- Polar Sensor Logger (.txt)
  // Same rules as src/muse2_pipeline/polar.py: RR file used directly, ECG only when there is no RR,
  // MARKER file -> markers; joined to the EEG recording that overlaps it in clock time.
  const POLAR_SETS = [];
  const polarType = (name, header) => {
    const m = name.match(/_(RR|ECG|HR|ACC|PPI|MARKER)\.txt$/i); if (m) return m[1].toUpperCase();
    const h = header.toLowerCase();
    if (h.includes('rr-interval') || /\brr\b/.test(h)) return 'RR';
    if (h.includes('ecg')) return 'ECG';
    if (h.includes('marker')) return 'MARKER';
    return null;
  };
  const polarKey = (path) => path.replace(/_(RR|ECG|HR|ACC|PPI|MARKER)\.txt$/i, '');
  const localEpoch = (s) => Date.parse(s.trim().replace(' ', 'T')) / 1000;
  function polarRows(text) {
    const lines = text.split(/\r?\n/).filter((l) => l.trim());
    const sep = lines[0].split(';').length >= lines[0].split(',').length ? ';' : ',';
    return [lines[0].split(sep).map((c) => c.trim().toLowerCase()), lines.slice(1).map((l) => l.split(sep))];
  }
  function parsePolarRR(text) {
    const [head, rows] = polarRows(text), ti = head.indexOf('phone timestamp'), ri = head.findIndex((c) => c.includes('rr'));
    const ts = [], rr = [];
    for (const r of rows) { const a = localEpoch(r[ti] || ''), b = parseFloat(r[ri]); if (fin(a) && fin(b)) { ts.push(a); rr.push(b); } }
    const t = ts.slice();
    for (let i = t.length - 2; i >= 0; i--) if (ts[i] === ts[i + 1]) t[i] = t[i + 1] - rr[i + 1] / 1000;
    return { t, rr };
  }
  function parsePolarECG(text) {
    const [head, rows] = polarRows(text), ti = head.indexOf('phone timestamp');
    const si = head.findIndex((c) => c.includes('sensor timestamp')), vi = head.findIndex((c) => c.includes('ecg'));
    let t0 = null; const sens = [], v = [];
    for (const r of rows) {
      const a = localEpoch(r[ti] || ''), val = parseFloat(r[vi]);
      if (!fin(val) || (t0 === null && !fin(a))) continue;
      if (t0 === null) t0 = a;
      sens.push(si >= 0 ? parseFloat(r[si]) : NaN); v.push(val);
    }
    let t, fs = 130;
    if (si >= 0 && sens.every(fin) && sens.length > 1) {
      t = sens.map((x) => t0 + (x - sens[0]) / 1e9);
      if (t[t.length - 1] > t[0]) fs = (t.length - 1) / (t[t.length - 1] - t[0]);
    } else t = v.map((_, i) => t0 + i / fs);
    return { t: Float64Array.from(t), v: Float64Array.from(v), fs };
  }
  function parsePolarMarkers(text) {
    const [head, rows] = polarRows(text), ti = head.indexOf('phone timestamp'), out = [];
    for (const r of rows) { const a = localEpoch(r[ti] || ''); if (fin(a)) out.push({ t: a, label: r.filter((_, j) => j !== ti).join(';').trim() || 'marker' }); }
    return out;
  }
  function loadPolarSet(name, files) {
    let rr, source;
    if (files.RR) { const p = parsePolarRR(files.RR); rr = { t: p.t, ms: p.rr }; source = 'RR'; }
    else if (files.ECG) {
      const e = parsePolarECG(files.ECG), tb = ecgBeats(e.v, e.t, e.fs);
      if (tb.length < 2) return null;
      rr = { t: tb.slice(1), ms: tb.slice(1).map((v, i) => (v - tb[i]) * 1000) }; source = 'ECG';
    } else return null;
    if (rr.t.length < 2) return null;
    return { name, source, t: rr.t, ms: rr.ms, markers: files.MARKER ? parsePolarMarkers(files.MARKER) : [],
      tFirst: rr.t[0] - rr.ms[0] / 1000, tLast: rr.t[rr.t.length - 1] };
  }
  function bestPolar(sets, absStart, dur) {
    if (absStart === null || absStart === undefined || !sets.length) return null;
    let best = null, bov = 0;
    for (const s of sets) { const ov = Math.min(absStart + dur, s.tLast) - Math.max(absStart, s.tFirst); if (ov > bov) { best = s; bov = ov; } }
    return best;
  }
  function attachPolar(rec, sets) {
    let s = bestPolar(sets, rec.absStart, rec.duration), aligned = 'clock';
    if (!s && (rec.absStart === null || rec.absStart === undefined) && sets.length === 1) { s = sets[0]; aligned = 'start'; }
    if (!s) return false;
    const origin = aligned === 'clock' ? rec.absStart : s.tFirst;
    rec.rr = { t: Float64Array.from(s.t, (v) => v - origin), ms: Float64Array.from(s.ms) };
    rec.heartName = 'Polar H10'; rec.hasHeart = true;
    rec.markers = rec.markers.filter((m) => !String(m.label).startsWith('Polar: '))
      .concat(s.markers.map((m) => ({ t: m.t - origin, label: `Polar: ${m.label}` }))).sort((a, b) => a.t - b.t);
    rec.polarInfo = { name: s.name, source: s.source, aligned, start_diff_s: +(s.tFirst - origin).toFixed(3) };
    SESS.delete(rec.id);
    return true;
  }

  // ---------------------------------------------------------------- registry & requests
  const SESS = new Map(), RECS = [];
  let counter = 0;
  const yieldUI = () => new Promise((r) => setTimeout(r, 30));
  function sessionList() {
    return RECS.map((r) => ({ id: r.id, label: r.label, name: r.participant, note: r.condition, start: r.start, duration: r.duration,
      has_ppg: r.hasPpg, has_polar: r.hasHeart, kind: r.kind, n_channels: r.nChannels }))
      .sort((a, b) => String(b.start || '').localeCompare(String(a.start || '')) || b.label.localeCompare(a.label));
  }
  function addRecording(rec) { RECS.push(rec); }
  async function addFiles(fileList, currentId = null) {
    await yieldUI();
    const byDir = {}, edfs = [], zips = [], errors = [];
    const polarFiles = [];
    for (const f of fileList) {
      const path = f.webkitRelativePath || f.relPath || f.name, low = path.toLowerCase();
      if (low.endsWith('.txt') && /phone timestamp/i.test(f.slice ? await f.slice(0, 300).text() : (await f.text()).slice(0, 300))) { polarFiles.push([path, f]); continue; }
      if (low.endsWith('.edf') || low.endsWith('.bdf')) edfs.push(f);
      else if (low.endsWith('.zip')) zips.push(f);
      else { const dir = path.includes('/') ? path.slice(0, path.lastIndexOf('/')) : '.'; (byDir[dir] = byDir[dir] || {})[path.slice(path.lastIndexOf('/') + 1)] = f; }
    }
    for (const z of zips) {
      if (typeof JSZip === 'undefined') { errors.push(`${z.name}: membuka ZIP perlu koneksi internet (pustaka JSZip)`); continue; }
      const zip = await JSZip.loadAsync(await z.arrayBuffer());
      for (const [p, e] of Object.entries(zip.files)) {
        if (e.dir) continue;
        const low = p.toLowerCase(), wrap = { name: p.slice(p.lastIndexOf('/') + 1), relPath: p, text: () => e.async('string'), arrayBuffer: () => e.async('arraybuffer') };
        if (low.endsWith('.txt') && /phone timestamp/i.test((await wrap.text()).slice(0, 200))) polarFiles.push([p, wrap]);
        else if (low.endsWith('.edf') || low.endsWith('.bdf')) edfs.push(wrap);
        else { const dir = p.includes('/') ? p.slice(0, p.lastIndexOf('/')) : '.'; (byDir[dir] = byDir[dir] || {})[wrap.name] = wrap; }
      }
    }
    const groups = {}, newSets = [];
    for (const [path, f] of polarFiles) {
      const text = await f.text(), typ = polarType(path.split('/').pop(), text.split(/\r?\n/)[0]);
      if (['RR', 'ECG', 'MARKER'].includes(typ)) (groups[polarKey(path)] = groups[polarKey(path)] || {})[typ] = text;
    }
    for (const [key, files] of Object.entries(groups)) {
      const st = loadPolarSet(key.split('/').pop(), files);
      if (st) { POLAR_SETS.push(st); newSets.push(st); } else errors.push(`${key.split('/').pop()}: tidak ada interval RR/EKG yang terbaca`);
    }
    const added = [];
    for (const f of edfs) {
      try { const r = recordingFromEDF(await f.arrayBuffer(), f.name, `r${++counter}`); addRecording(r); added.push(r.id); }
      catch (e) { errors.push(`${f.name}: ${e.message}`); }
    }
    for (const [dir, files] of Object.entries(byDir)) {
      try {
        if (files['muse_eeg.csv']) {
          const r = await recordingFromMusepolar(files, dir.split('/').pop() || dir, `r${++counter}`); addRecording(r); added.push(r.id);
        } else if (files['EEG_raw.csv']) {
          const r = await recordingFromLSL(files, dir, `r${++counter}`); addRecording(r); added.push(r.id);
        } else {
          for (const [nm, f] of Object.entries(files)) { // stand-alone EEG CSV files (Mind Monitor, muselsl, OpenBCI, ...)
            if (!/\.(csv|txt)$/i.test(nm)) continue;
            try { const r = recordingFromCSV(await f.text(), nm, `r${++counter}`); addRecording(r); added.push(r.id); }
            catch (e) { if (!/tidak ada kolom EEG/.test(e.message)) errors.push(e.message); }
          }
        }
      } catch (e) { errors.push(`${dir}: ${e.message}`); }
    }
    // join Polar recordings to the EEG recordings they overlap in clock time
    const polarJoined = [];
    for (const id of added) {
      const rec = RECS.find((r) => r.id === id);
      // by clock among every Polar recording opened so far; without an EEG clock only a single pair chosen together
      const sets = rec.absStart !== null && rec.absStart !== undefined ? POLAR_SETS : (added.length === 1 ? newSets : []);
      if (rec.kind !== 'musepolar' && attachPolar(rec, sets)) polarJoined.push(id);
    }
    let attachedTo = null;
    if (!added.length && newSets.length && currentId) { // only Polar files chosen: join them to the open recording
      const rec = RECS.find((r) => r.id === currentId);
      if (rec && rec.kind !== 'musepolar' && attachPolar(rec, newSets)) attachedTo = rec.id;
      else if (rec && rec.kind === 'musepolar') errors.push('Sesi musepolar sudah punya data Polar sendiri.');
    }
    if (!added.length && !attachedTo) throw new Error(errors[0] || 'Tidak ada rekaman EEG (folder musepolar, file EDF/BDF, atau CSV dengan kolom EEG) di pilihan ini.');
    return { root: 'browser', exists: true, sessions: sessionList(), added, errors, attachedTo, polarJoined };
  }
  async function session(id) {
    if (SESS.has(id)) return SESS.get(id);
    const rec = RECS.find((r) => r.id === id);
    if (!rec) throw new Error('Sesi tidak ditemukan.');
    await yieldUI();
    const s = new Session(rec); SESS.set(id, s); return s;
  }
  async function handle(path) {
    const u = new URL(path, 'http://x'), q = Object.fromEntries(u.searchParams), parts = u.pathname.split('/').filter(Boolean);
    const kind = parts[1], id = parts[2];
    if (kind === 'sessions') return { root: 'browser', exists: true, sessions: sessionList() };
    const s = (await session(id)).view(q.chans || 'all', q.heart || 'all', +q.pshift || 0);
    if (kind === 'session') return s.overview();
    if (kind === 'signal') return s.signal(+q.t0 || 0, fin(+q.t1) ? +q.t1 : 1e9, +q.n || 1600);
    if (kind === 'analysis') { await yieldUI(); return s.analyze(q.titik || '', q.band || 'alpha', q.metric || 'abs', +q.ref || 0, +q.art || 100); }
    throw new Error('permintaan tidak dikenal: ' + path);
  }

  // ---------------------------------------------------------------- export (ZIP of CSV tables)
  const csvLine = (a) => a.map((v) => (v === null || v === undefined ? '' : typeof v === 'string' && /[",\n]/.test(v) ? `"${v.replace(/"/g, '""')}"` : v)).join(',');
  async function exportZip(id, q) {
    const s = (await session(id)).view(q.chans, q.heart, +q.pshift || 0);
    const res = s.analyze(q.titik, q.band, q.metric, +q.ref, +q.art), spec = s.spec(+q.art), ch = s.ch, nch = s.nch;
    const segHead = ['ruas', 'nama', 't0_s', 't1_s', 'jendela', `jendela_bersih_${res.pair_label}`,
      ...ch.flatMap((c) => [`${c}_${res.band}_${res.metric}`, `${c}_z_vs_acuan`, `${c}_jendela_bersih`]), `asimetri_${res.pair_label}`, 'kondisi',
      'ppg_hr_bpm', 'ppg_rmssd_ms', 'ppg_sdnn_ms', 'polar_hr_bpm', 'polar_rmssd_ms', 'polar_sdnn_ms'];
    const segRows = res.segments.map((g) => [`${g.t0.toFixed(0)}–${g.t1.toFixed(0)} s`, g.name, g.t0, g.t1, g.n_win, g.n_pair,
      ...ch.flatMap((_, c) => [g.values[c], g.z[c], g.n_clean[c]]), g.asym, g.label,
      g.ppg.hr, g.ppg.rmssd, g.ppg.sdnn, g.polar ? g.polar.hr : null, g.polar ? g.polar.rmssd : null, g.polar ? g.polar.sdnn : null]);
    const tHead = ['measure', 'pair', 'n_a', 'n_b', 'med_a', 'med_b', 'p', 'p_holm', 'delta', 'effect', 'sig'];
    const winHead = ['t_start_s', 't_mid_s', ...ch.flatMap((c) => [...BAND_NAMES.map((b) => `${c}_${b}_uV2`), `${c}_total_uV2`, `${c}_artefak`])];
    const winRows = Array.from({ length: spec.nwin }, (_, w) => [spec.tStart[w], spec.tMid[w],
      ...ch.flatMap((_, c) => [...BAND_NAMES.map((b) => spec.power[b][w * nch + c]), spec.total[w * nch + c], spec.bad[w * nch + c]])]);
    const files = {
      'ruas.csv': [segHead, ...segRows], 'uji_berpasangan.csv': [tHead, ...res.tests.pairs.map((r) => tHead.map((k) => r[k]))],
      'uji_kruskal.csv': [['measure', 'p', 'k'], ...res.tests.omnibus.map((o) => [o.measure, o.p, o.k])],
      'jendela_dayapita.csv': [winHead, ...winRows],
    };
    for (const [nm, ser] of [['denyut_ppg.csv', s.ppg], ['denyut_polar.csv', s.polar]])
      if (ser.t.length) files[nm] = [['t_s', 'ibi_ms', 'valid'], ...ser.t.map((t, i) => [t, ser.ibi[i] * 1000, ser.valid[i]])];
    const base = `${s.rec.label.replace(/\.[^.]+$/, '')}_${res.band}`;
    if (typeof JSZip === 'undefined') return { name: `${base}_ruas.csv`, blob: new Blob([files['ruas.csv'].map(csvLine).join('\n')], { type: 'text/csv' }) };
    const zip = new JSZip();
    for (const [nm, rows] of Object.entries(files)) zip.file(nm, rows.map(csvLine).join('\n'));
    zip.file('pengaturan.json', JSON.stringify({ sesi: s.rec.label, ...q }, null, 2));
    return { name: `${base}_analisis.zip`, blob: await zip.generateAsync({ type: 'blob' }) };
  }

  // Tab-separated tables for the clipboard (paste into Excel/Sheets) - used where downloads are blocked.
  async function exportText(id, q) {
    const s = (await session(id)).view(q.chans, q.heart, +q.pshift || 0);
    const res = s.analyze(q.titik, q.band, q.metric, +q.ref, +q.art), ch = s.ch;
    const f = (v) => (v === null || v === undefined ? '' : typeof v === 'number' ? String(+v.toPrecision(5)).replace('.', ',') : String(v));
    const rows = [[`Sesi: ${s.rec.participant}`, `Pita: ${res.band} (${res.unit})`, `Ruas acuan: ${res.ref + 1}`], [],
      ['Ruas', 'Nama', 'Jendela bersih', ...ch, `Asimetri ${res.pair_label}`, 'Denyut PPG', 'PRV-RMSSD', `Denyut ${s.rec.heartName}`, 'HRV-RMSSD', 'Kondisi'],
      ...res.segments.map((g) => [`${Math.round(g.t0)}–${Math.round(g.t1)} s`, g.name, `${g.n_pair}/${g.n_win}`, ...g.values, g.asym,
        g.ppg.hr, g.ppg.rmssd, g.polar ? g.polar.hr : null, g.polar ? g.polar.rmssd : null, g.label]), [],
      ['Ukuran', 'Perbandingan', 'n', 'Median 1', 'Median 2', 'p', 'p Holm', 'δ Cliff', 'Efek', 'Berbeda'],
      ...res.tests.pairs.map((r) => [res.measure_labels[r.measure] || r.measure, r.pair, `${r.n_a}/${r.n_b}`, r.med_a, r.med_b, r.p, r.p_holm, r.delta, r.effect, r.sig ? 'ya' : 'tidak'])];
    return rows.map((r) => r.map(f).join('\t')).join('\n');
  }

  // ---------------------------------------------------------------- demo data (synthetic)
  function demo() {
    let seed = 7; const rnd = () => { seed = (seed * 16807) % 2147483647; return seed / 2147483647; };
    const gauss = () => Math.sqrt(-2 * Math.log(rnd() + 1e-12)) * Math.cos(2 * Math.PI * rnd());
    const heart = (dur, hrOf) => { const b = [0.3]; while (b[b.length - 1] < dur + 1) { const t = b[b.length - 1]; b.push(t + 60 / hrOf(t) * (1 + 0.04 * Math.sin(2 * Math.PI * t / 5)) + 0.01 * gauss()); } return b; };
    const make = (id, kind, label, name, chans, fs, dur, gen, beats, extra) => {
      const n = Math.round(dur * fs), t = Float64Array.from({ length: n }, (_, i) => i / fs);
      const x = chans.map((c, k) => { let lp = 0; return filterEEG(Float64Array.from(t, (tt) => { lp = 0.97 * lp + gauss(); return 1.5 * lp + gen(c, k, tt) + 2 * gauss(); }), fs); });
      return { id, kind, label, participant: name, condition: extra.note, start: extra.start, channels: chans, fs, t, x,
        ppg: extra.ppg || null, rr: { t: Float64Array.from(beats.slice(1)), ms: Float64Array.from(beats.slice(1).map((v, i) => (v - beats[i]) * 1000)) },
        heartName: extra.heartName, markers: extra.markers, syncOffset: extra.sync ?? null,
        quality: { eeg: { status: 'VALID', rate_hz: fs }, ppg: { status: extra.ppg ? 'VALID' : '-', rate_hz: extra.ppg ? 64 : null } },
        nChannels: chans.length, duration: dur, hasPpg: !!extra.ppg, hasHeart: true };
    };
    const blinks = Array.from({ length: 60 }, () => rnd() * 240);
    const blink = (tt) => { let s = 0; for (const b of blinks) if (!(b > 80 && b < 160)) s += 180 * Math.exp(-((tt - b) ** 2) / (2 * 0.08 ** 2)); return s; };
    const b1 = heart(240, (t) => (t < 80 ? 68 : t < 160 ? 63 : 80));
    const tp = Float64Array.from({ length: 240 * 64 }, (_, i) => i / 64);
    const ph = (tt) => { let j = lb(b1, tt); j = Math.max(1, Math.min(b1.length - 1, j)); return j - 1 + (tt - b1[j - 1]) / (b1[j] - b1[j - 1]); };
    const ppgV = Float64Array.from(tp, (tt) => { const w = 2 * Math.PI * ph(tt); return 210000 - 2500 * (Math.sin(w) + 0.4 * Math.sin(2 * w + 1)) + 30 * gauss(); });
    const muse = make('demo-muse', 'musepolar', 'demo_muse_4kanal', 'Demo Muse (4 kanal)', MUSE_CH, 256, 240, (c, k, tt) => {
      const al = tt >= 80 && tt < 160 ? 12 : 4, be = tt >= 160 ? 5 : 2;
      return al * Math.sin(2 * Math.PI * (10 + 0.3 * k) * tt + k) + be * Math.sin(2 * Math.PI * 20 * tt) + (c.startsWith('AF') ? blink(tt) : 0);
    }, b1, { note: 'istirahat → mata tertutup → aritmetika', start: '2026-09-26T09:30:00', heartName: 'Polar RR', sync: 0.062,
      ppg: { t: tp, v: ppgV, fs: 64 }, markers: [{ t: 80.2, label: 'Mata tertutup' }, { t: 160.1, label: 'Hitung mundur (aritmetika)' }] });
    const cap = ['Fp1', 'Fp2', 'F3', 'F4', 'C3', 'C4', 'P3', 'P4', 'O1', 'O2', 'F7', 'F8', 'T7', 'T8', 'P7', 'P8'];
    const b2 = heart(180, (t) => (t < 60 ? 70 : t < 120 ? 62 : 82));
    const edf = make('demo-edf', 'edf', 'demo_16kanal.edf', 'Demo EDF (16 kanal)', cap, 250, 180, (c, k, tt) => {
      const post = 'OP'.includes(c[0]), al = tt >= 60 && tt < 120 ? (post ? 20 : 6) : post ? 5 : 3, be = tt >= 120 ? (c[0] === 'F' ? 5 : 2.5) : 2;
      return al * Math.sin(2 * Math.PI * (10 + 0.1 * k) * tt + k) + be * Math.sin(2 * Math.PI * 21 * tt + k) + (c.startsWith('Fp') ? blink(tt) * 0.8 : 0);
    }, b2, { note: '', start: '2026-09-26T10:00:00', heartName: 'EKG (EDF)', markers: [{ t: 60, label: 'Mata tertutup' }, { t: 120, label: 'Aritmetika' }] });
    return [muse, edf];
  }
  async function loadDemo() {
    await yieldUI();
    if (!RECS.some((r) => r.id.startsWith('demo'))) demo().forEach(addRecording);
    return { root: 'browser', exists: true, sessions: sessionList() };
  }

  return { handle, addFiles, exportZip, exportText, loadDemo, _internals: { butterBandSOS, notchSOS, filtfilt, filterEEG, subsegmentSpectra, windowSpectra,
    readEDF, recordingFromEDF, recordingFromCSV, estimateRate, loadPolarSet, attachPolar, Session, mwTest, kruskal, holm, findPeaks, ppgBeats, ecgBeats, cleanIbi, hrvStats, canonical, position, museSources } };
})();
if (typeof window !== 'undefined') window.ENGINE = ENGINE;
if (typeof module !== 'undefined') module.exports = ENGINE;
