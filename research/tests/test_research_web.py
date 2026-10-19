"""The browser build (web/engine.js) gives the same results as the Python pipeline."""

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

np = pytest.importorskip("numpy")
pytest.importorskip("scipy")

RESEARCH = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RESEARCH / "src"))
sys.path.insert(0, str(RESEARCH / "tests"))

from muse2_pipeline.analysis import Session  # noqa: E402

NODE = shutil.which("node")
RUN = """
const fs = require('fs'); const E = require(process.argv[1]); const I = E._internals;
const b = fs.readFileSync(process.argv[2]);
const s = new I.Session(I.recordingFromEDF(b.buffer.slice(b.byteOffset, b.byteOffset + b.length), 'cap.edf', 'r1'));
const out = { all: s.analyze('60,120', 'alpha', 'abs', 0, 100), muse: s.view('muse4', 'all').analyze('60,120', 'alpha', 'rel', 0, 100),
              ov: s.overview() };
process.stdout.write(JSON.stringify(out));
"""


@pytest.mark.skipif(NODE is None, reason="Node.js not installed")
def test_engine_matches_python(tmp_path):
    from test_research_edf import make_edf

    p = make_edf(tmp_path / "cap.edf", dur=150)
    js = json.loads(subprocess.run([NODE, "-e", RUN, str(RESEARCH / "web" / "engine.js"), str(p)],
                                   capture_output=True, text=True, check=True).stdout)
    s = Session(p)
    py = {"all": s.analyze("60,120", "alpha", "abs", 0, 100), "muse": s.view("muse4").analyze("60,120", "alpha", "rel", 0, 100)}
    assert js["ov"]["channels"] == s.ch and js["ov"]["marker_titik"] == "60, 120"
    for key in ("all", "muse"):
        a, b = py[key], js[key]
        assert a["channels"] == b["channels"] and a["measures"] == b["measures"]
        for ga, gb in zip(a["segments"], b["segments"]):
            assert ga["is_ref"] == gb["is_ref"] and ga["n_pair"] == gb["n_pair"]
            np.testing.assert_allclose([v or 0 for v in ga["values"]], [v or 0 for v in gb["values"]], rtol=2e-3)
            assert ga["polar"]["hr"] == pytest.approx(gb["polar"]["hr"], rel=1e-6)
        for ra, rb in zip(a["tests"]["pairs"], b["tests"]["pairs"]):
            assert ra["sig"] == rb["sig"] and (ra["p"] or 0) == pytest.approx(rb["p"] or 0, rel=1e-2, abs=1e-6)


def test_build_single_file(tmp_path):
    sys.path.insert(0, str(RESEARCH / "web"))
    import build

    art = tmp_path / "page.html"
    out = build.build(art)
    html = out.read_text(encoding="utf-8")
    assert "/static/" not in html and "window.ENGINE" in html and html.lstrip().startswith("<!doctype html>")
    page = art.read_text(encoding="utf-8")
    assert page.startswith("<title>Muse 2 Research View</title>") and "RV_ARTIFACT" in page
    assert "<body" not in page and "<!doctype" not in page.lower()
