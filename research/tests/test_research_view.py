"""Research View v2: heart beats, blink-aware band power, segment analysis and the web server."""

import io
import json
import sys
import zipfile
from pathlib import Path

import pytest

np = pytest.importorskip("numpy")
pd = pytest.importorskip("pandas")
pytest.importorskip("scipy")

RESEARCH = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RESEARCH / "src"))
sys.path.insert(0, str(RESEARCH / "app"))

from muse2_pipeline.analysis import Session, holm  # noqa: E402
from muse2_pipeline.eeg import subsegment_spectra, window_spectra  # noqa: E402
from muse2_pipeline.hrv import clean_ibi, hrv_stats, ppg_beats  # noqa: E402

T0 = 1_790_400_000.0
SYNC = 0.062


def make_session(root: Path, name="20260926_093000_demo", dur=180.0, blinks=True, polar=True) -> Path:
    """Rest (0–60 s) → eyes closed: alpha up, HR down (60–120 s) → task: beta up, HR up (120–180 s)."""
    d = root / name
    d.mkdir(parents=True)
    rng = np.random.default_rng(3)
    t = np.arange(0, dur, 1 / 256)
    alpha = np.select([t < 60, t < 120], [4.0, 12.0], 4.0)
    beta = np.where(t < 120, 2.0, 5.0)
    eeg = pd.DataFrame({"timestamp": T0 + t})
    for k, c in enumerate(["TP9", "AF7", "AF8", "TP10"]):
        x = alpha * np.sin(2 * np.pi * (10 + 0.3 * k) * t) + beta * np.sin(2 * np.pi * 20 * t) + 3 * rng.standard_normal(len(t))
        if blinks and c.startswith("AF"):
            for b in np.arange(2.5, dur, 5.0):
                if not 60 < b < 120:
                    x = x + 180 * np.exp(-((t - b) ** 2) / (2 * 0.08 ** 2))
        eeg[c] = x
    eeg.to_csv(d / "muse_eeg.csv", index=False)
    beats = [0.3]
    while beats[-1] < dur + 1:
        tb = beats[-1]
        hr = 68 if tb < 60 else 60 if tb < 120 else 84
        beats.append(tb + 60 / hr * (1 + 0.04 * np.sin(2 * np.pi * tb / 5)))
    beats = np.array(beats)
    tp = np.arange(0, dur, 1 / 64)
    w = 2 * np.pi * np.interp(tp, beats, np.arange(len(beats)))
    pd.DataFrame({"timestamp": T0 + tp, "ambient": 1000.0, "ir": 2e5 + 2000 * (np.sin(w) + 0.4 * np.sin(2 * w + 1)),
                  "red": 1.5e5}).to_csv(d / "muse_ppg.csv", index=False)
    if polar:
        rr = pd.DataFrame({"timestamp": T0 + beats[1:] - SYNC, "rr_ms": np.round(np.diff(beats) * 1000)})
        rr[rr.timestamp < T0 + dur].to_csv(d / "polar_rr.csv", index=False)
    pd.DataFrame({"timestamp": [T0 + 2, T0 + 60.3, T0 + 120.2],
                  "label": ["SYNC mulai", "Mata tertutup", "Aritmetika"]}).to_csv(d / "marker.csv", index=False)
    (d / "session.json").write_text(json.dumps({
        "name": "demo", "note": "", "start_local": "2026-09-26T09:30:00", "duration_sec": dur,
        "sync": [{"ok": True, "muse_minus_polar_s": SYNC, "start_unix": T0 + 2}]}))
    return d


# --- heart -------------------------------------------------------------------------

def test_ppg_beats_on_sharp_pulses():
    # narrow pulses with a flat baseline made the original MAD-prominence detector double count
    fs = 64
    t = np.arange(0, 60, 1 / fs)
    x = 2e5 + 3000 * sum(np.exp(-((t - b) ** 2) / (2 * 0.06 ** 2)) for b in np.arange(0.2, 60, 1.0))
    x += 20 * np.random.default_rng(0).standard_normal(len(t))
    st = hrv_stats(clean_ibi(ppg_beats(x, t)))
    assert st["ok"] and st["hr"] == pytest.approx(60, abs=1)


def test_clean_ibi_flags_missed_beat():
    ibi = np.full(30, 0.8)
    ibi[10] = 1.6  # a missed beat
    ser = clean_ibi(np.cumsum(ibi), ibi)
    assert not ser["valid"][10] and ser["valid"].sum() == 29
    st = hrv_stats(ser)
    assert st["hr"] == pytest.approx(75) and st["rmssd"] == pytest.approx(0, abs=1e-9)


def test_holm():
    adj = holm([0.01, 0.04, None, 0.03])
    assert adj[2] is None and adj[0] == pytest.approx(0.03) and adj[1] == pytest.approx(0.06) and adj[3] == pytest.approx(0.06)


# --- EEG -----------------------------------------------------------------------------

def test_blinks_only_remove_subsegments(tmp_path):
    s = Session(make_session(tmp_path))
    spec = window_spectra(s.sub, 100.0)
    af7 = 1
    # a blink every 5 s would reject every 4 s window if whole windows were dropped
    whole_window_rejected = (s.sub["max_abs"][:, af7] > 100).any()
    assert whole_window_rejected
    assert (~spec["bad"][:, af7]).mean() > 0.9
    # a stricter threshold keeps fewer clean sub-segments
    assert window_spectra(s.sub, 30.0)["n_clean"].sum() < spec["n_clean"].sum()


