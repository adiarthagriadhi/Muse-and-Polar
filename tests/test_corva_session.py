"""CorVa v0.2 engine: markers → phases → R0 → labels per window and per phase → comparison with expectation.

A synthetic 17 min session follows the standard protocol with known behaviour: eyes closed doubles the
alpha amplitude (X down), slow breathing raises beat-to-beat RR variability (Y up). Synthetic data, no
physiological meaning.
"""

import shutil

import numpy as np
import pandas as pd
import pytest

from cass_polar.engine import CASSInputError, window_state
from corva import protocol
from corva.session import (MIN_EEG_S, analyze_session, clean_eeg_seconds, phase_spans, read_markers,
                           valid_rr_seconds)

FS = 256
T0 = 1_700_000_000.0


def _phase_starts():
    t, out = 0.0, {}
    for p in protocol.PROTOCOL:
        out[p["id"]] = t
        t += p["seconds"]
    return out, t


def _write_session(folder, seed=1, theta_boost=False):
    rng = np.random.default_rng(seed)
    starts, total = _phase_starts()
    folder.mkdir(parents=True, exist_ok=True)

    def phase_at(t):
        pid = None
        for k, s in starts.items():
            if t >= s:
                pid = k
        return pid

    # EEG: theta 6 Hz, alpha 10 Hz, beta 20 Hz with slow amplitude wander and noise
    t = np.arange(int(total * FS)) / FS
    eyes_closed = np.isin([phase_at(x) for x in np.arange(int(total))], ["ec_reg", "ec_deep"])
    alpha_amp = np.where(eyes_closed, 20.0, 10.0)[t.astype(int)]
    theta_amp = np.where(eyes_closed & theta_boost, 16.0, 4.0)[t.astype(int)]
    wander = 1 + 0.12 * np.sin(2 * np.pi * t / 37.0)
    cols = []
    for ch in range(4):
        ph = rng.uniform(0, 2 * np.pi, 3)
        x = (theta_amp * np.sin(2 * np.pi * 6 * t + ph[0]) + alpha_amp * wander * np.sin(2 * np.pi * 10 * t + ph[1])
             + 4.0 / wander * np.sin(2 * np.pi * 20 * t + ph[2]) + rng.normal(0, 2.0, len(t)))
        cols.append(x)
    eeg = np.column_stack([T0 + t, *cols])
    np.savetxt(folder / "muse_eeg.csv", eeg, delimiter=",", fmt=["%.6f"] + ["%.3f"] * 4,
               header="timestamp,TP9,AF7,AF8,TP10", comments="")

    # RR: slow breathing -> larger successive differences (higher RMSSD)
    beats, tb = [], 0.0
    while tb < total:
        sd = 45.0 if phase_at(tb) in ("eo_deep", "ec_deep") else 15.0
        rr = 850.0 + rng.normal(0, sd)
        tb += rr / 1000.0
        beats.append((T0 + tb, round(rr, 1)))
    pd.DataFrame(beats, columns=["timestamp", "rr_ms"]).to_csv(folder / "polar_rr.csv", index=False)

    marks = [(T0 + 0.5, "SYNC mulai")] + [(T0 + s, protocol.marker_label(pid)) for pid, s in starts.items()]
    marks.append((T0 + total - 0.2, protocol.MARKER_PREFIX + "selesai"))
    pd.DataFrame(marks, columns=["timestamp", "label"]).to_csv(folder / "marker.csv", index=False)
    return folder


@pytest.fixture(scope="module")
def session_dir(tmp_path_factory):
    return _write_session(tmp_path_factory.mktemp("corva") / "s1")


@pytest.fixture(scope="module")
def result(session_dir):
    return analyze_session(session_dir)


def _copy(session_dir, tmp_path):
    dst = tmp_path / "copy"
    shutil.copytree(session_dir, dst)
    return dst


def _phase(res, pid):
    return next(p for p in res["phases"] if p["id"] == pid)


# --- engine connection ---------------------------------------------------------------------------------

def test_window_state_has_theta_ratios_and_time_base(session_dir):
    state, duration, _ = window_state(session_dir, None)
    assert {"AF7_theta_beta_raw", "AF7_engagement_raw", "AF7_cortical_raw"} <= set(state.columns)
    assert state.attrs["eeg_start_unix"] == pytest.approx(T0)
    assert state.attrs["eeg_clean_windows"] and duration > 1000


# --- phases from markers -------------------------------------------------------------------------------

