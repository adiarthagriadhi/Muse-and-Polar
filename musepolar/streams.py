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
    "polar_ecg": {"device": "polar", "rate": 130, "unit": "uV", "columns": ["ecg_uV", "sensor_ns"]},
    "polar_acc": {"device": "polar", "rate": 200, "unit": "g", "columns": ["x", "y", "z", "sensor_ns"]},
    "marker": {"device": "app", "rate": 0, "unit": "", "columns": ["label"]},
}


class SampleClock:
    """Assigns evenly spaced timestamps to packets of samples.

    BLE notifications arrive with jitter, so per-sample times are reconstructed
    from the nominal sample rate ("device time": samples counted, including
    ``skipped`` ones the caller detected from sequence numbers or sensor time)
    and anchored to the host clock with an offset ``host - device``.

    Every packet gives an upper bound for that offset, because its last sample
    was taken no later than ``recv_time``.  The anchor therefore drops at once
    to a packet that arrives earlier than predicted, and rises only slowly
    (``follow`` times the excess, the excess capped at ``tolerance``) to absorb
    a crystal that runs slower than nominal.  A late packet that is not
    explained by lost samples (Bluetooth retransmission, a busy event loop)
    is a delivery delay, not a time jump, so it no longer moves the anchor.
    Only an excess above ``resync`` seconds re-anchors forward.

    v1.0.0 instead re-anchored to any packet off by more than ``tolerance`` and
    then refused to step back, so one delivery delay of more than ~0.3 s shifted
    all later timestamps of that stream forward for the rest of the connection.
    """

    def __init__(self, rate: float, tolerance: float = 0.25, follow: float = 0.01, resync: float = 5.0):
        self.dt = 1.0 / rate
        self.tolerance = tolerance
        self.follow = follow
        self.resync = resync
        self.offset: float | None = None  # host time - device time (s)
        self.dev = 0.0  # device time of the next sample (s)
        self.last_t: float | None = None

    def reset(self) -> None:
        self.offset = None
        self.dev = 0.0
        self.last_t = None

    def stamps(self, n: int, recv_time: float, skipped: int = 0) -> list[float]:
        self.dev += skipped * self.dt
        # offset implied by this packet: its last sample was taken no later than recv_time
        o = recv_time - (self.dev + (n - 1) * self.dt)
        if self.offset is None or o - self.offset > self.resync:
            self.offset = o
        elif o < self.offset:
            self.offset = o
        else:
            self.offset += min(o - self.offset, self.tolerance) * self.follow
        ts = []
        floor = -float("inf") if self.last_t is None else self.last_t + 0.5 * self.dt
        for i in range(n):
            # stay strictly increasing; after the anchor drops, samples are briefly compressed
            t = max(self.offset + self.dev + i * self.dt, floor)
            ts.append(t)
            floor = t + 0.5 * self.dt
        self.last_t = ts[-1]
        self.dev += n * self.dt
        return ts


def seq_gap(prev: int | None, seq: int, modulo: int = 0x10000) -> int:
    """Number of packets lost between two sequence numbers (with wraparound)."""
    if prev is None:
        return 0
    diff = (seq - prev) % modulo
    if diff == 0 or diff > modulo // 2:
        return 0  # duplicate or out of order: don't move the clock
    return diff - 1
