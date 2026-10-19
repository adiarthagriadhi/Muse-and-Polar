"""Central data hub: receives samples from devices, feeds the recorder and
analysers, and broadcasts batched updates to dashboard websockets."""

from __future__ import annotations

import asyncio
import json
import logging
import time
from collections import deque
from pathlib import Path

from . import cass
from .analysis import EegBands, Hrv, estimate_offset
from .recorder import Recorder
from .streams import STREAMS

log = logging.getLogger(__name__)


class Hub:
    def __init__(self, data_dir: Path, send_interval: float = 0.05, metrics_interval: float = 0.5,
                 cass_url: str = "http://127.0.0.1:8766/"):
        self.data_dir = Path(data_dir)
        self.cass_url = cass_url
        self.cass: dict = {"busy": False}
        self._cass_task: asyncio.Task | None = None
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
        # recent accelerometer history for cross-device synchronisation
        self.history = {"muse_acc": deque(maxlen=52 * 60), "polar_acc": deque(maxlen=200 * 60)}
        self.sync: dict = {"active": False, "result": None}
        self.syncs: list[dict] = []
        self._sync_task: asyncio.Task | None = None

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
        if stream in self.history:
            self.history[stream].extend(zip(ts, (r[:3] for r in rows)))
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

    # -- synchronisation ---------------------------------------------------
    def start_sync(self, duration: float = 10.0) -> None:
        if self._sync_task and not self._sync_task.done():
            return
        self._sync_task = asyncio.create_task(self._run_sync(duration))

    def compute_sync(self, t0: float, t1: float) -> dict:
        def window(stream):
            pts = [(t, xyz) for t, xyz in self.history[stream] if t0 <= t <= t1]
            return [p[0] for p in pts], [p[1] for p in pts]

        (mt, mx), (pt, px) = window("muse_acc"), window("polar_acc")
        if len(mt) < 20:
            res = {"ok": False, "reason": "akselerometer Muse tidak mengirim data"}
        elif len(pt) < 20:
            res = {"ok": False, "reason": "akselerometer Polar tidak mengirim data"}
        else:
            res = estimate_offset(mt, mx, pt, px)
        # a = Muse, b = Polar: positive offset = the same event appears later in Muse timestamps
        if "offset_s" in res:
            res["muse_minus_polar_s"] = res.pop("offset_s")
        res.update(start_unix=t0, end_unix=t1)
        return res

    async def _run_sync(self, duration: float) -> None:
        t0 = time.time()
        self.sync = {"active": True, "start": t0, "duration": duration, "result": self.sync.get("result")}
        self._events.append({"type": "sync", "sync": self.sync})
        self.marker("SYNC mulai")
        await asyncio.sleep(duration + 0.6)  # let late BLE packets arrive
        res = self.compute_sync(t0, t0 + duration)
        if "muse_minus_polar_s" in res:
            label = f"SYNC selesai (Muse−Polar {res['muse_minus_polar_s'] * 1000:+.0f} ms{'' if res['ok'] else ', ragu'})"
        else:
            label = "SYNC gagal"
        self.marker(label)
        self.syncs.append(res)
        if self.recorder:
            self.recorder.add_sync(res)
        self.sync = {"active": False, "result": res}
        self._events.append({"type": "sync", "sync": self.sync})
        log.info("sync: %s", res)

    # -- CASS Wellness ---------------------------------------------------
    def start_cass_send(self) -> None:
        if self._cass_task and not self._cass_task.done():
            return
        self._cass_task = asyncio.create_task(self._cass_send())

    async def _cass_send(self) -> None:
        rec = self.last_recording
        self.cass = {"busy": True, "step": "menyiapkan berkas"}
        self._events.append({"type": "cass", "cass": self.cass})
        try:
            if self.recorder:
                raise cass.CassError("hentikan rekaman dulu")
            if not rec:
                raise cass.CassError("belum ada rekaman di sesi ini")
            zip_path = await asyncio.to_thread(cass.export_session, Path(rec["dir"]))
            self.cass = {"busy": True, "step": "mengirim ke CASS Wellness", "zip": str(zip_path)}
            self._events.append({"type": "cass", "cass": self.cass})
            res = await cass.upload(zip_path, self.cass_url)
            self.cass = {"busy": False, "ok": True, "zip": str(zip_path), "dir": rec["dir"], "result": res}
        except cass.CassError as e:
            self.cass = {"busy": False, "ok": False, "error": str(e), **({"zip": self.cass["zip"]} if "zip" in self.cass else {})}
        except Exception as e:  # noqa: BLE001
            log.exception("CASS transfer failed")
            self.cass = {"busy": False, "ok": False, "error": f"{type(e).__name__}: {e}"}
        log.info("CASS: %s", self.cass)
        self._events.append({"type": "cass", "cass": self.cass})

    # -- data out ----------------------------------------------------------
    def hello(self) -> dict:
        return {
            "type": "hello",
            "streams": STREAMS,
            "status": self.status,
            "recording": self.recorder.info() if self.recorder else self.last_recording,
            "sync": self.sync,
            "cass": {**self.cass, "url": self.cass_url},
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
