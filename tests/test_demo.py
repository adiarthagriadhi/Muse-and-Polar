"""Demo sessions: valid recording format and a visible R0 → R1 shift in the CASS explorer."""

import json

from cass_polar.explorer import explorer_payload
from musepolar.demo import ensure_demo_sessions


def test_demo_sessions(tmp_path):
    folders = ensure_demo_sessions(tmp_path)
    assert [f.name.split("_", 2)[-1] for f in folders] == ["DEMO_P01", "DEMO_P02", "DEMO_P03"]
    assert ensure_demo_sessions(tmp_path) == folders  # created once, then reused
    meta = json.loads((folders[0] / "session.json").read_text())
    assert meta["demo"] and meta["samples"]["muse_eeg"] == 240 * 256
    assert (folders[0] / "muse_ppg.csv").read_text().startswith("timestamp,ambient,ir,red")

    post = lambda p: p["occupancy"]["POST"]["q"]  # noqa: E731
    p1, p2 = explorer_payload(folders[0]), explorer_payload(folders[1])
    assert p1["default_marker_s"] == 60 and p1["n_y_valid"] == p1["n_windows"]
    assert max(post(p1), key=post(p1).get) == "Q4"  # mental task: cortical up, autonomic down
    assert max(post(p2), key=post(p2).get) == "Q2"  # slow breathing: cortical down, autonomic up
