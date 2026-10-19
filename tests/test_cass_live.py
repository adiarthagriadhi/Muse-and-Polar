"""Dashboard CASS flow: record (simulator) → export ZIP into the session → CASS analysis."""

import asyncio
import io
import zipfile

from aiohttp.test_utils import TestClient, TestServer

from musepolar.hub import Hub
from musepolar.server import build_app
from musepolar.simulator import SimMuse, SimPolar


def test_export_and_analysis_from_recording(tmp_path):
    async def run():
        hub = Hub(tmp_path)
        stop = asyncio.Event()
        tasks = [asyncio.create_task(dev.run(stop)) for dev in (SimMuse(hub), SimPolar(hub))]
        client = TestClient(TestServer(build_app(hub, {})))
        await client.start_server()
        try:
            await asyncio.sleep(1.0)
            hub.start_recording("cass uji")
            await asyncio.sleep(32)
            info = hub.stop_recording()
            stop.set()
            await asyncio.gather(*tasks)
            sid = info["dir"].rsplit("/", 1)[-1]

            listing = await (await client.get("/api/cass/sessions")).json()
            assert [s["id"] for s in listing["sessions"]] == [sid]

            saved = await client.post(f"/api/cass/export/{sid}")
            assert saved.status == 200
            zpath = (await saved.json())["zip"]
            names = set(zipfile.ZipFile(zpath).namelist())
            assert {"muse_eeg.csv", "muse_ppg.csv", "polar_rr.csv", "session.json", "cass_polar_export.json"} <= names
            dl = await client.get(f"/api/cass/export/{sid}")
            assert set(zipfile.ZipFile(io.BytesIO(await dl.read())).namelist()) == names

            assert (await client.get(f"/cass/session/{sid}")).status == 200
            res = await client.get(f"/api/cass/analysis/{sid}?r0=12")
            payload = await res.json()
            assert res.status == 200, payload
            assert payload["autonomic_scalar"] == "polar_rr_rmssd" and payload["n_windows"] > 5
            assert payload["n_valid"] > 0

            bad = await client.post("/api/cass/export/..")
            assert bad.status in (400, 404)
        finally:
            await client.close()

    asyncio.run(run())
