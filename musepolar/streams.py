"""Stream definitions and small timing helpers shared by all devices."""

from __future__ import annotations

STREAMS: dict[str, dict] = {
    "muse_eeg": {"device": "muse", "rate": 256, "unit": "uV", "columns": ["TP9", "AF7", "AF8", "TP10"]},
    "muse_ppg": {"device": "muse", "rate": 64, "unit": "raw", "columns": ["ambient", "ir", "red"]},
    "muse_acc": {"device": "muse", "rate": 52, "unit": "g", "columns": ["x", "y", "z"]},
    "muse_gyro": {"device": "muse", "rate": 52, "unit": "deg/s", "columns": ["x", "y", "z"]},
    "muse_telemetry": {
        "device": "muse",
        "rate": 0,
        "unit": "",
        "columns": ["battery_pct", "fuel_gauge_mv", "adc_mv", "temperature_c"],
    },
    "polar_hr": {"device": "polar", "rate": 0, "unit": "bpm", "columns": ["hr_bpm", "contact"]},
    "polar_rr": {"device": "polar", "rate": 0, "unit": "ms", "columns": ["rr_ms"]},
    "polar_ecg": {"device": "polar", "rate": 130, "unit": "uV", "columns": ["ecg_uV"]},
    "marker": {"device": "app", "rate": 0, "unit": "", "columns": ["label"]},
}


class SampleClock:
    """Assigns evenly spaced timestamps to packets of samples.

    BLE notifications arrive with jitter, so per-sample times are reconstructed
    from the nominal sample rate and anchored to the host clock.  The anchor
    slowly follows the receive times to absorb crystal drift, and is reset when
    the prediction drifts further than ``tolerance`` seconds (e.g. after a gap).
    """

    def __init__(self, rate: float, tolerance: float = 0.25, follow: float = 0.01):
        self.dt = 1.0 / rate
        self.tolerance = tolerance
        self.follow = follow
        self.next_t: float | None = None
        self.last_t: float | None = None

    def reset(self) -> None:
        self.next_t = None
        self.last_t = None

    def stamps(self, n: int, recv_time: float, skipped: int = 0) -> list[float]:
        # The last sample of the packet was taken no later than recv_time.
        start = recv_time - (n - 1) * self.dt
        if self.next_t is not None:
            self.next_t += skipped * self.dt
        if self.next_t is None or abs(self.next_t - start) > self.tolerance:
            self.next_t = start
        else:
            self.next_t += (start - self.next_t) * self.follow
        if self.last_t is not None and self.next_t <= self.last_t:
            self.next_t = self.last_t + self.dt
        ts = [self.next_t + i * self.dt for i in range(n)]
        self.last_t = ts[-1]
        self.next_t += n * self.dt
        return ts


def seq_gap(prev: int | None, seq: int, modulo: int = 0x10000) -> int:
    """Number of packets lost between two sequence numbers (with wraparound)."""
    if prev is None:
        return 0
    diff = (seq - prev) % modulo
    if diff == 0 or diff > modulo // 2:
        return 0  # duplicate or out of order: don't move the clock
    return diff - 1
