"""Polar H10 chest strap over BLE: heart rate + RR intervals (standard HR service),
raw ECG at 130 Hz and accelerometer at 200 Hz (Polar Measurement Data service)."""

from __future__ import annotations

import asyncio
import logging
import time

from .ble import BleSensor
from .streams import SampleClock

log = logging.getLogger(__name__)

HR_MEASUREMENT = "00002a37-0000-1000-8000-00805f9b34fb"
BATTERY_LEVEL = "00002a19-0000-1000-8000-00805f9b34fb"
PMD_CONTROL = "fb005c81-02e7-f387-1cad-8acd2d8df0c8"
PMD_DATA = "fb005c82-02e7-f387-1cad-8acd2d8df0c8"

PMD_ECG = 0x00
PMD_ACC = 0x02
# Start ECG: sample rate 130 Hz (0x0082), resolution 14 bit
ECG_START = bytes([0x02, PMD_ECG, 0x00, 0x01, 0x82, 0x00, 0x01, 0x01, 0x0E, 0x00])
# Start ACC: sample rate 200 Hz (0x00C8), resolution 16 bit, range 8 g
ACC_START = bytes([0x02, PMD_ACC, 0x00, 0x01, 0xC8, 0x00, 0x01, 0x01, 0x10, 0x00, 0x02, 0x01, 0x08, 0x00])
RATES = {PMD_ECG: 130, PMD_ACC: 200}
NAMES = {PMD_ECG: "EKG", PMD_ACC: "akselerometer"}


def decode_hr(data: bytes) -> tuple[int, int, list[float]]:
    """Heart Rate Measurement -> (bpm, contact, rr intervals in ms).

    contact: 1 = skin contact, 0 = no contact, -1 = not reported.
    """
    flags = data[0]
    idx = 1
    if flags & 0x01:
        hr = int.from_bytes(data[idx:idx + 2], "little")
        idx += 2
    else:
        hr = data[idx]
        idx += 1
    contact = (1 if flags & 0x02 else 0) if flags & 0x04 else -1
    if flags & 0x08:  # energy expended present
        idx += 2
    rr: list[float] = []
    if flags & 0x10:
        while idx + 1 < len(data):
            rr.append(int.from_bytes(data[idx:idx + 2], "little") / 1024.0 * 1000.0)
            idx += 2
    return hr, contact, rr


def decode_pmd(data: bytes) -> tuple[int, int, list] | None:
    """PMD data frame -> (measurement type, sensor timestamp of last sample in ns, samples).

    ECG samples are microvolts; ACC samples are [x, y, z] in milli-g.
    Returns None for frames this app doesn't handle (e.g. compressed frames).
    """
    if len(data) < 10:
        return None
    kind, frame_type = data[0], data[9]
    ts = int.from_bytes(data[1:9], "little")
    body = data[10:]
    if kind == PMD_ECG and frame_type == 0x00:
        return kind, ts, [int.from_bytes(body[i:i + 3], "little", signed=True) for i in range(0, len(body) - 2, 3)]
    if kind == PMD_ACC and frame_type in (0x00, 0x01, 0x02):
        width = frame_type + 1  # bytes per axis: int8, int16 or int24
        step = 3 * width
        return kind, ts, [
            [int.from_bytes(body[i + a * width:i + (a + 1) * width], "little", signed=True) for a in range(3)]
            for i in range(0, len(body) - step + 1, step)
        ]
    return None


def decode_ecg(data: bytes) -> list[float] | None:
    """PMD data frame of type ECG -> samples in microvolts."""
    frame = decode_pmd(data)
    if frame is None or frame[0] != PMD_ECG:
        return None
    return [float(s) for s in frame[2]]


class SensorTimes:
    """Per-sample sensor timestamps (ns) from the PMD frame timestamp of the last sample.

    Sample spacing is taken from consecutive frame timestamps, so it follows the
    strap's real clock; frames that went missing are reported as ``skipped``.
    """

    def __init__(self, rate: float):
        self.rate = rate
        self.prev: int | None = None

    def reset(self) -> None:
        self.prev = None

    def stamps(self, ts_last: int, n: int) -> tuple[list[int], int]:
        nominal = 1e9 / self.rate
        dt, skipped = nominal, 0
        if self.prev is not None and ts_last > self.prev:
            span = ts_last - self.prev
            missing = round(span / nominal) - n
            if 0 < missing < self.rate * 10:
                skipped = missing
            elif missing <= 0:
                dt = span / n
        self.prev = ts_last
        return [int(round(ts_last - (n - 1 - i) * dt)) for i in range(n)], skipped