def test_subsegment_power_matches_sine():
    t = np.arange(0, 20, 1 / 256)
    df = pd.DataFrame({"time_s": t, **{c: 10 * np.sin(2 * np.pi * 10 * t) for c in ["TP9", "AF7", "AF8", "TP10"]}})
    sub = subsegment_spectra(df)
    # a 10 µV-amplitude sine has power A²/2 = 50 µV², all in the alpha band
    assert np.median(sub["power"]["alpha"]) == pytest.approx(50, rel=0.05)
    assert np.median(sub["power"]["beta"]) < 0.5


# --- segment analysis ---------------------------------------------------------------

def test_analysis_segments_labels_and_tests(tmp_path):
    s = Session(make_session(tmp_path))
    res = s.analyze("60,120", "alpha", "abs", ref=0, art_uv=100)
    segs = res["segments"]
    assert [g["code"] for g in segs][0] == "REFERENCE"
    # task: beta and heart rate up vs. rest. Which label wins depends on the original score
    # weights (alpha/beta enters Teraktivasi with a + sign), so only check the evidence here.
    assert segs[2]["code"] in ("ACTIVATED_HIGH_AROUSAL", "FOCUSED_ENGAGED")
    assert segs[2]["feat_z"]["beta"] > 1 and segs[2]["feat_z"]["hr"] > 1
    assert segs[1]["name"] == "Mata tertutup" and segs[2]["name"] == "Aritmetika"
    assert segs[1]["values"][1] > 5 * segs[0]["values"][1]  # alpha AF7 eyes closed
    assert segs[1]["polar"]["hr"] == pytest.approx(60, abs=1.5) and segs[2]["ppg"]["hr"] == pytest.approx(84, abs=2)
    assert res["hr_source"] == "polar"
    pairs = [r for r in res["tests"]["pairs"] if r["measure"] == "AF"]
    rest_closed = pairs[0]
    assert rest_closed["sig"] and rest_closed["delta"] == 1.0 and rest_closed["p_holm"] >= rest_closed["p"]
    assert rest_closed["n_b"] <= segs[1]["n_win"] // 2 + 1  # non-overlapping windows only
    assert {o["measure"] for o in res["tests"]["omnibus"]} >= {"AF", "AF7"}
    # relative power and another reference
    rel = s.analyze("60,120", "beta", "rel", ref=1)
    assert rel["unit"] == "%" and rel["segments"][1]["code"] == "REFERENCE"
    assert all(0 <= v <= 100 for g in rel["segments"] for v in g["values"] if v is not None)
    json.dumps(res)  # JSON-serialisable


def test_polar_sync_offset_applied(tmp_path):
    s = Session(make_session(tmp_path))
    assert s.sample["sync_offset"] == pytest.approx(SYNC)
    # RR timestamps were written as (true beat time − offset); the offset restores the true time
    first_beat = 0.3 + 60 / 68 * (1 + 0.04 * np.sin(2 * np.pi * 0.3 / 5))
    assert s.polar["t"][0] == pytest.approx(first_beat, abs=1e-3)


def test_single_segment_and_no_polar(tmp_path):
    s = Session(make_session(tmp_path, polar=False, blinks=False))
    res = s.analyze("", "theta")
    assert len(res["segments"]) == 1 and res["tests"]["pairs"] == []
    assert res["hr_source"] == "ppg" and res["segments"][0]["polar"] is None


# --- web server -------------------------------------------------------------------------

@pytest.fixture()
def client(tmp_path):
    pytest.importorskip("fastapi")
    pytest.importorskip("matplotlib")
    try:
        from fastapi.testclient import TestClient
    except (ImportError, RuntimeError):
        pytest.skip("TestClient dependencies not installed")
    import server

    make_session(tmp_path / "rec")
    server.STATE["default_root"] = tmp_path / "rec"
    return TestClient(server.app)


def test_server_endpoints(client):
    assert client.get("/").status_code == 200
    assert client.get("/static/app.js").status_code == 200
    lst = client.get("/api/sessions").json()
    assert lst["exists"] and len(lst["sessions"]) == 1 and lst["sessions"][0]["has_polar"]
    sid = lst["sessions"][0]["id"]
    ov = client.get(f"/api/session/{sid}").json()
    assert ov["marker_titik"] == "60, 120" and ov["sync_offset_ms"] == pytest.approx(62)
    res = client.get(f"/api/analysis/{sid}", params={"titik": "60,120", "band": "beta"}).json()
    assert len(res["segments"]) == 3 and len(res["bad"]) == len(ov["windows"]["t_mid"])
    assert client.get(f"/api/signal/{sid}", params={"t0": 0, "t1": 180, "n": 500}).json()["kind"] == "env"
    assert client.get(f"/api/signal/{sid}", params={"t0": 10, "t1": 12}).json()["kind"] == "raw"
    z = client.get(f"/api/export/{sid}", params={"titik": "60,120"})
    names = zipfile.ZipFile(io.BytesIO(z.content)).namelist()
    assert {"ruas.csv", "uji_berpasangan.csv", "jendela_dayapita.csv", "denyut_polar.csv"} <= set(names)
    doc = client.get(f"/api/report/{sid}", params={"titik": "60,120"})
    assert doc.status_code == 200 and doc.content[:2] == b"PK"
    assert client.get(f"/api/figure/{sid}").content[:4] == b"\x89PNG"
    assert client.get("/api/session/doesnotexist").status_code == 404


def test_server_upload_zip(client, tmp_path):
    d = make_session(tmp_path / "other", name="20260927_101010_zip", dur=40.0)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for p in d.rglob("*"):
            zf.write(p, p.relative_to(d.parent))
    r = client.post("/api/upload", files={"file": ("s.zip", buf.getvalue())})
    assert r.status_code == 200 and r.json()["sessions"][0]["label"] == d.name
    bad = client.post("/api/upload", files={"file": ("x.zip", b"not a zip")})
    assert bad.status_code == 400