def test_markers_to_phases(result):
    assert [m["phase_id"] for m in result["markers"]] == [p["id"] for p in protocol.PROTOCOL] + [None]
    base = _phase(result, "baseline")
    assert base["start"] == pytest.approx(0, abs=0.01) and base["analysis_start"] == pytest.approx(60, abs=0.01)
    assert base["end"] == pytest.approx(300, abs=0.01) and base["complete"]
    assert result["r0"]["start"] == pytest.approx(60, abs=0.01) and result["r0"]["adequate"]
    assert result["r0"]["rr_valid_s"] >= 200 and result["r0"]["eeg_clean_s"] >= 200


def test_settling_windows_not_analysed(result):
    for w in result["windows"]:
        if w["phase_id"] == "eo_reg" and w["t0"] < 360:
            assert not w["analysed"]
    assert any(w["analysed"] and w["phase_id"] == "eo_reg" for w in result["windows"])


def test_restarted_protocol_uses_last_run(tmp_path):
    mk = pd.DataFrame({"timestamp": [T0 + 1, T0 + 50, T0 + 60, T0 + 400],
                       "label": [protocol.marker_label("baseline"), protocol.MARKER_PREFIX + "dihentikan",
                                 protocol.marker_label("baseline"), protocol.marker_label("eo_reg")]})
    mk.to_csv(tmp_path / "marker.csv", index=False)
    m = read_markers(tmp_path, T0)
    assert list(m.phase_id) == ["baseline", "eo_reg"] and m.time_s.iloc[0] == pytest.approx(60)
    spans = phase_spans(m, 1000)
    assert spans["baseline"]["end"] == pytest.approx(360) and spans["eo_reg"]["end"] == pytest.approx(580)


def test_phase_closed_by_stop_marker():
    m = pd.DataFrame({"time_s": [0.0, 300.0, 330.0], "label": ["", "", ""],
                      "phase_id": ["baseline", "eo_reg", None]})
    sp = phase_spans(m, 2000)
    assert sp["eo_reg"]["end"] == 330 and not sp["eo_reg"]["complete"]


def test_missing_baseline_marker_is_an_error(session_dir, tmp_path):
    d = _copy(session_dir, tmp_path)
    pd.DataFrame({"timestamp": [T0 + 1], "label": ["Baseline mulai"]}).to_csv(d / "marker.csv", index=False)
    with pytest.raises(CASSInputError, match="tidak ditemukan"):
        analyze_session(d)


# --- labels per phase and comparison with expectation --------------------------------------------------

def test_phase_labels_follow_known_behaviour(result):
    got = {p["id"]: p["label"]["code"] for p in result["phases"]}
    assert got["baseline"] == "NEUTRAL" and got["eo_reg"] == "NEUTRAL"
    assert got["eo_deep"] == "Y_HIGH"
    assert got["ec_reg"] == "X_LOW"
    assert got["ec_deep"] == "Q2"
    assert _phase(result, "ec_deep")["label"]["phase_reading"] == "istirahat baik"


def test_comparison_with_expectation(result):
    assert _phase(result, "baseline")["comparison"] == "acuan (R0)"
    for pid in ("eo_reg", "eo_deep", "ec_reg", "ec_deep"):
        assert _phase(result, pid)["comparison"] == "sesuai harapan", pid
    assert result["summary"] == {"n_compared": 4, "n_as_expected": 4}


def test_phase_outputs_medians_occupancy_and_confidence(result):
    p = _phase(result, "ec_reg")
    assert p["medians"]["x_z"] < -0.6 and abs(p["medians"]["y_z"]) < 0.6
    assert p["occupancy"].get("X_LOW", 0) > 0.5 and abs(sum(p["occupancy"].values()) - 1) < 0.01
    assert p["data"]["rr_valid_s"] >= 60 and p["data"]["eeg_clean_s"] >= MIN_EEG_S
    assert p["data"]["analysis_s"] == pytest.approx(120, abs=0.5) and p["adequate"]
    assert p["segment_ln_rmssd"] == pytest.approx(np.log(p["segment_rmssd_ms"]), abs=1e-3)
    assert p["expected_refs"] == protocol.EXPECTATION_REFS["ec_reg"]


