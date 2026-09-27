"""EDF / EDF+ input and multi-channel (e.g. 16-channel 10-20) recordings."""

import io
import sys
import zipfile
from pathlib import Path

import pytest

np = pytest.importorskip("numpy")
pytest.importorskip("pandas")
pytest.importorskip("scipy")

RESEARCH = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RESEARCH / "src"))
sys.path.insert(0, str(RESEARCH / "app"))

from muse2_pipeline.analysis import Session  # noqa: E402
from muse2_pipeline.edf import read_edf, write_edf  # noqa: E402
from muse2_pipeline.io import list_recordings  # noqa: E402
from muse2_pipeline.montage import canonical, frontal_pair, positions, regions  # noqa: E402

CAP16 = ["Fp1", "Fp2", "F3", "F4", "C3", "C4", "P3", "P4", "O1", "O2", "F7", "F8", "T3", "T4", "T5", "T6"]


def make_edf(path: Path, dur=180.0, fs=250, labels=None, ecg=True, prefix="EEG ", suffix="-REF") -> Path:
    """Rest (0–60 s) → eyes closed: posterior alpha up, HR down → task: frontal beta up, HR up."""
    rng = np.random.default_rng(5)
    t = np.arange(0, dur, 1 / fs)
    sig = {}
    for k, lab in enumerate(labels or CAP16):
        post = lab[0] in "OP" or lab in ("T5", "T6")
        alpha = np.where((t >= 60) & (t < 120), 20 if post else 6, 5 if post else 3)
        beta = np.where(t >= 120, 5 if lab[0] == "F" else 2.5, 2.0)
        x = alpha * np.sin(2 * np.pi * (10 + 0.1 * k) * t + k) + beta * np.sin(2 * np.pi * 21 * t + k)
        sig[f"{prefix}{lab}{suffix}"] = (fs, x + 4 * rng.standard_normal(len(t)))
    if ecg:
        beats = [0.4]
        while beats[-1] < dur:
            tb = beats[-1]
            beats.append(tb + 60 / (70 if tb < 60 else 62 if tb < 120 else 82))
        e = np.zeros(len(t))
        for b in beats:
            e += 1000 * np.exp(-((t - b) ** 2) / (2 * 0.012 ** 2)) - 150 * np.exp(-((t - b - 0.2) ** 2) / (2 * 0.04 ** 2))
        sig["ECG"] = (fs, e + 20 * rng.standard_normal(len(t)))
    write_edf(path, sig, annotations=[(60.0, "Mata tertutup"), (120.0, "Aritmetika")],
              patient="S01 M X Subjek_16kanal")
    return path


def test_labels_and_positions():
    assert canonical("EEG Fp1-REF") == "Fp1" and canonical("FP2") == "Fp2" and canonical("EEG T3-A1") == "T7"
    assert canonical("T5") == "P7" and canonical("EEG CZ-LE") == "Cz"
    assert canonical("Fp1-F7") is None and canonical("ECG") is None and canonical("Status") is None
    ch = [canonical(l) for l in CAP16]
    pos = positions(ch)
    assert len(pos) == 16
    assert pos["Fp1"][0] < 0 < pos["Fp2"][0] and pos["Fp1"][1] > pos["C3"][1] > pos["O1"][1]  # left/right, front/back
    assert all(x * x + y * y < 1 for x, y in pos.values())
    assert frontal_pair(ch) == ("F3", "F4") and frontal_pair(["TP9", "AF7", "AF8", "TP10"]) == ("AF7", "AF8")
    assert set(regions(ch)) == {"Frontal", "Sentral", "Temporal", "Parietal", "Oksipital"}
    # Muse keeps its compact layout
    assert positions(["TP9", "AF7", "AF8", "TP10"])["AF7"] == (-0.5, 0.48)


def test_edf_roundtrip(tmp_path):
    t = np.arange(0, 10, 1 / 256)
    x = 50 * np.sin(2 * np.pi * 10 * t)
    write_edf(tmp_path / "a.edf", {"EEG Cz": (256, x), "EEG Pz": (256, x / 1000)},
              annotations=[(2.5, "start"), (7.0, "stop")], dims={"EEG Pz": "mV"})
    d = read_edf(tmp_path / "a.edf")
    fs, v = d["signals"]["EEG Cz"]
    assert fs == 256 and len(v) == len(x) and np.max(np.abs(v - x)) < 0.01
    assert d["annotations"] == [(2.5, "start"), (7.0, "stop")] and d["edfplus"]
    assert d["dims"][1] == "mV"


