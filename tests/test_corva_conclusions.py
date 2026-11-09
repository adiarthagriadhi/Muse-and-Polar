"""CorVa conclusions (D-19 to D-21): session narrative from phase labels, and change between sessions."""

import pytest

from corva import conclusions as C
from corva.evidence import all_evidence
from corva.labels import classify, references
from corva.protocol import PROTOCOL


def _result(medians: dict, theta=None, r0_ok=True, raw=None, delta=None, inadequate=()):
    """A minimal analyze_session() result: medians = {phase id: (x_z, y_z)}."""
    phases = []
    for p in PROTOCOL:
        pid = p["id"]
        x, y = medians.get(pid, (0.0, 0.0))
        ok = r0_ok and pid not in inadequate
        lab = classify(x, y, "rest", (theta or {}).get(pid)) if ok else classify(None, None)
        exp = None if p["reference"] else ("sesuai harapan" if lab["code"] in p["expected"] else "berbeda dari harapan")
        phases.append({"id": pid, "name": p["name"], "reference": p["reference"], "adequate": ok,
                       "label": lab, "comparison": "acuan (R0)" if p["reference"] else (exp if ok else None),
                       "medians": {"x_z": x, "y_z": y, "theta_beta_z": (theta or {}).get(pid, 0.0)},
                       "delta": (delta or {}).get(pid, {"log_beta_alpha": 0.0, "ln_rmssd": 0.0})})
    r0 = {"adequate": r0_ok, "raw": raw or {"log_beta_alpha": -2.4, "ln_rmssd": 3.4},
          "raw_scale": {"log_beta_alpha": 0.3, "ln_rmssd": 0.1}}
    res = {"session_id": "s", "phases": phases, "r0": r0}
    res["conclusions"] = C.conclude(res)
    return res


TYPICAL = {"eo_deep": (0.0, 2.0), "ec_reg": (-2.0, 0.0), "ec_deep": (-2.0, 2.0)}


def ids(res):
    return [i["id"] for i in res["conclusions"]["items"]]


def test_typical_relaxation():
    res = _result(TYPICAL)
    assert ids(res) == ["relax_typical"]
    item = res["conclusions"]["items"][0]
    assert not item["assumed"] and "korteks melambat" in item["narrative"] and "vagal naik" in item["narrative"]
    assert res["conclusions"]["summary"].startswith("Relatif terhadap baseline sesi ini: respons rileks khas")


def test_difficulty_relaxing_is_written_as_assumed():
    res = _result({"eo_deep": (0.0, 0.2), "ec_reg": (0.1, 0.0), "ec_deep": (-2.0, 2.0)})
    got = {i["id"]: i for i in res["conclusions"]["items"]}
    assert set(got) == {"relax_cortical_difficulty", "relax_vagal_difficulty"}
    for i in got.values():
        assert i["assumed"] and i["narrative"].startswith("Diasumsikan sulit rileks")
        assert "sebagian" in i["narrative"]  # one of the two phases still responded
    assert "(diasumsikan)" in res["conclusions"]["summary"]


def test_cortical_load_with_vagal_withdrawal():
    res = _result({**TYPICAL, "eo_reg": (1.5, -1.0)})
    got = {i["id"]: i for i in res["conclusions"]["items"]}
    assert "cortical_load" in got and "Q4" in got["cortical_load"]["narrative"] and not got["cortical_load"]["assumed"]
    assert got["vagal_withdrawal_rest"]["narrative"].startswith("Diasumsikan tegang")


def test_fatigue_needs_theta_beta():
    tired = {**TYPICAL, "ec_reg": (-1.5, -2.0)}
    assert "fatigue" in ids(_result(tired, theta={"ec_reg": 2.0}))
    assert "fatigue" not in ids(_result(tired, theta={"ec_reg": 0.1}))


def test_no_conclusion_without_adequate_baseline():
    res = _result(TYPICAL, r0_ok=False)
    assert ids(res) == [] and "R0 tidak memenuhi" in res["conclusions"]["summary"]


def test_inadequate_phases_are_listed_not_concluded():
    res = _result(TYPICAL, inadequate=("eo_deep", "ec_deep"))
    assert "relax_typical" not in ids(res)  # only one relaxation phase left
    assert set(res["conclusions"]["missing"]) == {"Mata terbuka · napas dalam", "Mata tertutup · napas dalam"}


def test_compare_sessions():
    pre = _result({"eo_deep": (0.0, 0.2), "ec_reg": (-2.0, 0.0), "ec_deep": (-2.0, 0.3)},
                  raw={"log_beta_alpha": -2.4, "ln_rmssd": 3.0},
                  delta={"ec_deep": {"log_beta_alpha": -0.30, "ln_rmssd": 0.02}})
    post = _result(TYPICAL, raw={"log_beta_alpha": -2.42, "ln_rmssd": 3.3},
                   delta={"ec_deep": {"log_beta_alpha": -0.32, "ln_rmssd": 0.25}})
    out = C.compare(pre, post)
    text = " | ".join(i["narrative"] for i in out["items"])
    assert all(i["assumed"] and i["narrative"].startswith("Diasumsikan") for i in out["items"])
    assert "tonus vagal saat istirahat (R0) lebih tinggi" in text  # 0.3 ln units = 3 × R0 scale
    assert "aktivasi kortikal saat istirahat" not in text  # 0.02 < 0.6 × 0.3
    assert "fase 5 mata tertutup · napas dalam" in text and "vagal lebih tinggi" in text
    assert "sulit rileks secara vagal: tampak sebelum, tidak tampak sesudah" in text
    assert out["summary"].startswith("Diasumsikan, dibanding sesi sebelum")
    row = next(r for r in out["table"] if r["id"] == "ec_deep")
    assert row["ln_rmssd"]["diff"] == pytest.approx(0.23)


def test_compare_needs_both_baselines():
    out = C.compare(_result(TYPICAL, r0_ok=False), _result(TYPICAL))
    assert out["items"] == [] and "Belum bisa dibandingkan" in out["summary"]


def test_every_conclusion_is_traceable():
    refs, ev = references(), all_evidence()
    for cid, (title, status) in C.CONCLUSIONS.items():
        e = ev["concl_" + cid]
        assert e["refs"] and all(k in refs for k in e["refs"]), cid
        assert bool(e.get("combination_assumed")) == (status == "asumsi"), cid


def test_conclusions_csv():
    pre, post = _result({"eo_deep": (0.0, 0.2)}), _result(TYPICAL)
    text = C.conclusions_csv(post, C.compare(pre, post))
    assert text.splitlines()[0].startswith("scope,session,pre_session,id")
    assert "sesi,s,,relax_typical" in text and "perbandingan,s,s," in text
