"""CorVa v0.5 tooling: subjective scales (D-22), validation statistics (D-23) and reference-group norms (D-24)."""

import csv
import json

import pandas as pd
import pytest

from corva import norms as N
from corva import protocol
from corva.session import analyze_session
from corva.validate import icc_2_1, icc_reading, kappa, run
from test_corva_session import T0, _phase_starts, _write_session


# --- scales ------------------------------------------------------------------------------------------------

def test_scale_marker_roundtrip():
    label = protocol.scale_label("ec_reg", {"KSS": 7, "rileks": 6})
    assert label == "CorVa skala: ec_reg KSS=7 rileks=6"
    assert protocol.parse_scale(label) == ("ec_reg", {"KSS": 7, "rileks": 6})
    assert protocol.parse_scale(protocol.scale_label("eo_reg", None)) == ("eo_reg", {})
    assert protocol.parse_scale("CorVa skala: ec_reg KSS=12 x=3") == ("ec_reg", {})  # out of range / unknown
    assert protocol.parse_scale("CorVa: Relaks (baseline)") is None
    assert protocol.phase_from_marker(label) is None  # never mistaken for a phase marker
    js = protocol.as_json()
    assert [s["id"] for s in js["scales"]] == ["KSS", "rileks"] and js["scale_prefix"] == protocol.SCALE_PREFIX


def _add_ratings(folder, ratings, extra=()):
    mk = pd.read_csv(folder / "marker.csv")
    starts, _ = _phase_starts()
    secs = {p["id"]: p["seconds"] for p in protocol.PROTOCOL}
    rows = [(T0 + starts[pid] + secs[pid] - 0.3, protocol.scale_label(pid, v)) for pid, v in ratings.items()]
    rows += list(extra)
    mk = pd.concat([mk, pd.DataFrame(rows, columns=["timestamp", "label"])]).sort_values("timestamp")
    mk.to_csv(folder / "marker.csv", index=False)


def test_engine_reads_ratings_of_the_current_run(tmp_path):
    d = _write_session(tmp_path / "s")
    # a rating written before the baseline marker belongs to an earlier run and is ignored
    _add_ratings(d, {"ec_reg": {"KSS": 8, "rileks": 3}, "ec_deep": None},
                 extra=[(T0 - 30, protocol.scale_label("ec_reg", {"KSS": 2, "rileks": 9}))])
    res = analyze_session(d)
    ph = {p["id"]: p for p in res["phases"]}
    assert ph["ec_reg"]["subjective"] == {"KSS": 8, "rileks": 3}
    assert ph["ec_deep"]["subjective"] == {} and ph["eo_reg"]["subjective"] is None
    assert ph["ec_reg"]["label"]["code"] == "X_LOW"  # ratings do not move the phase boundaries


# --- statistics --------------------------------------------------------------------------------------------

def test_kappa_known_values():
    pairs = [(True, True)] * 20 + [(True, False)] * 5 + [(False, True)] * 10 + [(False, False)] * 15
    k = kappa(pairs)
    assert k["agreement"] == 0.7 and k["kappa"] == 0.4 and k["n"] == 50
    assert kappa([])["kappa"] is None


def test_icc_2_1_known_values():
    assert icc_2_1([(1, 2), (2, 3), (3, 4), (4, 5)]) == pytest.approx(0.769, abs=1e-3)  # constant bias lowers agreement
    assert icc_2_1([(1, 1), (2, 2), (3, 3)]) == 1.0
    assert icc_2_1([(1, 1), (2, 2)]) is None  # fewer than 3 participants
    assert [icc_reading(v) for v in (0.3, 0.6, 0.8, 0.95, None)] == ["buruk", "sedang", "baik", "sangat baik", None]


# --- norms -------------------------------------------------------------------------------------------------

def test_norms_build_percentile_and_annotate():
    rows = [{"participant": i, "phase_id": "eo_deep", "log_beta_alpha": 0.0, "ln_rmssd": i / 10} for i in range(11)]
    nm = N.build(rows)
    e = nm["phases"]["eo_deep"]["ln_rmssd"]
    assert nm["n_participants"] == 11 and nm["provisional"] and e["n"] == 11
    assert e["percentiles"]["50"] == pytest.approx(0.5)
    assert N.percentile_of(0.5, e) == pytest.approx(50) and N.percentile_of(5.0, e) == 99 and N.percentile_of(None, e) is None
    res = {"phases": [{"id": "eo_deep", "delta": {"log_beta_alpha": 0.0, "ln_rmssd": 0.9}}, {"id": "ec_reg", "delta": None}]}
    N.annotate(res, nm)
    assert res["phases"][0]["norms"]["ln_rmssd"]["percentile"] == pytest.approx(90) and "norms" not in res["phases"][1]
    assert res["norms"] == {"n_participants": 11, "provisional": True}


def test_norms_file_format(tmp_path):
    (tmp_path / "x.json").write_text(json.dumps({"format": "lain"}))
    with pytest.raises(ValueError):
        N.load(tmp_path / "x.json")


# --- the validation run ------------------------------------------------------------------------------------

def test_validation_run(tmp_path):
    root = tmp_path / "data"
    for name, seed, day in (("A", 1, 0), ("A", 5, 1), ("B", 2, 0)):
        d = _write_session(root / f"{name}_{day}", seed=seed)
        (d / "session.json").write_text(json.dumps({"name": name, "start_unix": T0 + day * 86400}))
        _add_ratings(d, {"ec_reg": {"KSS": 4, "rileks": 7}, "ec_deep": {"KSS": 3, "rileks": 8}, "eo_reg": {"KSS": 3, "rileks": 5}})
    (root / "rusak").mkdir()
    (root / "rusak" / "marker.csv").write_text("timestamp,label\n1,CorVa: Relaks (baseline)\n")
    out = tmp_path / "out"
    report = run(root, out, norms_out=out / "norms.json")
    assert report["n_sessions"] == 3 and report["n_participants"] == 2
    assert report["expectation"]["pct"] == 100.0 and report["expectation"]["per_phase"]["ec_deep"]["n"] == 3
    rel = report["subjective"]["relax_vs_rating"]
    assert rel["n"] == 6 and rel["both"] == 6 and rel["agreement"] == 1.0
    assert report["subjective"]["fatigue_vs_kss"]["n"] == 9 and report["subjective"]["fatigue_vs_kss"]["neither"] == 9
    assert report["test_retest"]["n_participants"] == 1 and report["test_retest"]["icc"]["R0_ln_rmssd"]["icc"] is None
    rows = list(csv.DictReader(open(out / "corva_phases.csv", encoding="utf-8")))
    assert len(rows) == 15 and {r["participant"] for r in rows} == {"A", "B"}
    assert any(r["kss"] == "4" and r["phase_id"] == "ec_reg" for r in rows)
    nm = N.load(out / "norms.json")
    assert nm["n_participants"] == 2 and nm["provisional"] and "baseline" not in nm["phases"]
    assert "Laporan validasi CorVa" in (out / "corva_report.md").read_text(encoding="utf-8")