class PolarH10(BleSensor):
    key = "polar"
    tick_interval = 60.0

    def __init__(self, hub, name_prefix: str = "Polar H10", address: str | None = None,
                 ecg: bool = True, acc: bool = True):
        super().__init__(hub, name_prefix, address)
        self.ecg = ecg
        self.acc = acc
        self.clocks = {PMD_ECG: SampleClock(130), PMD_ACC: SampleClock(200)}
        self.sensor = {PMD_ECG: SensorTimes(130), PMD_ACC: SensorTimes(200)}
        self._pmd_reply: asyncio.Future | None = None

    def reset(self) -> None:
        for obj in (*self.clocks.values(), *self.sensor.values()):
            obj.reset()

    def on_hr(self, data: bytes) -> None:
        now = time.time()
        hr, contact, rr = decode_hr(data)
        self.hub.push("polar_hr", [now], [[hr, contact]])
        if rr:
            # RR intervals end at (roughly) the notification time; space them backwards.
            ts, t = [], now
            for value in reversed(rr):
                ts.append(t)
                t -= value / 1000.0
            self.hub.push("polar_rr", ts[::-1], [[v] for v in rr])

    def on_pmd_data(self, data: bytes) -> None:
        now = time.time()
        frame = decode_pmd(data)
        if frame is None:
            if len(data) > 9 and data[9] & 0x80:
                log.warning("Polar sent a compressed PMD frame (type 0x%02x), ignored", data[9])
            return
        kind, ts_last, samples = frame
        if not samples:
            return
        sensor_ns, skipped = self.sensor[kind].stamps(ts_last, len(samples))
        ts = self.clocks[kind].stamps(len(samples), now, skipped)
        if kind == PMD_ECG:
            rows = [[float(v), s] for v, s in zip(samples, sensor_ns)]
            self.hub.push("polar_ecg", ts, rows)
        else:
            rows = [[x / 1000.0, y / 1000.0, z / 1000.0, s] for (x, y, z), s in zip(samples, sensor_ns)]
            self.hub.push("polar_acc", ts, rows)

    def on_pmd_control(self, data: bytes) -> None:
        # Response: F0 <op> <measurement type> <status> ...; status 0 = success
        if len(data) >= 4 and data[0] == 0xF0:
            if self._pmd_reply and not self._pmd_reply.done():
                self._pmd_reply.set_result(data[3])

    async def _pmd_request(self, client, cmd: bytes) -> int | None:
        """PMD handles one request at a time: send it and wait for its response."""
        self._pmd_reply = asyncio.get_running_loop().create_future()
        await client.write_gatt_char(PMD_CONTROL, cmd, response=True)
        try:
            return await asyncio.wait_for(self._pmd_reply, timeout=3)
        except asyncio.TimeoutError:
            log.warning("no PMD response to %s", cmd.hex())
            return None

    async def start(self, client) -> None:
        await self.tick(client)
        await client.start_notify(HR_MEASUREMENT, lambda _s, d: self.on_hr(d))
        wanted = [(PMD_ECG, ECG_START)] * self.ecg + [(PMD_ACC, ACC_START)] * self.acc
        if not wanted:
            return
        await client.start_notify(PMD_CONTROL, lambda _s, d: self.on_pmd_control(d))
        await client.start_notify(PMD_DATA, lambda _s, d: self.on_pmd_data(d))
        failed = []
        for kind, cmd in wanted:
            status = await self._pmd_request(client, cmd)
            if status:  # 0 = success, None = no reply (stream may still start)
                log.warning("Polar %s start failed with status %d", NAMES[kind], status)
                failed.append(f"{NAMES[kind]} (status {status})")
        if failed:
            self.hub.update_status(self.key, message="Gagal memulai " + ", ".join(failed))

    async def tick(self, client) -> None:
        try:
            battery = await client.read_gatt_char(BATTERY_LEVEL)
            self.hub.update_status(self.key, battery=int(battery[0]))
        except Exception:  # noqa: BLE001
            pass

    async def stop(self, client) -> None:
        for kind, on in ((PMD_ECG, self.ecg), (PMD_ACC, self.acc)):
            if on:
                await self._pmd_request(client, bytes([0x03, kind]))
