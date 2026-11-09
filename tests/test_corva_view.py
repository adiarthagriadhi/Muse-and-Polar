"""CorVa Space v0.3: page, JSON and CSV routes, and the dashboard button."""

import asyncio
import csv
import io
import json
import re

import pytest
from aiohttp.test_utils import TestClient, TestServer

from corva.routes import corva_sessions
from corva.session import PHASE_COLUMNS, WINDOW_COLUMNS, analyze_session, phases_csv, windows_csv
from corva.view import build_html
from musepolar.hub import Hub
from musepolar.server import build_app
from test_corva_session import _write_session

SID = "2026-11-09_100000_corva_uji"
PRE = "2026-11-08_100000_corva_sebelum"


@pytest.fixture(scope="module")
def data_dir(tmp_path_factory):
    root = tmp_path_factory.mktemp("rec")
    d = _write_session(root / SID)
    (d / "session.json").write_text(json.dumps({"name": "corva uji"}))
    _write_session(root / PRE, seed=4, theta_boost=True)
    plain = _write_session(root / "2026-11-09_090000_tanpa_protokol", seed=2)
    (plain / "marker.csv").write_text("timestamp,label\n1700000001,Baseline mulai\n")
    return root


@pytest.fixture(scope="module")
def result(data_dir):
    return analyze_session(data_dir / SID)


def _embedded(html):
    m = re.search(r'<script id="corva-data" type="application/json">(.*?)</script>', html, re.S)
    return json.loads(m.group(1).replace("<\\/", "</"))


def test_page_embeds_result_and_citations(result):
    html = build_html(result, [{"id": SID, "name": "corva uji"}], SID)
    data = _embedded(html)
    assert data["result"]["summary"] == result["summary"] and data["current"] == SID
    assert set(data["cells"]) >= {"Q1", "Q2", "Q3", "Q4", "NEUTRAL", "NO_DATA"}
    assert [p["num"] for p in data["protocol"]] == [1, 2, 3, 4, 5]
    assert "hopkins2009" in data["cites"] and data["cites"]["hopkins2009"]["cite"]
    assert data["result"]["conclusions"]["items"][0]["id"] == "relax_typical"
    assert all(k in data["cites"] for i in data["result"]["conclusions"]["items"] for k in i["refs"])


def test_page_is_split_into_screens(result):
    """One screen per page with tabs and a pager, not one long scroll (print shows every page)."""
    html = build_html(result, [{"id": SID, "name": "corva uji"}], SID)
    pages = re.findall(r'<section class="page" id="([a-z]+)" data-title="([^"]+)"', html)
    assert [p for p, _ in pages] == ["kesimpulan", "perbandingan", "peta", "fase", "lintasan", "tabel", "metode", "rujukan"]
    assert 'id="tabs"' in html and 'id="prevPage"' in html and 'id="nextPage"' in html
    assert "overflow: hidden" in html and ".page.active { display: block" in html
    assert ".page { display: block !important; break-before: page; }" in html  # print: all pages
    assert "if (!D.comparison) $('perbandingan').remove();" in html


def test_page_data_cannot_break_out_of_script(result):
    evil = "</script><script>alert(1)</script>"
    html = build_html(result, [{"id": SID, "name": evil}], SID)
    assert evil not in html
    assert _embedded(html)["sessions"][0]["name"] == evil


def test_csv_exports(result):
    rows = list(csv.DictReader(io.StringIO(phases_csv(result))))
    assert list(rows[0]) == PHASE_COLUMNS and [r["id"] for r in rows] == [p["id"] for p in result["phases"]]
    assert rows[4]["code"] == "Q2" and rows[4]["comparison"] == "sesuai harapan"
    win = list(csv.DictReader(io.StringIO(windows_csv(result))))
    assert list(win[0]) == WINDOW_COLUMNS and len(win) == len(result["windows"])


def test_only_sessions_with_protocol_markers_are_listed(data_dir):
    assert [s["id"] for s in corva_sessions(data_dir)] == [SID, PRE]


def test_routes(data_dir):
    async def run():
        client = TestClient(TestServer(build_app(Hub(data_dir), {})))
        await client.start_server()
        try:
            r = await client.get("/corva", allow_redirects=False)
            assert r.status == 302 and r.headers["Location"] == f"/corva/session/{SID}"
            r = await client.get(f"/corva/session/{SID}")
            html = await r.text()
            assert r.status == 200 and "CorVa Space" in html and _embedded(html)["current"] == SID
            r = await client.get(f"/api/corva/analysis/{SID}")
            assert r.status == 200 and (await r.json())["summary"]["n_as_expected"] == 4
            r = await client.get(f"/api/corva/export/{SID}?level=windows")
            assert r.status == 200 and "attachment" in r.headers["Content-Disposition"]
            assert (await r.text()).startswith(",".join(WINDOW_COLUMNS))
            assert (await client.get(f"/api/corva/export/{SID}?level=x")).status == 400
            assert (await client.get("/api/corva/sessions")).status == 200
            # a recording without the protocol: readable error page, not a crash
            r = await client.get("/corva/session/2026-11-09_090000_tanpa_protokol")
            assert r.status == 422 and "tidak ditemukan" in await r.text()
            assert (await client.get("/api/corva/analysis/..")).status in (400, 404)
            # comparison with an earlier session (D-19)
            r = await client.get(f"/corva/session/{SID}?pre={PRE}")
            cmp = _embedded(await r.text())["comparison"]
            assert r.status == 200 and cmp["pre"] == PRE and cmp["post"] == SID and cmp["table"]
            r = await client.get(f"/corva/session/{SID}?pre=tidak_ada")
            assert r.status == 200 and _embedded(await r.text())["comparison"]["error"]
            r = await client.get(f"/api/corva/compare?pre={PRE}&post={SID}")
            assert r.status == 200 and (await r.json())["summary"]
            r = await client.get(f"/api/corva/export/{SID}?level=conclusions&pre={PRE}")
            text = await r.text()
            assert r.status == 200 and "sesi," in text and "perbandingan," in text
            page = await (await client.get("/")).text()
            assert 'id="corvaShow"' in page
        finally:
            await client.close()

    asyncio.run(run())