def test_window_labels_and_ratios(result):
    w = [w for w in result["windows"] if w["analysed"] and w["phase_id"] == "ec_deep"]
    assert w and sum(x["code"] == "Q2" for x in w) / len(w) > 0.5
    assert all(x["ln_rmssd"] == pytest.approx(np.log(x["rmssd_ms"]), abs=1e-3) for x in w if x["rmssd_ms"])
    assert all(x["theta_beta_z"] is not None and x["engagement_z"] is not None for x in w)


def test_theta_beta_qualifies_q3(tmp_path):
    """Eyes closed with a theta surge: X down; with Y also down the Q3 label carries the fatigue marker."""
    d = _write_session(tmp_path / "theta", seed=3, theta_boost=True)
    res = analyze_session(d)
    p = _phase(res, "ec_reg")
    assert p["medians"]["theta_beta_z"] >= 0.6
    rr = pd.read_csv(d / "polar_rr.csv")  # make ec_reg vagally lower: almost no beat-to-beat change
    rel = rr.timestamp - T0
    s = _phase_starts()[0]["ec_reg"]
    sel = (rel >= s) & (rel < s + 180)
    rr.loc[sel, "rr_ms"] = 850 + np.random.default_rng(5).normal(0, 3, sel.sum()).round(1)
    rr.to_csv(d / "polar_rr.csv", index=False)
    p = _phase(analyze_session(d), "ec_reg")
    assert p["label"]["code"] == "Q3"
    assert p["label"]["qualifier"].startswith("lelah") and p["comparison"] == "berbeda dari harapan"


# --- data condition (D-11) -----------------------------------------------------------------------------

def test_rr_gap_gives_no_data_with_reason(session_dir, tmp_path):
    d = _copy(session_dir, tmp_path)
    rr = pd.read_csv(d / "polar_rr.csv")
    s = _phase_starts()[0]["eo_deep"]
    rel = rr.timestamp - T0
    rr[~((rel >= s + 70) & (rel < s + 180))].to_csv(d / "polar_rr.csv", index=False)
    res = analyze_session(d)
    p = _phase(res, "eo_deep")
    assert p["label"]["code"] == "NO_DATA" and p["comparison"] is None and not p["adequate"]
    assert any(r.startswith("RR valid") for r in p["reasons"])
    assert _phase(res, "ec_deep")["label"]["code"] == "Q2"


def test_inadequate_r0_blocks_all_phase_labels(session_dir, tmp_path):
    d = _copy(session_dir, tmp_path)
    rr = pd.read_csv(d / "polar_rr.csv")
    rel = rr.timestamp - T0
    rr[~((rel >= 70) & (rel < 300))].to_csv(d / "polar_rr.csv", index=False)
    res = analyze_session(d)
    assert not res["r0"]["adequate"]
    assert all(p["label"]["code"] == "NO_DATA" for p in res["phases"])
    assert any("R0 tidak memenuhi" in w for w in res["warnings"])


def test_stopped_protocol_marks_unrecorded_phases(session_dir, tmp_path):
    d = _copy(session_dir, tmp_path)
    s = _phase_starts()[0]
    mk = pd.DataFrame({"timestamp": [T0 + s["baseline"], T0 + s["eo_reg"], T0 + s["eo_deep"], T0 + s["eo_deep"] + 30],
                       "label": [protocol.marker_label("baseline"), protocol.marker_label("eo_reg"),
                                 protocol.marker_label("eo_deep"), protocol.MARKER_PREFIX + "dihentikan"]})
    mk.to_csv(d / "marker.csv", index=False)
    res = analyze_session(d)
    assert _phase(res, "eo_reg")["label"]["code"] == "NEUTRAL"
    deep = _phase(res, "eo_deep")
    assert deep["label"]["code"] == "NO_DATA" and not deep["complete"] and deep["data"]["analysis_s"] == 0
    for pid in ("ec_reg", "ec_deep"):
        assert not _phase(res, pid)["recorded"] and _phase(res, pid)["reasons"] == ["fase tidak direkam"]


# --- helpers ---------------------------------------------------------------------------------------------

def test_clean_eeg_seconds_union():
    assert clean_eeg_seconds([(0, 4), (2, 6), (10, 14)], 1, 12) == pytest.approx(7)
    assert clean_eeg_seconds([], 0, 100) == 0


def test_valid_rr_seconds_rule():
    rr = pd.DataFrame({"time_s": [1, 2, 3, 4, 5], "rr_ms": [1000, 1000, 1500, 1000, 250]})
    # 1500 is a >20 % jump, the 1000 after it too, 250 is out of range
    assert valid_rr_seconds(rr, 0, 10) == pytest.approx(2.0)
