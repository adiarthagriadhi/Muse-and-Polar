'use strict';
// CorVa Space standard protocol: guides the participant through the phases from /api/corva/protocol,
// writes a "CorVa: <phase>" marker at each phase start, paces slow breathing (visual + tones) and
// announces phase changes by voice so the eyes-closed blocks need no screen. After every phase the
// participant rates sleepiness (KSS) and relaxation 1-9; the answers are written as a marker
// "CorVa skala: <phase> KSS=.. rileks=..". Uses $, send and recording from app.js.
// Add ?protokol=cepat to the URL to run 30x faster (demo / testing).

const PV = { proto: null, run: null, timer: null, audio: null, breathTimer: null };
const PV_SPEED = new URLSearchParams(location.search).get('protokol') === 'cepat' ? 30 : 1;

function pvFmt(s) {
  s = Math.max(0, Math.ceil(s));
  return `${String(Math.floor(s / 60)).padStart(2, '0')}:${String(s % 60).padStart(2, '0')}`;
}

function pvSay(text) {
  if (!$('pvSound').checked || !window.speechSynthesis) return;
  try {
    speechSynthesis.cancel();
    const u = new SpeechSynthesisUtterance(text);
    u.lang = 'id-ID';
    speechSynthesis.speak(u);
  } catch (e) { /* speech is optional */ }
}

function pvTone(from, to, secs) {
  if (!$('pvSound').checked) return;
  try {
    PV.audio = PV.audio || new (window.AudioContext || window.webkitAudioContext)();
    const ctx = PV.audio, t = ctx.currentTime, o = ctx.createOscillator(), g = ctx.createGain();
    o.type = 'sine';
    o.frequency.setValueAtTime(from, t);
    o.frequency.linearRampToValueAtTime(to, t + secs);
    g.gain.setValueAtTime(0.0001, t);
    g.gain.exponentialRampToValueAtTime(0.08, t + 0.3);
    g.gain.setValueAtTime(0.08, t + secs - 0.4);
    g.gain.exponentialRampToValueAtTime(0.0001, t + secs);
    o.connect(g).connect(ctx.destination);
    o.start(t);
    o.stop(t + secs + 0.05);
  } catch (e) { /* audio is optional */ }
}

function pvStopBreathing() {
  clearInterval(PV.breathTimer);
  PV.breathTimer = null;
  $('pvPacer').hidden = true;
  $('pvBall').classList.remove('in');
}

function pvStartBreathing() {
  const half = 60 / PV.proto.slow_breaths_per_min / 2 / PV_SPEED;  // seconds in, seconds out
  $('pvPacer').hidden = false;
  $('pvBall').style.transitionDuration = `${half}s`;
  let inhale = true;
  const step = () => {
    $('pvBall').classList.toggle('in', inhale);
    $('pvBreath').textContent = inhale ? 'Tarik napas…' : 'Hembuskan…';
    pvTone(inhale ? 330 : 495, inhale ? 495 : 330, half);
    inhale = !inhale;
  };
  step();
  PV.breathTimer = setInterval(step, half * 1000);
}

function pvEnterPhase(i) {
  const r = PV.run, ph = PV.proto.phases[i];
  r.i = i;
  r.phaseStart = performance.now();
  r.phaseLen = ph.seconds / PV_SPEED;
  sendMarker(PV.proto.marker_prefix + ph.name);
  $('pvName').textContent = ph.name;
  $('pvStep').textContent = `fase ${i + 1}/${PV.proto.phases.length}`;
  $('pvOStep').textContent = `Fase ${i + 1} dari ${PV.proto.phases.length}`;
  $('pvOName').textContent = ph.name;
  $('pvOInstr').textContent = ph.instruction;
  const next = PV.proto.phases[i + 1];
  $('pvONext').textContent = next ? `Berikutnya: ${next.name}` : 'Fase terakhir';
  pvStopBreathing();
  pvSay(`${ph.name}. ${ph.instruction}`);
  if (ph.breathing === 'slow') setTimeout(() => { if (PV.run && PV.run.i === i) pvStartBreathing(); }, 4000 / PV_SPEED);
}

function pvTick() {
  const r = PV.run;
  if (!r) return;
  const ph = PV.proto.phases[r.i];
  const el = (performance.now() - r.phaseStart) / 1000;
  const left = r.phaseLen - el;
  if (r.rating) return;
  if (left <= 0) {
    pvRate(r.i);
    return;
  }
  const settle = ph.settle_s / PV_SPEED;
  $('pvTime').textContent = pvFmt(left * PV_SPEED);
  $('pvOTime').textContent = pvFmt(left * PV_SPEED);
  $('pvSettle').textContent = el < settle ? 'stabilisasi (tidak dianalisis)' : 'jendela analisis';
  const done = PV.proto.phases.slice(0, r.i).reduce((a, p) => a + p.seconds, 0) + el * PV_SPEED;
  $('pvBar').style.width = `${(100 * done / PV.proto.total_seconds).toFixed(1)}%`;
}

// ---- subjective ratings after a phase (D-22)
function pvAdvance() {
  const r = PV.run;
  if (!r) return;
  if (r.i + 1 < PV.proto.phases.length) pvEnterPhase(r.i + 1); else pvFinish(true);
}

