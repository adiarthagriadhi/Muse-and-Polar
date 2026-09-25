"""Polar H10 chest strap over BLE: heart rate + RR intervals (standard HR service)
and raw ECG at 130 Hz (Polar Measurement Data service)."""

from __future__ import annotations

import logging
import time

from .ble import BleSensor
from .streams import SampleClock

log = logging.getLogger(__name__)

HR_MEASUREMENT = "00002a37-0000-1000-8000-00805f9b34fb"
BATTERY_LEVEL = "00002a19-0000-1000-8000-00805f9b34fb"
PMD_CONTROL = "fb005c81-02e7-f387-1cad-8acd2d8df0c8"
PMD_DATA = "fb005c82-02e7-f387-1cad-8acd2d8df0c8"

# Start ECG stream: sample rate 130 Hz (0x0082), resolution 14 bit (0x000E)
ECG_START = bytes([0x02, 0x00, 0x00, 0x01, 0x82, 0x00, 0x01, 0x01, 0x0E, 0x00])
ECG_STOP = bytes([0x03, 0x00])
PMD_ECG = 0x00


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


def decode_ecg(data: bytes) -> list[float] | None:
    """PMD data frame of type ECG -> samples in microvolts."""
    if len(data) < 10 or data[0] != PMD_ECG or data[9] != 0x00:
        return None
    return [float(int.from_bytes(data[i:i + 3], "little", signed=True)) for i in range(10, len(data) - 2, 3)]


class PolarH10(BleSensor):
    key = "polar"
    tick_interval = 60.0

    def __init__(self, hub, name_prefix: str = "Polar H10", address: str | None = None, ecg: bool = True):
        super().__init__(hub, name_prefix, address)
        self.ecg = ecg
        self.ecg_clock = SampleClock(130)

    def reset(self) -> None:
        self.ecg_clock.reset()

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
        samples = decode_ecg(data)
        if samples:
            self.hub.push("polar_ecg", self.ecg_clock.stamps(len(samples), now), [[s] for s in samples])

    def on_pmd_control(self, data: bytes) -> None:
        # Response: F0 <op> <type> <status> ...; status 0 = success
        if len(data) >= 4 and data[0] == 0xF0 and data[3] != 0:
            log.warning("Polar PMD request 0x%02x failed with status %d", data[1], data[3])
            self.hub.update_status(self.key, message=f"ECG gagal dimulai (status {data[3]})")

    async def start(self, client) -> None:
        try:
            battery = await client.read_gatt_char(BATTERY_LEVEL)
            self.hub.update_status(self.key, battery=int(battery[0]))
        except Exception:  # noqa: BLE001
            pass
        await client.start_notify(HR_MEASUREMENT, lambda _s, d: self.on_hr(d))
        if self.ecg:
            await client.start_notify(PMD_CONTROL, lambda _s, d: self.on_pmd_control(d))
            await client.start_notify(PMD_DATA, lambda _s, d: self.on_pmd_data(d))
            await client.write_gatt_char(PMD_CONTROL, ECG_START, response=True)

    async def tick(self, client) -> None:
        try:
            battery = await client.read_gatt_char(BATTERY_LEVEL)
            self.hub.update_status(self.key, battery=int(battery[0]))
        except Exception:  # noqa: BLE001
            pass

    async def stop(self, client) -> None:
        if self.ecg:
            await client.write_gatt_char(PMD_CONTROL, ECG_STOP, response=True)
