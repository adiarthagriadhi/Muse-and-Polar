"""Polar Sensor Logger .txt files joined to EEG recordings by clock time."""

import json
import shutil
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pytest

np = pytest.importorskip("numpy")
pd = pytest.importorskip("pandas")
pytest.importorskip("scipy")

RESEARCH = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RESEARCH / "src"))
sys.path.insert(0, str(RESEARCH / "app"))

from muse2_pipeline.analysis import Session  # noqa: E402
from muse2_pipeline.io import list_recordings  # noqa: E402
from muse2_pipeline.polar import parse_rr  # noqa: E402

START = datetime(2026, 9, 20, 8, 15, 0)
PREFIX = "Polar_H10_A1B2C3D4_20260920_081440"


def write_polar(folder: Path, start=START, dur=90.0, lead=20.0, rr_file=True, ecg=True):
    """Polar Sensor Logger files starting `lead` s before `start`; HR 68 then 60 bpm after 45 s of EEG time."""
    t0 = start - timedelta(seconds=lead)
    beats = [0.5]
    while beats[-1] < dur + lead + 5:
        tb = beats[-1] - lead
        beats.append(beats[-1] + 60 / (68 if tb < 45 else 60) * (1 + 0.03 * np.sin(2 * np.pi * beats[-1] / 5)))
    beats = np.array(beats)
    rr = np.round(np.diff(beats) * 1000)
    iso = lambda s: (t0 + timedelta(seconds=float(s))).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3]  # noqa: E731
    if rr_file:
        lines, i = ["Phone timestamp;RR-interval [ms]"], 1
        while i < len(beats):  # packets of 1-2 intervals share the phone time of their last beat
            k = 2 if i % 3 == 0 and i + 1 < len(beats) else 1
            stamp = iso(beats[i + k - 1] + 0.03)
            lines += [f"{stamp};{rr[i - 1 + j]:.0f}" for j in range(k)]
            i += k
        (folder / f"{PREFIX}_RR.txt").write_text("\n".join(lines) + "\n")
    (folder / f"{PREFIX}_HR.txt").write_text("Phone timestamp;HR [bpm];HRV [ms];Breathing interval [rpm];\n" + iso(1) + ";70;0;0;\n")
    if ecg:
        fs = 130
        ts = np.arange(int((dur + lead) * fs)) / fs
        v = sum(1000 * np.exp(-((ts - b) ** 2) / (2 * 0.012 ** 2)) for b in beats)
        base = 599_000_000_000_000_000
        rows = [f"{iso((i // 73) * 73 / fs + 0.56)};{base + int(t * 1e9)};{t * 1000:.2f};{x:.0f}" for i, (t, x) in enumerate(zip(ts, v))]
        (folder / f"{PREFIX}_ECG.txt").write_text("Phone timestamp;sensor timestamp [ns];timestamp [ms];ecg [uV]\n" + "\n".join(rows) + "\n")
    (folder / f"{PREFIX}_MARKER.txt").write_text("Phone timestamp;Marker\n" + iso(lead + 30.0) + ";MARKER_START\n")
    return beats


def write_mind_monitor(folder: Path, start=START, dur=90.0):
    rng = np.random.default_rng(1)
    t = np.arange(0, dur, 1 / 256)
    df = pd.DataFrame({"TimeStamp": [(start + timedelta(seconds=float(x))).strftime("%Y-%m-%d %H:%M:%S.%f")[:-3] for x in t]})
    for k, c in enumerate(["TP9", "AF7", "AF8", "TP10"]):
        df[f"RAW_{c}"] = 800 + 5 * np.sin(2 * np.pi * 10 * t + k) + 3 * rng.standard_normal(len(t))
    df.to_csv(folder / "mindMonitor.csv", index=False)


def test_parse_rr_packets(tmp_path):
    beats = write_polar(tmp_path, ecg=False)
    rr = parse_rr((tmp_path / f"{PREFIX}_RR.txt").read_text())
    true_end = np.array([(START - timedelta(seconds=20)).timestamp() + b for b in beats[1:]])
    assert len(rr["t"]) == len(beats) - 1
    assert np.max(np.abs(rr["t"] - true_end)) < 0.05  # packet times spread back by RR