function pvRate(i) {
  const r = PV.run, ph = PV.proto.phases[i], scales = PV.proto.scales || [];
  if (!scales.length) { pvAdvance(); return; }
  r.rating = { phase: ph.id, values: {}, deadline: performance.now() + PV.proto.rating_timeout_s * 1000 / PV_SPEED };
  pvStopBreathing();
  $('pvOverlay').hidden = false;  // the participant answers on this screen
  $('pvOName').textContent = 'Penilaian singkat';
  $('pvOInstr').textContent = `Tentang fase tadi: ${ph.name}. Pilih angka 1 sampai 9.`;
  $('pvOTime').hidden = true;
  $('pvSettle').textContent = 'menunggu penilaian peserta';
  $('pvRateRows').innerHTML = scales.map((sc) => {
    const lab = sc.labels || {}, keys = Object.keys(lab).map(Number);
    const lo = lab[Math.min(...keys)] || '', hi = lab[Math.max(...keys)] || '';
    const btns = Array.from({ length: 9 }, (_, k) => `<button type="button" data-s="${sc.id}" data-v="${k + 1}" aria-pressed="false">${k + 1}</button>`).join('');
    return `<div class="pv-q"><b>${sc.question}</b><div class="pv-scale" role="group" aria-label="${sc.question}">${btns}</div>`
      + `<div class="pv-anchors"><span>1 = ${lo}</span><span>9 = ${hi}</span></div><div class="pv-chosen" id="pvChosen-${sc.id}"></div></div>`;
  }).join('');
  $('pvRate').hidden = false;
  pvSay(ph.eyes === 'closed' ? 'Silakan buka mata. Nilai fase tadi.' : 'Nilai fase tadi.');
  r.ratingTimer = setInterval(() => {
    if (!PV.run || !PV.run.rating) return;
    const left = (PV.run.rating.deadline - performance.now()) / 1000;
    $('pvRateLeft').textContent = `dilewati otomatis dalam ${Math.ceil(left * PV_SPEED)} s`;
    if (left <= 0) pvRateDone();
  }, 250);
}

function pvRateDone() {
  const r = PV.run;
  if (!r || !r.rating) return;
  clearInterval(r.ratingTimer);
  const v = r.rating.values, scales = (PV.proto.scales || []).map((s) => s.id).filter((k) => v[k]);
  const label = PV.proto.scale_prefix + r.rating.phase + (scales.length ? scales.map((k) => ` ${k}=${v[k]}`).join('') : ' dilewati');
  sendMarker(label);
  r.rating = null;
  $('pvRate').hidden = true;
  $('pvOTime').hidden = false;
  pvAdvance();
}

$('pvRateRows').addEventListener('click', (e) => {
  const b = e.target.closest('button[data-s]');
  const r = PV.run;
  if (!b || !r || !r.rating) return;
  const sc = (PV.proto.scales || []).find((s) => s.id === b.dataset.s);
  r.rating.values[b.dataset.s] = +b.dataset.v;
  b.parentElement.querySelectorAll('button').forEach((x) => x.setAttribute('aria-pressed', String(x === b)));
  const labels = (sc && sc.labels) || {};
  $(`pvChosen-${b.dataset.s}`).textContent = labels[b.dataset.v] ? `${b.dataset.v} = ${labels[b.dataset.v]}` : '';
  if ((PV.proto.scales || []).every((s) => r.rating.values[s.id])) setTimeout(pvRateDone, 600);
});
$('pvRateSkip').addEventListener('click', () => { if (PV.run && PV.run.rating) { PV.run.rating.values = {}; pvRateDone(); } });

function pvStart() {
  if (!PV.proto || PV.run) return;
  if (PV.audio === null && $('pvSound').checked) pvTone(440, 440, 0.15);  // unlock audio on this click
  const startedRecording = !(recording && recording.active);
  if (startedRecording) send({ cmd: 'record_start', name: $('sessionName').value || 'CorVa' });
  PV.run = { i: 0, startedRecording };
  $('pvIdle').hidden = true;
  $('pvRun').hidden = false;
  $('pvOverlay').hidden = false;
  // give the recorder a moment to open its files so the first marker lands in the session
  setTimeout(() => {
    if (!PV.run) return;
    pvEnterPhase(0);
    PV.timer = setInterval(pvTick, 250);
  }, startedRecording ? 600 : 0);
}

function pvFinish(completed) {
  if (!PV.run) return;
  clearInterval(PV.timer);
  clearInterval(PV.run.ratingTimer);
  $('pvRate').hidden = true;
  $('pvOTime').hidden = false;
  pvStopBreathing();
  sendMarker(PV.proto.marker_prefix + (completed ? 'selesai' : 'dihentikan'));
  pvSay(completed ? 'Protokol selesai. Terima kasih.' : 'Protokol dihentikan.');
  if (PV.run.startedRecording) setTimeout(() => send({ cmd: 'record_stop' }), 800);
  PV.run = null;
  $('pvRun').hidden = true;
  $('pvIdle').hidden = false;
  $('pvOverlay').hidden = true;
  $('pvBar').style.width = '0';
}

fetch('/api/corva/protocol').then((r) => r.json()).then((p) => {
  PV.proto = p;
  $('pvTotal').textContent = `${p.phases.length} fase · ${Math.round(p.total_seconds / 60)} menit${PV_SPEED > 1 ? ' (mode cepat)' : ''}`;
}).catch(() => { $('pvStart').disabled = true; $('pvStart').title = 'Protokol tidak tersedia'; });

$('pvStart').addEventListener('click', pvStart);
$('pvStop').addEventListener('click', () => { if (confirm('Hentikan protokol?')) pvFinish(false); });
$('pvSkip').addEventListener('click', () => {
  if (!PV.run) return;
  if (PV.run.rating) { PV.run.rating.values = {}; pvRateDone(); return; }  // skipping the rating moves on
  pvAdvance();
});
$('pvScreen').addEventListener('click', () => { $('pvOverlay').hidden = false; });
$('pvClose').addEventListener('click', () => { $('pvOverlay').hidden = true; });
