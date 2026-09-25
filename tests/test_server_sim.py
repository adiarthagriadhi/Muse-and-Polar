"""End-to-end: run the server with simulated devices, drive it over the websocket."""

import asyncio
import json
from types import SimpleNamespace

from aiohttp.test_utils import TestClient, TestServer

from musepolar.hub import Hub
from musepolar.server import build_app, make_slots
from musepolar.simulator import SIM_MUSE_LAG


def test_sim_end_to_end(tmp_path):
    async def run():
        hub = Hub(tmp_path)
        args = SimpleNamespace(sim=True)
        slots = make_slots(hub, args)
        broadcaster = asyncio.create_task(hub.broadcast_loop())
        client = TestClient(TestServer(build_app(hub, slots)))
        await client.start_server()
        try:
            page = await client.get("/")
            assert page.status == 200 and "Muse" in await page.text()
            assert (await client.get("/static/app.js")).status == 200

            ws = await client.ws_connect("/ws")
            hello = json.loads((await ws.receive()).data)
            assert hello["type"] == "hello" and "muse_eeg" in hello["streams"]

            for dev in ("muse", "polar"):
                await ws.send_json({"cmd": "connect", "device": dev})
            await ws.send_json({"cmd": "record_start", "name": "sim"})
            await asyncio.sleep(1.0)
            await ws.send_json({"cmd": "marker", "label": "Mata tertutup"})
            await ws.send_json({"cmd": "sync", "duration": 8})

            seen, metrics = set(), None
            loop = asyncio.get_running_loop()
            sync = None
            end = loop.time() + 12
            while loop.time() < end and not (sync and not sync["active"]):
                msg = json.loads((await ws.receive(timeout=2)).data)
                if msg["type"] == "data":
                    seen |= set(msg["streams"])
                elif msg["type"] == "metrics":
                    metrics = msg
                elif msg["type"] == "sync":
                    sync = msg["sync"]
            await ws.send_json({"cmd": "record_stop"})
            for dev in ("muse", "polar"):
                await ws.send_json({"cmd": "disconnect", "device": dev})
            await asyncio.sleep(0.3)
            await ws.close()

            assert {"muse_eeg", "muse_ppg", "muse_acc", "polar_ecg", "polar_acc", "polar_hr", "marker"} <= seen
            res = sync["result"]
            assert res["ok"], res
            assert abs(res["muse_minus_polar_s"] - SIM_MUSE_LAG) < 0.015
            assert metrics["eeg"] is not None
            assert hub.status["muse"]["state"] == "disconnected"
            assert hub.last_recording and not hub.last_recording["active"]
            session = next(tmp_path.iterdir())
            files = {p.name for p in session.iterdir()}
            assert {"session.json", "muse_eeg.csv", "polar_ecg.csv", "polar_rr.csv", "marker.csv"} <= files
            meta = json.loads((session / "session.json").read_text())
            assert len(meta["sync"]) == 1 and meta["sync"][0]["ok"]
            assert (session / "polar_acc.csv").read_text().startswith("timestamp,x,y,z,sensor_ns")
            eeg_lines = (session / "muse_eeg.csv").read_text().count("\n")
            assert eeg_lines > 256 * 3  # ~4 s of 256 Hz
        finally:
            await client.close()
            broadcaster.cancel()

    asyncio.run(run())
