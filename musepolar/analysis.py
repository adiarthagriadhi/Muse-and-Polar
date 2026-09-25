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
