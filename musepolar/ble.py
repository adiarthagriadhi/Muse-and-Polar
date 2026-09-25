"""Common scan / connect / reconnect loop for BLE sensors (via bleak)."""

from __future__ import annotations

import asyncio
import logging
import time

log = logging.getLogger(__name__)


async def wait_any(*events: asyncio.Event, timeout: float | None = None) -> None:
    tasks = [asyncio.create_task(e.wait()) for e in events]
    try:
        await asyncio.wait(tasks, timeout=timeout, return_when=asyncio.FIRST_COMPLETED)
    finally:
        for t in tasks:
            t.cancel()


class BleSensor:
    """Base class: finds a device by name prefix (or address) and keeps it streaming.

    Subclasses implement ``start(client)``, optionally ``stop(client)`` and
    ``tick(client)`` (called every ``tick_interval`` seconds while connected).
    """

    key = "device"
    tick_interval = 5.0
    scan_timeout = 10.0

    def __init__(self, hub, name_prefix: str, address: str | None = None):
        self.hub = hub
        self.issue = ""  # last problem, shown on the dashboard while reconnecting
        self.name_prefix = name_prefix.lower()
        self.address = address.lower() if address else None

    # -- hooks -------------------------------------------------------------
    async def start(self, client) -> None:  # pragma: no cover - hardware
        raise NotImplementedError

    async def stop(self, client) -> None:
        pass

    async def tick(self, client) -> None:
        pass

    def reset(self) -> None:
        """Clear decoder state between connections."""

    # -- main loop ---------------------------------------------------------
    def _matches(self, device, adv) -> bool:
        if self.address:
            return device.address.lower() == self.address
        name = (adv.local_name or device.name or "").lower()
        return name.startswith(self.name_prefix)

    async def run(self, stop: asyncio.Event) -> None:
        from bleak import BleakClient, BleakScanner

        while not stop.is_set():
            try:
                self.hub.set_status(self.key, state="scanning", message=self.issue)
                device = await BleakScanner.find_device_by_filter(self._matches, timeout=self.scan_timeout)
                if device is None:
                    self.issue = "perangkat tidak ditemukan — nyala? terhubung ke HP/aplikasi lain?"
                    self.hub.set_status(self.key, state="not_found", message=self.issue)
                    await wait_any(stop, timeout=2)
                    continue
                if stop.is_set():
                    break
                name = device.name or device.address
                self.hub.set_status(self.key, state="connecting", name=name)
                disconnected = asyncio.Event()
                self.reset()
                async with BleakClient(device, disconnected_callback=lambda _c: disconnected.set()) as client:
                    await self.start(client)
                    self.issue = ""
                    self.hub.set_status(self.key, state="streaming", name=name, address=device.address)
                    log.info("%s streaming from %s", self.key, name)
                    while not (stop.is_set() or disconnected.is_set()):
                        await wait_any(stop, disconnected, timeout=self.tick_interval)
                        if not (stop.is_set() or disconnected.is_set()):
                            await self.tick(client)
                    if stop.is_set() and client.is_connected:
                        try:
                            await asyncio.wait_for(self.stop(client), timeout=3)
                        except Exception as exc:  # noqa: BLE001
                            log.debug("%s stop failed: %s", self.key, exc)
                if not stop.is_set():
                    self.issue = f"koneksi terputus {time.strftime('%H:%M:%S')}, menyambung ulang…"
                    log.warning("%s disconnected, reconnecting", self.key)
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001
                log.exception("%s error", self.key)
                self.issue = f"error: {exc or type(exc).__name__}"
                self.hub.set_status(self.key, state="error", message=self.issue)
            if not stop.is_set():
                await wait_any(stop, timeout=2)
        self.hub.set_status(self.key, state="disconnected")


async def write_char(client, uuid: str, data: bytes) -> None:
    """Write using write-without-response when the characteristic supports it."""
    char = client.services.get_characteristic(uuid)
    response = char is None or "write-without-response" not in char.properties
    await client.write_gatt_char(uuid, data, response=response)
