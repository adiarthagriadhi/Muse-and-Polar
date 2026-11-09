"""CASS-NV (CorVa Space) label rules: 3 × 3 grid, phase reading, Q3 qualifier, missing data."""

import math

import pytest

from corva.labels import CELLS, classify, zone


def test_zone_edges():
    assert zone(0.5) == "high" and zone(-0.5) == "low" and zone(0.49) == "neutral"
    assert zone(None) is None and zone(math.nan) is None


@pytest.mark.parametrize("x,y,code", [
    (1.2, 0.9, "Q1"), (-1.0, 1.0, "Q2"), (-0.8, -0.7, "Q3"), (1.5, -2.0, "Q4"),
    (1.0, 0.1, "X_HIGH"), (-1.0, 0.0, "X_LOW"), (0.2, 1.0, "Y_HIGH"), (0.0, -1.0, "Y_LOW"),
    (0.1, -0.2, "NEUTRAL"),
])
def test_grid(x, y, code):
    assert classify(x, y)["code"] == code


def test_all_nine_cells_defined():
    assert len(CELLS) == 9 and len({c[0] for c in CELLS.values()}) == 9


def test_phase_reading():
    assert classify(1.5, -2.0, "activity")["phase_reading"] == "respons wajar (reaktivitas)"
    assert classify(1.5, -2.0, "recovery")["phase_reading"] == "pemulihan tertunda"
    assert classify(1.5, -2.0, "unknown")["phase"] is None


def test_q3_qualifier():
    assert classify(-1, -1, "activity", theta_beta_z=1.0)["qualifier"].startswith("lelah")
    assert classify(-1, -1, "recovery")["qualifier"].startswith("pemulihan awal")
    assert classify(-1, -1, "rest")["qualifier"] is None


def test_missing_data():
    assert classify(None, 1.0)["code"] == "NO_DATA"
    assert classify(1.0, math.nan)["code"] == "NO_DATA"
