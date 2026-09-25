"""Central data hub: receives samples from devices, feeds the recorder and
analysers, and broadcasts batched updates to dashboard websockets."""

from __future__ import annotations

import asyncio
import json
import logging
import time
from pathlib import Path

from .analysis import EegBands, Hrv
from .recorder import Recorder
from .streams import STREAMS

log = logging.getLogger(__name__)


class Hub:
    def __init__(self, data_dir: Path, send_interval: float = 0.05, metrics_interval: float = 0.5):
        self.data_dir = Path(data_dir)
        self.send_interval = send_interval
        self.metrics_interval = metrics_interval
        self.clients: set = set()
        self.status: dict[str, dict] = {"muse": {"state": "disconnected"}, "polar": {"state": "disconnected"}}
        self.recorder: Recorder | None = None
        self.last_recording: dict | None = None
        self.eeg = EegBands()
        self.hrv = Hrv()
        self.latest: dict[str, list] = {}
        self._pending: dict[str, dict] = {}
        self._events: list[dict] = []

    # -- data in -----------------------------------------------------------
    def push(self, stream: str, ts: list[float], rows: list[list]) -> None:
        p = self._pending.setdefault(stream, {"t": [], "v": []})
        p["t"].extend(ts)
        p["v"].extend(rows)
        self.latest[stream] = rows[-1]
        if self.recorder:
            try:
                self.recorder.write(stream, ts, rows)
            except Exception:  # noqa: BLE001
                log.exception("recording write failed")
        if stream == "muse_eeg":
            self.eeg.add(rows)
        elif stream == "polar_rr":
            for t, row in zip(ts, rows):
                self.hrv.add(t, row[0])

    def set_status(self, device: str, **info) -> None:
        if info.get("state") in ("scanning", "disconnected"):
            if device == "muse":
                self.eeg.reset()
            else:
                self.hrv.reset()
        keep = {k: v for k, v in self.status.get(device, {}).items() if k in ("battery",)}
        if info.get("state") == "disconnected":
            keep = {}
        self.status[device] = {**keep, **info}
        self._events.append({"type": "status", "status": self.status})

    def update_status(self, device: str, **info) -> None:
        self.status.setdefault(device, {}).update(info)
        self._events.append({"type": "status", "status": self.status})

    # -- recording / markers ----------------------------------------------
    def start_recording(self, name: str = "", note: str = "") -> dict:
        if self.recorder:
            return self.recorder.info()
        self.recorder = Recorder(self.data_dir, name, note, devices=json.loads(json.dumps(self.status)))
        log.info("recording to %s", self.recorder.dir)
        self._events.append({"type": "recording", "recording": self.recorder.info()})
        return self.recorder.info()

    def stop_recording(self) -> dict | None:
        if not self.recorder:
            return None
        self.recorder.close()
        info = self.recorder.info()
        log.info("recording saved: %s (%.1f s)", info["dir"], info["elapsed"])
        self.last_recording = info
        self.recorder = None
        self._events.append({"type": "recording", "recording": info})
        return info

    def marker(self, label: str) -> None:
        label = (label or "marker").strip()[:200]
        t = time.time()
        self.push("marker", [t], [[label]])

    # -- data out ----------------------------------------------------------
    def hello(self) -> dict:
        return {
            "type": "hello",
            "streams": STREAMS,
            "status": self.status,
            "recording": self.recorder.info() if self.recorder else self.last_recording,
            "server_time": time.time(),
        }

    def metrics(self) -> dict:
        return {
            "type": "metrics",
            "eeg": self.eeg.compute(),
            "hrv": self.hrv.compute(),
            "recording": self.recorder.info() if self.recorder else None,
            "server_time": time.time(),
        }

    async def _send_all(self, text: str) -> None:
        for ws in list(self.clients):
            try:
                await ws.send_str(text)
            except Exception:  # noqa: BLE001
                self.clients.discard(ws)

    async def broadcast_loop(self) -> None:
        last_metrics = 0.0
        while True:
            await asyncio.sleep(self.send_interval)
            msgs, self._events = self._events, []
            # collapse repeated status updates into the latest one
            statuses = [m for m in msgs if m["type"] == "status"]
            msgs = [m for m in msgs if m["type"] != "status"] + statuses[-1:]
            if self._pending:
                msgs.append({"type": "data", "streams": self._pending})
                self._pending = {}
            now = time.monotonic()
            if now - last_metrics >= self.metrics_interval:
                last_metrics = now
                try:
                    msgs.append(self.metrics())
                except Exception:  # noqa: BLE001
                    log.exception("metrics failed")
                if self.recorder:
                    self.recorder.flush()
            if self.clients:
                for m in msgs:
                    await self._send_all(json.dumps(m, separators=(",", ":")))
