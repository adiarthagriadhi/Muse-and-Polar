"""EEG CSV files from other sources: Mind Monitor, muselsl, OpenBCI, the earlier app, generic 10-20 CSV."""

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

T = 90.0
MUSE = ["TP9", "AF7", "AF8", "TP10"]


def eeg(t, k, closed, rng):
    alpha = np.where(closed, 14, 4)
    return alpha * np.sin(2 * np.pi * (10 + 0.3 * k) * t + k) + 2 * np.sin(2 * np.pi * 20 * t) + 3 * rng.standard_normal(len(t))


def write_all(root: Path) -> Path:
    rng = np.random.default_rng(3)
    root.mkdir(parents=True, exist_ok=True)
    fs = 256
    t = np.arange(0, T, 1 / fs)
    closed = t >= 45
    # Mind Monitor: date-time stamps rounded to ms, RAW_* plus band columns, markers in Elements
    start = datetime(2026, 9, 20, 8, 15, 0)
    stamp = lambda s: (start + timedelta(seconds=float(s))).strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]  # noqa: E731
    mm = pd.DataFrame({"TimeStamp": [stamp(x) for x in t]})
    for k, c in enumerate(MUSE):
        mm[f"Delta_{c}"] = 0.5
        mm[f"RAW_{c}"] = 800 + eeg(t, k, closed, rng)
    mm["Elements"] = ""
    ev = pd.DataFrame({"TimeStamp": [stamp(20), stamp(45), stamp(46)],
                       "Elements": ["/muse/elements/blink", "/Marker/1", "/muse/elements/jaw_clench"]})
    pd.concat([mm, ev]).sort_values("TimeStamp", kind="stable").to_csv(root / "mindMonitor.csv", index=False)
    # muselsl
    pd.DataFrame({"timestamps": 1.79e9 + t, **{c: eeg(t, k, closed, rng) for k, c in enumerate(MUSE)},
                  "Right AUX": 0.0}).to_csv(root / "muselsl.csv", index=False)
    # OpenBCI GUI (.txt, % header, 16 channels at 125 Hz)
    t2 = np.arange(0, T, 1 / 125)
    ob = pd.DataFrame({"Sample Index": np.arange(len(t2)) % 256,
                       **{f" EXG Channel {k}": eeg(t2, k, t2 >= 45, rng) for k in range(16)}, " Timestamp": 1.79e9 + t2})
    (root / "OpenBCI-RAW.txt").write_text("%OpenBCI Raw EXG Data\n%Number of channels = 16\n%Sample Rate = 125 Hz\n"
                                          + ob.to_csv(index=False))
    # earlier research app layout
    d = root / "P05_Trial" / "experiment"
    d.mkdir(parents=True)
    pd.DataFrame({"Timestamp_LSL": 5000 + t, **{f"EEG_{c}": eeg(t, k, closed, rng) for k, c in enumerate(MUSE)}}
                 ).to_csv(d / "EEG_raw.csv", index=False)
    tp = np.arange(0, T, 1 / 64)
    w = 2 * np.pi * 1.1 * tp
    pd.DataFrame({"Timestamp_LSL": 5000 + tp, "PPG_1": 1000.0, "PPG_2": 2e5 + 2000 * (np.sin(w) + 0.4 * np.sin(2 * w + 1)),
                  "PPG_3": 1.5e5}).to_csv(d / "PPG_raw.csv", index=False)
    (d / "recording_metadata.json").write_text(json.dumps({"start_iso": "2026-03-02T10:00:00", "duration_sec": T}))
    # generic 10-20 CSV: semicolons, time in ms, ECG and a marker column
    t3 = np.arange(0, T, 1 / 250)
    g = pd.DataFrame({"Time (ms)": t3 * 1000})
    for k, c in enumerate(["Fp1", "Fp2", "F3", "F4", "C3", "C4", "O1", "O2"]):
        g[c] = eeg(t3, k, (t3 >= 45) if c[0] == "O" else np.zeros(len(t3), bool), rng)
    beats = np.arange(0.4, T, 60 / 66)
    g["ECG"] = sum(900 * np.exp(-((t3 - b) ** 2) / (2 * 0.012 ** 2)) for b in beats) + 10 * rng.standard_normal(len(t3))
    g["Marker"] = ""
    g.loc[int(45 * 250), "Marker"] = "mata tertutup"
    g.to_csv(root / "generic_8ch.csv", index=False, sep=";")
    return root


@pytest.fixture(scope="module")
def csvdir(tmp_path_factory):
    return write_all(tmp_path_factory.mktemp("csv") / "rec")


def by_label(root):
    return {r["label"]: r for r in list_recordings(root)}


def test_listing_recognises_every_layout(csvdir):
    recs = by_label(csvdir)
    assert set(recs) == {"mindMonitor.csv", "muselsl.csv", "OpenBCI-RAW.txt", "P05_Trial / experiment", "generic_8ch.csv"}
    assert recs["P05_Trial / experiment"]["kind"] == "lsl" and recs["OpenBCI-RAW.txt"]["n_channels"] == 16
    assert recs["generic_8ch.csv"]["has_heart"] and not recs["muselsl.csv"]["has_heart"]


