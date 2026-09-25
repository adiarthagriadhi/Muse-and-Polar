"""Muse 2 headband over BLE: EEG (4 ch @ 256 Hz), PPG (3 ch @ 64 Hz), accelerometer,
gyroscope and telemetry.  Protocol follows muse-js / muselsl."""

from __future__ import annotations

import asyncio
import time

from .ble import BleSensor, write_char
from .streams import SampleClock, seq_gap


def _uuid(short: str) -> str:
    return f"273e{short}-4c4d-454d-96be-f03bac821358"


CONTROL = _uuid("0001")
EEG_CHARS = [_uuid("0003"), _uuid("0004"), _uuid("0005"), _uuid("0006")]  # TP9, AF7, AF8, TP10
GYRO = _uuid("0009")
ACC = _uuid("000a")
TELEMETRY = _uuid("000b")
PPG_CHARS = [_uuid("000f"), _uuid("0010"), _uuid("0011")]  # ambient, IR, red

EEG_SCALE = 0.48828125  # uV per LSB (1000/2048)
ACC_SCALE = 0.0000610352  # g per LSB
GYRO_SCALE = 0.0074768  # deg/s per LSB


def encode_command(cmd: str) -> bytes:
    body = f"{cmd}\n".encode()
    return bytes([len(body)]) + body


# -- packet decoders ------------------------------------------------------

def decode_eeg(data: bytes) -> tuple[int, list[float]]:
    """2-byte sequence + 12 unsigned 12-bit samples -> microvolts."""
    seq = int.from_bytes(data[0:2], "big")
    out: list[float] = []
    payload = data[2:20]
    for i in range(0, 18, 3):
        b0, b1, b2 = payload[i], payload[i + 1], payload[i + 2]
        for raw in ((b0 << 4) | (b1 >> 4), ((b1 & 0x0F) << 8) | b2):
            out.append(EEG_SCALE * (raw - 0x800))
    return seq, out


def decode_ppg(data: bytes) -> tuple[int, list[float]]:
    """2-byte sequence + 6 unsigned 24-bit samples."""
    seq = int.from_bytes(data[0:2], "big")
    return seq, [float(int.from_bytes(data[i:i + 3], "big")) for i in range(2, 20, 3)]


def decode_imu(data: bytes, scale: float) -> tuple[int, list[list[float]]]:
    """2-byte sequence + 3 samples of signed 16-bit (x, y, z)."""
    seq = int.from_bytes(data[0:2], "big")
    vals = [int.from_bytes(data[i:i + 2], "big", signed=True) * scale for i in range(2, 20, 2)]
    return seq, [vals[0:3], vals[3:6], vals[6:9]]


def decode_telemetry(data: bytes) -> list[float]:
    u16 = [int.from_bytes(data[i:i + 2], "big") for i in range(0, 10, 2)]
    return [u16[1] / 512.0, u16[2] * 2.2, float(u16[3]), float(u16[4])]


class PacketJoiner:
    """Muse sends each channel in its own notification; join those sharing a sequence."""

    def __init__(self, n_channels: int, max_pending: int = 16):
        self.n = n_channels
        self.max_pending = max_pending
        self.pending: dict[int, list] = {}

    def reset(self) -> None:
        self.pending.clear()

    def add(self, seq: int, channel: int, samples: list[float]) -> list[list[float]] | None:
        slot = self.pending.setdefault(seq, [None] * self.n)
        slot[channel] = samples
        if any(s is None for s in slot):
            while len(self.pending) > self.max_pending:
                self.pending.pop(next(iter(self.pending)))
            return None
        del self.pending[seq]
        # anything older than a completed packet will never complete
        for k in [k for k in self.pending if 0 < (seq - k) % 0x10000 < 0x8000]:
            del self.pending[k]
        return [list(row) for row in zip(*slot)]


class Muse(BleSensor):
    key = "muse"
    tick_interval = 10.0

    def __init__(self, hub, name_prefix: str = "Muse", address: str | None = None, ppg: bool = True):
        super().__init__(hub, name_prefix, address)
        self.ppg = ppg
        self.eeg_join = PacketJoiner(4)
        self.ppg_join = PacketJoiner(3)
        self.eeg_clock = SampleClock(256)
        self.ppg_clock = SampleClock(64)
        self.acc_clock = SampleClock(52)
        self.gyro_clock = SampleClock(52)
        self.last_seq: dict[str, int | None] = {}

    def reset(self) -> None:
        for obj in (self.eeg_join, self.ppg_join, self.eeg_clock, self.ppg_clock, self.acc_clock, self.gyro_clock):
            obj.reset()
        self.last_seq = {}

    def _gap(self, stream: str, seq: int) -> int:
        gap = seq_gap(self.last_seq.get(stream), seq)
        self.last_seq[stream] = seq
        return gap if gap < 1000 else 0

    # -- notification handlers ---------------------------------------------
    def on_eeg(self, channel: int, data: bytes) -> None:
        now = time.time()
        seq, samples = decode_eeg(data)
        rows = self.eeg_join.add(seq, channel, samples)
        if rows:
            ts = self.eeg_clock.stamps(len(rows), now, self._gap("eeg", seq) * 12)
            self.hub.push("muse_eeg", ts, rows)

    def on_ppg(self, channel: int, data: bytes) -> None:
        now = time.time()
        seq, samples = decode_ppg(data)
        rows = self.ppg_join.add(seq, channel, samples)
        if rows:
            ts = self.ppg_clock.stamps(len(rows), now, self._gap("ppg", seq) * 6)
            self.hub.push("muse_ppg", ts, rows)

    def on_acc(self, data: bytes) -> None:
        now = time.time()
        seq, rows = decode_imu(data, ACC_SCALE)
        self.hub.push("muse_acc", self.acc_clock.stamps(3, now, self._gap("acc", seq) * 3), rows)

    def on_gyro(self, data: bytes) -> None:
        now = time.time()
        seq, rows = decode_imu(data, GYRO_SCALE)
        self.hub.push("muse_gyro", self.gyro_clock.stamps(3, now, self._gap("gyro", seq) * 3), rows)

    def on_telemetry(self, data: bytes) -> None:
        values = decode_telemetry(data)
        self.hub.push("muse_telemetry", [time.time()], [values])
        self.hub.update_status(self.key, battery=round(values[0]))

    # -- lifecycle ---------------------------------------------------------
    async def _cmd(self, client, cmd: str) -> None:
        await write_char(client, CONTROL, encode_command(cmd))
        await asyncio.sleep(0.05)

    async def start(self, client) -> None:
        await self._cmd(client, "h")  # halt
        await self._cmd(client, "p50" if self.ppg else "p21")  # preset: EEG + PPG, or EEG only
        await client.start_notify(TELEMETRY, lambda _s, d: self.on_telemetry(d))
        await client.start_notify(ACC, lambda _s, d: self.on_acc(d))
        await client.start_notify(GYRO, lambda _s, d: self.on_gyro(d))
        for ch, uuid in enumerate(EEG_CHARS):
            await client.start_notify(uuid, lambda _s, d, ch=ch: self.on_eeg(ch, d))
        if self.ppg:
            for ch, uuid in enumerate(PPG_CHARS):
                await client.start_notify(uuid, lambda _s, d, ch=ch: self.on_ppg(ch, d))
        await self._cmd(client, "s")  # status / start
        await self._cmd(client, "d")  # resume streaming

    async def tick(self, client) -> None:
        await self._cmd(client, "k")  # keep-alive

    async def stop(self, client) -> None:
        await self._cmd(client, "h")
