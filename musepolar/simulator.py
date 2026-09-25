"""Synthetic Muse 2 / Polar H10 for trying the dashboard without hardware (--sim)."""

from __future__ import annotations

import asyncio
import math
import random
import time

from .ble import wait_any


class _SimDevice:
    key = "device"
    name = "Simulator"
    tick = 0.05

    def __init__(self, hub):
        self.hub = hub

    def emit(self, t0: float, t1: float) -> None:
        raise NotImplementedError

    async def run(self, stop: asyncio.Event) -> None:
        self.hub.set_status(self.key, state="connecting", name=self.name)
        await wait_any(stop, timeout=0.5)
        self.hub.set_status(self.key, state="streaming", name=self.name, address="simulated", battery=87)
        last = time.time()
        while not stop.is_set():
            await wait_any(stop, timeout=self.tick)
            now = time.time()
            self.emit(last, now)
            last = now
        self.hub.set_status(self.key, state="disconnected")


SIM_MUSE_LAG = 0.060  # simulated extra latency of the Muse, recovered by the sync procedure


def _jumps(hub, t: float, lag: float = 0.0) -> float:
    """Extra vertical acceleration (g) from three small jumps during a sync window."""
    sync = hub.sync
    if not sync.get("active"):
        return 0.0
    v = 0.0
    for e in (2.0, 4.5, 7.0):
        d = t - (sync["start"] + e + lag)
        v += 1.6 * math.exp(-(d ** 2) / (2 * 0.04 ** 2)) - 0.8 * math.exp(-((d + 0.25) ** 2) / (2 * 0.06 ** 2))
    return v


def _ticks(t0: float, t1: float, rate: float) -> list[float]:
    """Sample instants on a global rate grid within (t0, t1]."""
    k0 = math.floor(t0 * rate) + 1
    k1 = math.floor(t1 * rate)
    return [k / rate for k in range(k0, k1 + 1)]


class SimMuse(_SimDevice):
    key = "muse"
    name = "Muse-SIM"

    def __init__(self, hub):
        super().__init__(hub)
        self.phase = [random.random() * 6.28 for _ in range(4)]
        self._tele = 0.0

    def emit(self, t0: float, t1: float) -> None:
        ts = _ticks(t0, t1, 256)
        if ts:
            rows = []
            for t in ts:
                alpha_amp = 12 + 10 * math.sin(2 * math.pi * t / 20)  # alpha waxes and wanes
                blink = 150 * math.exp(-((t % 7) - 0.2) ** 2 / 0.005)
                row = []
                for ch in range(4):
                    v = 800 + alpha_amp * math.sin(2 * math.pi * 10 * t + self.phase[ch])
                    v += 6 * math.sin(2 * math.pi * 6 * t + ch) + 4 * math.sin(2 * math.pi * 20 * t + 2 * ch)
                    v += 5 * math.sin(2 * math.pi * 50 * t) + random.gauss(0, 5)
                    if ch in (1, 2):
                        v -= blink
                    row.append(v)
                rows.append(row)
            self.hub.push("muse_eeg", ts, rows)
        ts = _ticks(t0, t1, 64)
        if ts:
            rows = []
            for t in ts:
                pulse = math.sin(2 * math.pi * 1.2 * t) + 0.3 * math.sin(2 * math.pi * 2.4 * t + 1)
                rows.append([30000 + random.gauss(0, 30), 250000 + 3000 * pulse, 180000 + 1800 * pulse])
            self.hub.push("muse_ppg", ts, rows)
        ts = _ticks(t0, t1, 52)
        if ts:
            self.hub.push("muse_acc", ts, [
                [0.02 * math.sin(t), -0.05 + 0.01 * math.sin(0.7 * t), 0.99 + _jumps(self.hub, t, SIM_MUSE_LAG)]
                for t in ts
            ])
            self.hub.push("muse_gyro", ts, [[random.gauss(0, 0.5), random.gauss(0, 0.5), random.gauss(0, 0.5)] for _ in ts])
        if t1 - self._tele > 5:
            self._tele = t1
            self.hub.push("muse_telemetry", [t1], [[87.0, 3900.0, 0.0, 30.0]])


class SimPolar(_SimDevice):
    key = "polar"
    name = "Polar H10 SIM"

    def __init__(self, hub):
        super().__init__(hub)
        self.next_beat = time.time() + 0.5
        self.beats: list[float] = []
        self.pending_rr: list[float] = []
        self.last_hr_push = time.time()
        self.t_start = time.time()

    def _sensor_ns(self, t: float) -> int:
        return int((t - self.t_start) * 1e9 * 1.00002)  # strap clock runs 20 ppm fast

    def _ecg(self, t: float) -> float:
        v = 0.0
        for b in self.beats[-3:]:
            d = t - b
            v += 150 * math.exp(-((d + 0.16) ** 2) / 0.0008)  # P
            v -= 120 * math.exp(-((d + 0.03) ** 2) / 0.00005)  # Q
            v += 1400 * math.exp(-(d ** 2) / 0.00007)  # R
            v -= 250 * math.exp(-((d - 0.03) ** 2) / 0.00006)  # S
            v += 300 * math.exp(-((d - 0.25) ** 2) / 0.003)  # T
        return v + 40 * math.sin(2 * math.pi * 0.25 * t) + random.gauss(0, 12)

    def emit(self, t0: float, t1: float) -> None:
        while self.next_beat <= t1 + 0.3:
            if self.beats:
                self.pending_rr.append((self.next_beat - self.beats[-1]) * 1000)
            self.beats.append(self.next_beat)
            self.beats = self.beats[-5:]
            # respiratory sinus arrhythmia (~0.25 Hz breathing) + noise
            rr = 0.85 + 0.06 * math.sin(2 * math.pi * 0.25 * self.next_beat) + random.gauss(0, 0.015)
            self.next_beat += rr
        ts = _ticks(t0, t1, 130)
        if ts:
            self.hub.push("polar_ecg", ts, [[float(round(self._ecg(t))), self._sensor_ns(t)] for t in ts])
        ts = _ticks(t0, t1, 200)
        if ts:
            self.hub.push("polar_acc", ts, [
                [-0.98 - _jumps(self.hub, t) + random.gauss(0, 0.01), 0.05 + random.gauss(0, 0.01),
                 0.12 + 0.02 * math.sin(2 * math.pi * 0.25 * t), self._sensor_ns(t)]
                for t in ts
            ])
        if t1 - self.last_hr_push >= 1.0:
            self.last_hr_push = t1
            rr = [r for r in self.pending_rr]
            self.pending_rr = []
            hr = round(60000 / (sum(rr) / len(rr))) if rr else 70
            self.hub.push("polar_hr", [t1], [[hr, 1]])
            if rr:
                ts, t = [], t1
                for value in reversed(rr):
                    ts.append(t)
                    t -= value / 1000
                self.hub.push("polar_rr", ts[::-1], [[v] for v in rr])
