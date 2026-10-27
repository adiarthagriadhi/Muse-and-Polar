"""After a restart the dashboard must still know the newest recording (CASS buttons)."""

import json

from musepolar.hub import Hub, latest_recording


def _session(root, name, eeg=3, rr=2, meta=True):
    d = root / name
    d.mkdir(parents=True)
    (d / "muse_eeg.csv").write_text("timestamp,TP9,AF7,AF8,TP10\n" + "1,1,1,1,1\n" * eeg)
    if rr is not None:
        (d / "polar_rr.csv").write_text("timestamp,rr_ms\n" + "1,900\n" * rr)
    if meta:
        (d / "session.json").write_text(json.dumps({"name": name, "start_unix": 100.0, "end_unix": 130.5,
                                                    "duration_sec": 30.5}))
    return d


def test_none_when_folder_missing_or_empty(tmp_path):
    assert latest_recording(tmp_path / "nope") is None
    (tmp_path / "kosong").mkdir()
    assert latest_recording(tmp_path) is None


def test_picks_newest_and_counts_rows(tmp_path):
    _session(tmp_path, "20261001_100000", eeg=1, rr=1)
    new = _session(tmp_path, "20261002_100000", eeg=5, rr=4)
    info = latest_recording(tmp_path)
    assert info["dir"] == str(new.resolve())
    assert info["active"] is False and info["elapsed"] == 30.5
    assert info["counts"]["muse_eeg"] == 5 and info["counts"]["polar_rr"] == 4


def test_session_without_session_json_still_counts(tmp_path):
    _session(tmp_path, "20261003_100000", meta=False)
    info = latest_recording(tmp_path)
    assert info["counts"]["muse_eeg"] == 3 and info["elapsed"] == 0.0


def test_missing_rr_is_reported_not_hidden(tmp_path):
    _session(tmp_path, "20261004_100000", rr=None)
    assert "polar_rr" not in latest_recording(tmp_path)["counts"]


def test_hello_carries_it(tmp_path):
    _session(tmp_path, "20261005_100000")
    hub = Hub(tmp_path)
    hub.last_recording = latest_recording(tmp_path)
    assert hub.hello()["recording"]["counts"]["polar_rr"] == 2