def test_join_by_clock_with_rr(tmp_path):
    write_polar(tmp_path)
    write_mind_monitor(tmp_path)
    assert [r["label"] for r in list_recordings(tmp_path)] == ["mindMonitor.csv"]  # Polar .txt are not EEG
    s = Session(tmp_path / "mindMonitor.csv")
    ov = s.overview()
    assert ov["polar_info"]["source"] == "RR" and ov["polar_info"]["aligned"] == "clock"
    assert ov["polar_info"]["start_diff_s"] == pytest.approx(-19.5, abs=0.1) and ov["heart_name"] == "Polar H10"
    assert "Polar: MARKER_START" in [m["label"] for m in ov["markers"]] and ov["marker_titik"] == "30"
    res = s.analyze("45")
    assert res["hr_source"] == "polar"
    assert res["segments"][0]["polar"]["hr"] == pytest.approx(68, abs=1) and res["segments"][1]["polar"]["hr"] == pytest.approx(60, abs=1)
    shifted = s.view("all", "all", 5.0)
    assert shifted.polar["t"][0] - s.polar["t"][0] == pytest.approx(5.0) and shifted.overview()["pshift"] == 5.0


def test_join_with_ecg_only(tmp_path):
    write_polar(tmp_path, rr_file=False)
    write_mind_monitor(tmp_path)
    ov = Session(tmp_path / "mindMonitor.csv").overview()
    assert ov["polar_info"]["source"] == "ECG" and ov["hrv"]["polar"]["hr"] == pytest.approx(64, abs=2)


def test_no_overlap_no_join(tmp_path):
    write_polar(tmp_path, start=START + timedelta(hours=3))
    write_mind_monitor(tmp_path)
    assert Session(tmp_path / "mindMonitor.csv").overview()["polar_info"] is None


def test_server_pshift(tmp_path):
    pytest.importorskip("fastapi")
    try:
        from fastapi.testclient import TestClient
    except (ImportError, RuntimeError):
        pytest.skip("TestClient dependencies not installed")
    import server

    write_polar(tmp_path, ecg=False)
    write_mind_monitor(tmp_path)
    server.STATE["default_root"] = tmp_path
    c = TestClient(server.app)
    sid = c.get("/api/sessions").json()["sessions"][0]["id"]
    ov = c.get(f"/api/session/{sid}", params={"pshift": 2.5}).json()
    assert ov["pshift"] == 2.5 and ov["polar_info"]["source"] == "RR"
    assert c.get(f"/api/analysis/{sid}", params={"pshift": 2.5, "titik": "45"}).json()["hr_source"] == "polar"


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js not installed")
def test_browser_engine_joins_the_same(tmp_path):
    write_polar(tmp_path, ecg=False)
    write_mind_monitor(tmp_path)
    run = """
const fs = require('fs'), path = require('path'); const E = require(process.argv[1]); const dir = process.argv[2];
const files = fs.readdirSync(dir).map((n) => ({ name: n, webkitRelativePath: 'd/' + n, text: async () => fs.readFileSync(path.join(dir, n), 'utf8') }));
(async () => {
  const r = await E.addFiles(files); const id = r.added[0];
  const ov = await E.handle(`/api/session/${id}`), a = await E.handle(`/api/analysis/${id}?titik=45`);
  process.stdout.write(JSON.stringify({ info: ov.polar_info, mk: ov.marker_titik, hr: a.segments.map((g) => g.polar.hr) }));
})();
"""
    js = json.loads(subprocess.run(["node", "-e", run, str(RESEARCH / "web" / "engine.js"), str(tmp_path)],
                                   capture_output=True, text=True, check=True).stdout)
    s = Session(tmp_path / "mindMonitor.csv")
    ov, res = s.overview(), s.analyze("45")
    assert js["info"] == ov["polar_info"] and js["mk"] == ov["marker_titik"]
    assert js["hr"] == pytest.approx([g["polar"]["hr"] for g in res["segments"]], rel=1e-9)
