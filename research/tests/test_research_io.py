"""Research app reads sessions in the musepolar recording format."""

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

from muse2_pipeline import compute_prv_09, list_samples, load_sample, marker_titik, parse_marks, ruas_stats  # noqa: E402
from muse2_pipeline.io import unpack_zip  # noqa: E402

T0 = 1_758_790_000.0  # Unix time of the first EEG sample
PPG_LAG = 0.37  # PPG stream starts a bit later than EEG
DUR = 90.0


def make_session(root: Path, name="20260925_101500_subjek01", ppg=True, hr_hz=1.0) -> Path:
    d = root / name
    d.mkdir(parents=True)
    rng = np.random.default_rng(1)
    t = np.arange(0, DUR, 1 / 256)
    alpha = np.where(t < 45, 5.0, 15.0)
    eeg = pd.DataFrame({"timestamp": T0 + t})
    for c in ("TP9", "AF7", "AF8", "TP10"):
        eeg[c] = alpha * np.sin(2 * np.pi * 10 * t) + 5 * rng.standard_normal(len(t))
    eeg.to_csv(d / "muse_eeg.csv", index=False)
    if ppg:
        tp = np.arange(0, DUR - 1, 1 / 64)
        w = 2 * np.pi * hr_hz * tp  # continuous pulse wave with a dicrotic harmonic
        pulse = np.sin(w) + 0.4 * np.sin(2 * w + 1.0)
        pd.DataFrame({
            "timestamp": T0 + PPG_LAG + tp,
            "ambient": 1000 + rng.standard_normal(len(tp)),
            "ir": 200000 + 3000 * pulse + 20 * rng.standard_normal(len(tp)),
            "red": 150000 + 1000 * pulse,
        }).to_csv(d / "muse_ppg.csv", index=False)
    pd.DataFrame({
        "timestamp": [T0 + 5, T0 + 45.2, T0 + 80],
        "label": ["SYNC mulai", "Mata tertutup", "SYNC selesai (+0.062 s)"],
    }).to_csv(d / "marker.csv", index=False)
    (d / "session.json").write_text(json.dumps({
        "name": "subjek01", "note": "mata tertutup di detik 45",
        "start_unix": T0 - 1, "start_local": "2026-09-25T10:15:00", "duration_sec": DUR,
    }))
    return d


def test_list_samples_finds_musepolar_sessions(tmp_path):
    make_session(tmp_path, "20260925_101500_subjek01")
    make_session(tmp_path, "20260925_111500_subjek02", ppg=False)
    (tmp_path / "not_a_session").mkdir()
    inv = list_samples(tmp_path)
    assert inv["label"].tolist() == ["20260925_101500_subjek01", "20260925_111500_subjek02"]
    assert inv["participant"].iloc[0] == "subjek01"
    assert inv["has_ppg"].tolist() == [True, False]
    # A session folder itself is also accepted as root.
    assert list_samples(tmp_path / "20260925_101500_subjek01")["label"].tolist() == ["20260925_101500_subjek01"]


def test_load_sample_aligns_streams_and_maps_ppg(tmp_path):
    d = make_session(tmp_path)
    data = load_sample(d)
    eeg, ppg = data["eeg_f"], data["ppg"]
    assert eeg["time_s"].iloc[0] == 0.0
    assert ppg["time_s"].iloc[0] == pytest.approx(PPG_LAG, abs=1e-6)  # shared clock kept
    assert (ppg["PPG2"] == ppg["ir"]).all()
    assert data["meta"]["eeg_validation"]["status"] == "VALID"
    assert data["meta"]["ppg_validation"]["status"] == "VALID"
    assert data["markers"]["time_s"].tolist() == pytest.approx([5, 45.2, 80])
    assert marker_titik(data["markers"]) == "45"
    assert len(data["bp"]) > 30

    prv = compute_prv_09(ppg["PPG2"].to_numpy(float), ppg["time_s"].to_numpy(float))
    assert prv["ok"] and prv["hr"] == pytest.approx(60, abs=1)

    tab, _ = ruas_stats(data["bp"], parse_marks("45", eeg["time_s"].iloc[-1]), "alpha")
    assert tab["AF7"].iloc[1] > 3 * tab["AF7"].iloc[0]  # alpha rises after the marker


def test_session_without_ppg(tmp_path):
    data = load_sample(make_session(tmp_path, ppg=False))
    assert data["ppg"].empty and data["meta"]["ppg_validation"]["status"] == "-"
    prv = compute_prv_09(data["ppg"]["PPG2"].to_numpy(float), data["ppg"]["time_s"].to_numpy(float))
    assert not prv["ok"] and len(prv["tp"]) == 0


def _zip_of(folder: Path) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for p in folder.rglob("*"):
            zf.write(p, p.relative_to(folder.parent))
    return buf.getvalue()


def test_unpack_zip(tmp_path):
    d = make_session(tmp_path / "rec")
    root = unpack_zip(_zip_of(d))
    assert list_samples(root)["label"].tolist() == [d.name]


def test_api_upload_then_figures(tmp_path):
    pytest.importorskip("fastapi")
    pytest.importorskip("matplotlib")
    try:
        from fastapi.testclient import TestClient
    except (ImportError, RuntimeError):
        pytest.skip("TestClient dependencies not installed")
    import api

    d = make_session(tmp_path / "rec")
    client = TestClient(api.app)
    r = client.post("/upload", files={"file": ("s.zip", _zip_of(d))}, follow_redirects=False)
    assert r.status_code == 303
    page = client.get(r.headers["location"])
    assert page.status_code == 200 and "ERROR" not in page.text and d.name in page.text
    # Figures must use the uploaded folder, not the default recordings/ folder.
    import html
    import re

    src = html.unescape(re.search(r'id="img-tr" src="([^"]+)"', page.text).group(1))
    assert client.get(src).status_code == 200
    view = client.get("/api/view", params={"trials": str(api.LAST_UPLOAD["root"]), "label": d.name}).json()
    assert view["denyut"] == pytest.approx(60, abs=1) and view["eeg"] == "VALID"
