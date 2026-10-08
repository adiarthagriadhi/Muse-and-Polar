"""B1 reference PPG pipeline: settings and behaviour on synthetic pulses."""

import sys
from pathlib import Path

import pytest

np = pytest.importorskip("numpy")
pytest.importorskip("scipy")

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from muse2_pipeline import ppg_b1  # noqa: E402


def synthetic_ppg(beats, fs=64.0, dur=120.0, noise=200.0, seed=0):
    t = np.arange(int(dur * fs)) / fs
    x = np.zeros_like(t)
    for b in beats:
        x += np.exp(-0.5 * ((t - b - 0.1) / 0.08) ** 2)
    x = 1e5 + 3000 * x + np.random.default_rng(seed).normal(0, noise, len(t))
    return t, x


def test_b1_settings_are_fixed():
    assert ppg_b1.FS == 64.0 and ppg_b1.BAND == (0.6, 3.5)


def test_interval_rule_matches_b1():
    ibi = np.array([800, 810, 1000, 820, 250, 2100, 800], float)
    # compared with the preceding raw interval: 1000 is > 20 % above 810, 820 is within 20 % of 1000,
    # 250 and 2100 are out of range, 800 is > 20 % below 2100
    assert ppg_b1.valid_intervals(ibi).tolist() == [True, True, False, True, False, False, False]


def test_recovers_rate_and_variability_from_clean_pulses():
    rr = 0.8 + 0.03 * np.sin(np.arange(160) * 0.7)
    beats = np.cumsum(rr)
    t, x = synthetic_ppg(beats)
    tp = ppg_b1.ppg_beats(x, t)
    ref = ppg_b1.window_metrics(beats, 10, 110)
    got = ppg_b1.window_metrics(tp, 10, 110)
    assert abs(got["hr"] - ref["hr"]) < 1.0
    assert abs(got["rmssd"] - ref["rmssd"]) < 10.0
    assert got["art"] < 0.05


def test_rmssd_uses_successive_valid_intervals_only():
    # intervals 0.8, 0.8, 0.8, 0.82, 1.5, 0.8, 0.81, 0.8 s: 1.5 and the 0.8 after it are rejected
    beats = np.r_[0, np.cumsum([0.8, 0.8, 0.8, 0.82, 1.5, 0.8, 0.81, 0.8])]
    m = ppg_b1.window_metrics(beats, 0, 10)
    assert m["n"] == 6
    # no difference across the gap (0.82 -> 0.81): only 0, 0, +20, -10 ms
    assert m["rmssd"] == pytest.approx(np.sqrt(np.mean(np.square([0, 0, 20, -10]))))


def test_polar_beats_start_at_zero():
    assert ppg_b1.polar_beats([1000, 500]).tolist() == [0.0, 1.0, 1.5]
