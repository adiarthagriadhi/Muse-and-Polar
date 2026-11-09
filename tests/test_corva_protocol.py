"""CorVa standard protocol: phases, durations, markers, expectations."""

from corva.protocol import PROTOCOL, as_json, compare, marker_label, phase_from_marker, total_seconds


def test_phases_and_durations():
    assert [p["id"] for p in PROTOCOL] == ["baseline", "eo_reg", "eo_deep", "ec_reg", "ec_deep"]
    assert PROTOCOL[0]["seconds"] == 300 and all(p["seconds"] == 180 for p in PROTOCOL[1:])
    assert all(p["settle_s"] == 60 for p in PROTOCOL)
    assert total_seconds() == 17 * 60
    assert [p["reference"] for p in PROTOCOL].count(True) == 1


def test_markers_round_trip():
    for p in PROTOCOL:
        assert phase_from_marker(marker_label(p["id"])) == p["id"]
    assert phase_from_marker("Mata tertutup") is None


def test_compare():
    assert compare("eo_deep", "Q2") == "sesuai harapan"
    assert compare("eo_deep", "Q4") == "berbeda dari harapan"
    assert compare("eo_deep", "NO_DATA") is None


def test_json():
    j = as_json()
    assert j["slow_breaths_per_min"] == 6 and len(j["phases"]) == 5
