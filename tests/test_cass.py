"""CASS Wellness export format and upload against a stub server."""

import asyncio
import csv
import io
import json
import zipfile

from aiohttp import web
from aiohttp.test_utils import TestServer

from musepolar import cass
from musepolar.hub import Hub
from musepolar.recorder import Recorder


def make_recording(tmp_path):
    rec = Recorder(tmp_path, name="P07 pagi", note="uji")
    rec.write("muse_eeg", [1000.0, 1000.004], [[1.5, 2.0, 3.0, 4.0], [5.0, 6.0, 7.0, 8.0]])
    rec.write("muse_ppg", [1000.0, 1000.016], [[10, 20, 30], [11, 21, 31]])
    rec.write("polar_rr", [1000.5], [[812.0]])
    rec.close()
    return rec.dir


def test_export_session(tmp_path):
    folder = make_recording(tmp_path)
    path = cass.export_session(folder)
    assert path.parent == folder and path.suffix == ".zip"
    with zipfile.ZipFile(path) as z:
        assert {"EEG_raw.csv", "PPG_raw.csv", "recording_metadata.json", "polar_rr.csv"} <= set(z.namelist())
        eeg = list(csv.reader(io.StringIO(z.read("EEG_raw.csv").decode())))
        ppg = list(csv.reader(io.StringIO(z.read("PPG_raw.csv").decode())))
        meta = json.loads(z.read("recording_metadata.json"))
    assert eeg[0] == ["Timestamp_LSL", "EEG_TP9", "EEG_AF7", "EEG_AF8", "EEG_TP10"]
    assert eeg[1] == ["1000.000000", "1.5", "2.0", "3.0", "4.0"] and len(eeg) == 3
    assert ppg[0] == ["Timestamp_LSL", "PPG_1", "PPG_2", "PPG_3"] and ppg[2][2] == "21"  # PPG_2 = IR
    assert meta["participant"] == "P07_pagi" and meta["recording_type"] == "experiment"
    assert meta["start_iso"] != "unknown"


def test_export_needs_eeg_and_ppg(tmp_path):
    rec = Recorder(tmp_path, name="polar saja")
    rec.write("polar_rr", [1.0], [[800.0]])
    rec.close()
    try:
        cass.export_session(rec.dir)
    except cass.CassError as e:
        assert "muse_eeg" in str(e)
    else:
        raise AssertionError("expected CassError")


def test_hub_sends_to_cass(tmp_path):
    received = {}

    async def upload(request):
        form = await request.post()
        received["fields"] = {k: form[k] for k in ("marker", "ruas", "prv")}
        received["zip"] = form["file"].file.read()
        return web.json_response({
            "n_sessions": 1, "sessions": [{"session_id": "P07_pagi_experiment", "n_windows": 10, "n_y_valid": 8}],
            "problems": [], "html": "Wellness_Explorer_x.html", "html_url": "/out/Wellness_Explorer_x.html",
        })

    async def listing(_request):
        return web.json_response({"files": []})

    async def run():
        app = web.Application()
        app.router.add_post("/api/upload", upload)
        app.router.add_get("/api/list", listing)
        server = TestServer(app)
        await server.start_server()
        base = str(server.make_url("/"))
        try:
            assert await cass.is_running(base)
            hub = Hub(tmp_path, cass_url=base)
            hub.last_recording = {"dir": str(make_recording(tmp_path)), "active": False}
            hub.start_cass_send()
            await hub._cass_task
            return hub.cass, base
        finally:
            await server.close()

    state, base = asyncio.run(run())
    assert state["ok"], state
    assert state["result"]["html_url"] == base.rstrip("/") + "/out/Wellness_Explorer_x.html"
    assert received["fields"] == {"marker": "", "ruas": "30", "prv": "20"}
    assert zipfile.ZipFile(io.BytesIO(received["zip"])).namelist()[0] == "EEG_raw.csv"


def test_cass_not_running(tmp_path):
    async def run():
        hub = Hub(tmp_path, cass_url="http://127.0.0.1:9/")
        hub.last_recording = {"dir": str(make_recording(tmp_path)), "active": False}
        assert not await cass.is_running(hub.cass_url)
        hub.start_cass_send()
        await hub._cass_task
        return hub.cass

    state = asyncio.run(run())
    assert state["ok"] is False and "jalankan.sh" in state["error"] and state["zip"].endswith(".zip")