def test_mind_monitor(csvdir):
    s = Session(csvdir / "mindMonitor.csv")
    ov = s.overview()
    assert s.ch == MUSE and s.fs == 256  # ms-rounded stamps would give 250 without snapping
    assert ov["marker_titik"] == "45" and ov["start"] == "2026-09-20T08:15:00"  # blink/jaw events ignored
    res = s.analyze("45", "alpha")
    assert res["segments"][1]["values"][1] > 5 * res["segments"][0]["values"][1]


def test_muselsl_openbci_and_earlier_app(csvdir):
    m = Session(csvdir / "muselsl.csv")
    assert m.ch == MUSE and m.fs == 256 and m.pair_label == "AF"
    o = Session(csvdir / "OpenBCI-RAW.txt")
    assert o.nch == 16 and o.fs == 125 and o.ch[0] == "EXG Channel 0" and o.pair is None
    assert o.overview()["positions"] == {}
    lsl = Session(csvdir / "P05_Trial" / "experiment")
    ov = lsl.overview()
    assert lsl.ch == MUSE and ov["kind"] == "lsl" and ov["start"] == "2026-03-02T10:00:00"
    assert ov["hrv"]["ppg"]["hr"] == pytest.approx(66, abs=1)


def test_generic_csv_with_ecg_and_markers(csvdir):
    s = Session(csvdir / "generic_8ch.csv")
    ov = s.overview()
    assert s.fs == 250 and s.pair == ("F3", "F4") and ov["marker_titik"] == "45"
    assert ov["hrv"]["polar"]["hr"] == pytest.approx(66, abs=1) and ov["heart_name"] == "EKG (CSV)"
    res = s.analyze("45")
    o1 = s.ch.index("O1")
    assert res["segments"][1]["values"][o1] > 5 * res["segments"][0]["values"][o1]
    # no temporal electrodes (T7/P7/TP7): the Muse-like view cannot be built and the channels stay as they are
    assert ov["options"]["muse4"] is None and s.view("muse4").ch == s.ch


def test_low_rate_csv_is_rejected(tmp_path):
    # Mind Monitor with "Recording Interval = 1 second" (averaged values instead of raw EEG)
    stamps = [(datetime(2026, 1, 1) + timedelta(seconds=k)).strftime("%Y-%m-%d %H:%M:%S.000") for k in range(120)]
    pd.DataFrame({"TimeStamp": stamps, "RAW_TP9": 800.0, "RAW_AF7": 801.0, "RAW_AF8": 802.0, "RAW_TP10": 803.0}
                 ).to_csv(tmp_path / "x.csv", index=False)
    with pytest.raises(Exception, match="terlalu rendah"):
        Session(tmp_path / "x.csv")


def test_server_csv_upload(csvdir):
    pytest.importorskip("fastapi")
    try:
        from fastapi.testclient import TestClient
    except (ImportError, RuntimeError):
        pytest.skip("TestClient dependencies not installed")
    import server

    client = TestClient(server.app)
    r = client.post("/api/upload", files={"file": ("muselsl.csv", (csvdir / "muselsl.csv").read_bytes())})
    assert r.status_code == 200 and r.json()["sessions"][0]["kind"] == "csv"


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js not installed")
def test_browser_engine_reads_the_same_csv(csvdir):
    run = """
const fs = require('fs'); const E = require(process.argv[1]); const I = E._internals;
const out = {};
for (const p of process.argv.slice(2)) {
  const s = new I.Session(I.recordingFromCSV(fs.readFileSync(p, 'utf8'), require('path').basename(p), 'r'));
  const ov = s.overview(); const a = s.analyze(ov.marker_titik || '45', 'alpha');
  out[require('path').basename(p)] = { fs: ov.fs, ch: ov.channels, mk: ov.marker_titik, start: ov.start,
    refs: a.segments.map((g) => g.is_ref), values: a.segments.map((g) => g.values) };
}
process.stdout.write(JSON.stringify(out));
"""
    names = ["mindMonitor.csv", "muselsl.csv", "OpenBCI-RAW.txt", "generic_8ch.csv"]
    js = json.loads(subprocess.run(["node", "-e", run, str(RESEARCH / "web" / "engine.js"), *[str(csvdir / n) for n in names]],
                                   capture_output=True, text=True, check=True).stdout)
    for n in names:
        s = Session(csvdir / n)
        ov = s.overview()
        a = s.analyze(ov["marker_titik"] or "45", "alpha")
        j = js[n]
        assert j["fs"] == s.fs and j["ch"] == s.ch and j["mk"] == ov["marker_titik"] and j["start"] == ov["start"]
        assert j["refs"] == [g["is_ref"] for g in a["segments"]]
        np.testing.assert_allclose([[v or 0 for v in g["values"]] for g in a["segments"]],
                                   [[v or 0 for v in vs] for vs in j["values"]], rtol=2e-3)
