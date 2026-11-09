"""Demo sessions: valid recording format, a visible R0 → R1 shift in the CASS explorer, and CorVa protocol runs."""

import json

from cass_polar.explorer import explorer_payload
from corva.session import analyze_session
from musepolar.demo import ensure_demo_sessions


def test_demo_sessions(tmp_path):
    folders = ensure_demo_sessions(tmp_path)
    assert [f.name.split("_", 2)[-1] for f in folders] == ["DEMO_P01", "DEMO_P02", "DEMO_P03", "DEMO_P04", "DEMO_P05"]
    assert ensure_demo_sessions(tmp_path) == folders  # created once, then reused
    meta = json.loads((folders[0] / "session.json").read_text())
    assert meta["demo"] and meta["samples"]["muse_eeg"] == 240 * 256
    assert (folders[0] / "muse_ppg.csv").read_text().startswith("timestamp,ambient,ir,red")

    post = lambda p: p["occupancy"]["POST"]["q"]  # noqa: E731
    p1, p2 = explorer_payload(folders[0]), explorer_payload(folders[1])
    assert p1["default_marker_s"] == 60 and p1["n_y_valid"] == p1["n_windows"]
    assert max(post(p1), key=post(p1).get) == "Q4"  # mental task: cortical up, autonomic down
    assert max(post(p2), key=post(p2).get) == "Q2"  # slow breathing: cortical down, autonomic up

    # CorVa protocol demos: P04 as expected in every phase, P05 drowsy with eyes closed
    p4, p5 = analyze_session(folders[3]), analyze_session(folders[4])
    assert p4["summary"] == {"n_compared": 4, "n_as_expected": 4} and not p4["warnings"]
    assert [p["label"]["code"] for p in p4["phases"]] == ["NEUTRAL", "NEUTRAL", "Y_HIGH", "X_LOW", "Q2"]
    assert p5["summary"] == {"n_compared": 4, "n_as_expected": 3}
    drowsy = next(p for p in p5["phases"] if p["id"] == "ec_reg")
    assert drowsy["label"]["code"] == "Q3" and drowsy["label"]["qualifier"].startswith("lelah")
    assert drowsy["comparison"] == "berbeda dari harapan"
    assert json.loads((folders[3] / "session.json").read_text())["duration_sec"] == 17 * 60