def test_session_from_16_channel_edf(tmp_path):
    s = Session(make_edf(tmp_path / "cap.edf"))
    assert s.nch == 16 and s.fs == 250 and s.pair == ("F3", "F4") and "T7" in s.ch
    ov = s.overview()
    assert ov["kind"] == "edf" and ov["marker_titik"] == "60, 120" and len(ov["positions"]) == 16
    assert ov["heart_name"] == "EKG (EDF)" and ov["hrv"]["polar"]["hr"] == pytest.approx(71, abs=2)
    res = s.analyze(ov["marker_titik"], "alpha")
    segs = res["segments"]
    o1 = s.ch.index("O1")
    assert segs[1]["values"][o1] > 5 * segs[0]["values"][o1]  # eyes closed: occipital alpha
    assert segs[1]["polar"]["hr"] == pytest.approx(62, abs=1.5) and segs[2]["polar"]["hr"] == pytest.approx(82, abs=2)
    assert segs[1]["name"] == "Mata tertutup" and res["pair_label"] == "F3/F4"
    assert res["measures"][0] == "F3+F4" and res["measures"][-1] == "Asimetri F3/F4" and len(res["measures"]) == 18
    row = next(r for r in res["tests"]["pairs"] if r["measure"] == "O1" and r["a"] == 0 and r["b"] == 1)
    assert row["sig"] and row["delta"] == 1.0
    assert len(res["bad"][0]) == 16


def test_edf_without_1020_names(tmp_path):
    p = make_edf(tmp_path / "raw.edf", dur=40, labels=["Ch1", "Ch2", "Ch3"], ecg=False, prefix="", suffix="")
    s = Session(p)
    assert s.ch == ["Ch1", "Ch2", "Ch3"] and s.pair is None
    assert s.overview()["positions"] == {}
    res = s.analyze("20")
    assert res["measures"] == ["Rata-rata", "Ch1", "Ch2", "Ch3"] and len(res["segments"]) == 2


def test_listing_and_exports(tmp_path):
    from muse2_pipeline import report

    make_edf(tmp_path / "cap.edf", dur=60)
    rec = list_recordings(tmp_path)
    assert rec[0]["kind"] == "edf" and rec[0]["n_channels"] == 16 and rec[0]["name"] == "Subjek 16kanal"
    s = Session(tmp_path / "cap.edf")
    res = s.analyze("30")
    assert report.figure_png(s, res)[:4] == b"\x89PNG"
    assert report.report_docx(s, res)[:2] == b"PK"
    names = zipfile.ZipFile(io.BytesIO(report.export_zip(s, res, {}))).namelist()
    assert "denyut_polar.csv" in names  # EKG-derived intervals


def test_server_edf_upload(tmp_path):
    pytest.importorskip("fastapi")
    try:
        from fastapi.testclient import TestClient
    except (ImportError, RuntimeError):
        pytest.skip("TestClient dependencies not installed")
    import server

    server.STATE["default_root"] = tmp_path / "none"
    client = TestClient(server.app)
    data = make_edf(tmp_path / "cap.edf", dur=60).read_bytes()
    r = client.post("/api/upload", files={"file": ("cap.edf", data)})
    assert r.status_code == 200
    ses = r.json()["sessions"][0]
    assert ses["kind"] == "edf" and ses["n_channels"] == 16
    ov = client.get(f"/api/session/{ses['id']}").json()
    assert len(ov["channels"]) == 16
    sig = client.get(f"/api/signal/{ses['id']}", params={"t0": 0, "t1": 60, "n": 400}).json()
    assert len(sig["lo"]) == 16


def test_channel_mode_and_heart_sources(tmp_path):
    s = Session(make_edf(tmp_path / "cap.edf", dur=120))
    v4 = s.view("muse4", "all")
    assert v4.ch == ["T7", "Fp1", "Fp2", "T8"] and v4.muse_map["AF7"] == "Fp1" and v4.pair == ("Fp1", "Fp2")
    res = v4.analyze("60")
    assert len(res["segments"][0]["values"]) == 4 and len(res["bad"][0]) == 4 and res["measures"][0] == "Fp1+Fp2"
    assert v4.overview()["options"]["n_all"] == 16 and s.nch == 16  # the full session is untouched
    none = s.view("all", "none")
    assert none.analyze("60")["hr_source"] is None and none.overview()["hrv"]["polar"] is None
    assert s.view("all", "ecg").analyze("60")["hr_source"] == "polar"
    assert s.view("all", "all") is s


def test_server_channel_and_heart_params(tmp_path):
    pytest.importorskip("fastapi")
    try:
        from fastapi.testclient import TestClient
    except (ImportError, RuntimeError):
        pytest.skip("TestClient dependencies not installed")
    import server

    (tmp_path / "rec").mkdir()
    make_edf(tmp_path / "rec" / "cap.edf", dur=60)
    server.STATE["default_root"] = tmp_path / "rec"
    client = TestClient(server.app)
    sid = client.get("/api/sessions").json()["sessions"][0]["id"]
    ov = client.get(f"/api/session/{sid}", params={"chans": "muse4", "heart": "none"}).json()
    assert ov["channels"] == ["T7", "Fp1", "Fp2", "T8"] and ov["chans"] == "muse4" and ov["heart"] == "none"
    assert len(client.get(f"/api/signal/{sid}", params={"chans": "muse4", "t0": 0, "t1": 60}).json()["lo"]) == 4
    res = client.get(f"/api/analysis/{sid}", params={"chans": "muse4", "heart": "none", "titik": "30"}).json()
    assert res["channels"] == ["T7", "Fp1", "Fp2", "T8"] and res["hr_source"] is None
    doc = client.get(f"/api/report/{sid}", params={"chans": "muse4", "heart": "ppg", "titik": "30"})
    assert doc.status_code == 200 and doc.content[:2] == b"PK"
