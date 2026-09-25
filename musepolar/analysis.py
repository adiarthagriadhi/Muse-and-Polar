"""Live metrics: EEG band powers / signal quality and HRV from RR intervals."""

from __future__ import annotations

from collections import deque

import numpy as np

BANDS = {"delta": (1, 4), "theta": (4, 8), "alpha": (8, 13), "beta": (13, 30), "gamma": (30, 45)}
CHANNELS = ["TP9", "AF7", "AF8", "TP10"]


class EegBands:
    def __init__(self, rate: int = 256, window_sec: float = 2.0, n_channels: int = 4):
        self.rate = rate
        self.size = int(rate * window_sec)
        self.buf = np.zeros((n_channels, self.size))
        self.filled = 0

    def reset(self) -> None:
        self.buf[:] = 0
        self.filled = 0

    def add(self, rows: list[list[float]]) -> None:
        arr = np.asarray(rows, dtype=float).T  # (channels, n)
        n = arr.shape[1]
        if n >= self.size:
            self.buf[:] = arr[:, -self.size:]
        else:
            self.buf = np.roll(self.buf, -n, axis=1)
            self.buf[:, -n:] = arr
        self.filled = min(self.size, self.filled + n)

    def compute(self) -> dict | None:
        if self.filled < self.size:
            return None
        x = self.buf - self.buf.mean(axis=1, keepdims=True)
        # noise estimate on the last second (after removing slow drift)
        last = x[:, -self.rate:]
        t = np.arange(last.shape[1])
        trend = np.polynomial.polynomial.polyfit(t, last.T, 1)
        detr = last - (trend[0][:, None] + trend[1][:, None] * t)
        noise = detr.std(axis=1)

        win = np.hanning(self.size)
        spec = np.abs(np.fft.rfft(x * win, axis=1)) ** 2
        freqs = np.fft.rfftfreq(self.size, 1.0 / self.rate)
        absolute = {}
        for band, (lo, hi) in BANDS.items():
            mask = (freqs >= lo) & (freqs < hi)
            absolute[band] = spec[:, mask].sum(axis=1)
        total = sum(absolute.values()) + 1e-12
        relative = {b: absolute[b] / total for b in BANDS}
        return {
            "relative": {b: float(relative[b].mean()) for b in BANDS},
            "per_channel": {ch: {b: float(relative[b][i]) for b in BANDS} for i, ch in enumerate(CHANNELS)},
            "noise_uV": {ch: float(noise[i]) for i, ch in enumerate(CHANNELS)},
        }


class Hrv:
    """Time-domain HRV over a sliding window of RR intervals."""

    def __init__(self, window_sec: float = 60.0):
        self.window = window_sec
        self.rr: deque[tuple[float, float]] = deque()

    def reset(self) -> None:
        self.rr.clear()

    def add(self, t: float, rr_ms: float) -> None:
        if 250 <= rr_ms <= 2500:  # physiologically plausible
            self.rr.append((t, rr_ms))
        while self.rr and self.rr[0][0] < t - self.window:
            self.rr.popleft()

    def compute(self) -> dict | None:
        if len(self.rr) < 5:
            return None
        rr = np.array([v for _, v in self.rr])
        diff = np.diff(rr)
        return {
            "n": int(len(rr)),
            "window_sec": self.window,
            "mean_rr": float(rr.mean()),
            "mean_hr": float(60000.0 / rr.mean()),
            "sdnn": float(rr.std(ddof=1)),
            "rmssd": float(np.sqrt(np.mean(diff ** 2))),
            "pnn50": float(np.mean(np.abs(diff) > 50) * 100),
        }


# -- cross-device synchronisation ------------------------------------------

def _movement_envelope(t: np.ndarray, xyz: np.ndarray, grid: np.ndarray, fs: float, smooth: float) -> np.ndarray:
    """|acceleration magnitude - rest level|, resampled onto ``grid`` and smoothed."""
    mag = np.linalg.norm(xyz, axis=1)
    dev = np.abs(mag - np.median(mag))
    y = np.interp(grid, t, dev, left=0.0, right=0.0)
    k = max(1, int(round(smooth * fs)))
    return np.convolve(y, np.ones(k) / k, mode="same")


def _count_events(env: np.ndarray, fs: float, min_g: float = 0.15, refractory: float = 0.4) -> int:
    thr = max(min_g, 0.4 * float(env.max()))
    above = np.flatnonzero(env > thr)
    if above.size == 0:
        return 0
    return int(1 + np.sum(np.diff(above) > refractory * fs))


def estimate_offset(
    a_t, a_xyz, b_t, b_xyz, fs: float = 500.0, max_lag: float = 1.0, smooth: float = 0.04
) -> dict:
    """Time offset between two accelerometers that felt the same movements (taps/jumps).

    Returns ``offset_s`` = how much later the same event appears in stream *a*
    than in stream *b* (on the shared host clock).  To align: ``t_b + offset_s``.
    """
    a_t, b_t = np.asarray(a_t, float), np.asarray(b_t, float)
    a_xyz, b_xyz = np.asarray(a_xyz, float), np.asarray(b_xyz, float)
    if len(a_t) < 20 or len(b_t) < 20:
        return {"ok": False, "reason": "data akselerometer tidak cukup"}
    t0, t1 = max(a_t[0], b_t[0]), min(a_t[-1], b_t[-1])
    if t1 - t0 < 2.0:
        return {"ok": False, "reason": "rentang data yang tumpang-tindih kurang dari 2 detik"}
    grid = np.arange(t0, t1, 1.0 / fs)
    a = _movement_envelope(a_t, a_xyz, grid, fs, smooth)
    b = _movement_envelope(b_t, b_xyz, grid, fs, smooth)
    events_a, events_b = _count_events(a, fs), _count_events(b, fs)
    a0, b0 = a - a.mean(), b - b.mean()
    denom = float(np.linalg.norm(a0) * np.linalg.norm(b0))
    if denom == 0:
        return {"ok": False, "reason": "tidak ada gerakan terdeteksi", "events_a": events_a, "events_b": events_b}
    n = len(grid)
    L = min(int(max_lag * fs), n - 1)
    full = np.correlate(a0, b0, mode="full")  # index n-1 = zero lag; +k: a later than b
    seg = full[n - 1 - L:n + L]
    i = int(np.argmax(seg))
    frac = 0.0
    if 0 < i < len(seg) - 1:  # parabolic sub-sample refinement
        y0, y1, y2 = seg[i - 1], seg[i], seg[i + 1]
        d = y0 - 2 * y1 + y2
        frac = 0.5 * (y0 - y2) / d if d else 0.0
    lag = (i - L + frac) / fs
    corr = float(seg[i] / denom)
    ok = corr >= 0.5 and min(events_a, events_b) >= 2
    reason = "" if ok else (
        "gerakan kurang jelas — lakukan minimal 2–3 loncatan/ketukan tegas" if min(events_a, events_b) < 2
        else "pola gerakan kedua sensor kurang mirip (korelasi rendah)"
    )
    return {
        "ok": ok,
        "reason": reason,
        "offset_s": float(lag),
        "correlation": corr,
        "events_a": events_a,
        "events_b": events_b,
        "at_edge": abs(i - L) >= L - 1,
    }
