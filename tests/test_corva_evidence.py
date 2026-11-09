"""CASS-NV evidence traceability: every rule cites the bibliography or is a declared assumption."""

from corva.evidence import all_evidence
from corva.labels import ALT_NAMES, CELLS, EVIDENCE, NO_DATA, PHASE_READING, classify, cite, references
from corva.protocol import EXPECTATION_REFS, PROTOCOL

REQUIRED = {"authors", "authors_complete", "year", "title", "journal", "doi", "doi_verified", "read", "finding"}


def test_bibliography_entries_complete():
    refs = references()
    assert len(refs) >= 20
    for key, r in refs.items():
        assert REQUIRED <= set(r), key
        assert r["authors"] and r["title"] and r["finding"], key
        assert r["doi"] is None or r["doi"].startswith("10."), key


def test_every_rule_has_evidence_or_is_a_declared_assumption():
    refs = references()
    codes = {c[0] for c in CELLS.values()} | {NO_DATA[0]}
    rules = {"axis_x", "axis_y", "two_axes", "threshold", "phases", "min_rr", "q3_qualifier",
             "protocol_baseline", "protocol_block", "protocol_eyes", "protocol_slow_breathing"}
    assert codes | rules <= set(all_evidence())
    for name, ev in all_evidence().items():
        assert ev["basis"], name
        if ev.get("assumption"):
            assert not ev["refs"], name
        else:
            assert ev["refs"], f"{name}: no reference and not declared an assumption"
        for k in ev["refs"]:
            assert k in refs, f"{name} cites unknown reference {k}"


def test_every_reference_is_used():
    used = {k for ev in all_evidence().values() for k in ev["refs"]}
    assert set(references()) == used


def test_labels_carry_their_references():
    assert set(classify(1.5, -2.0)["refs"]) == set(EVIDENCE["Q4"]["refs"])
    with_phase = classify(-1, 1, "recovery")["refs"]
    assert "laborde2018" in with_phase and "barry2007" in with_phase
    assert set(PHASE_READING) == {"Q1", "Q2", "Q3", "Q4"}
    assert classify(None, None)["refs"] == EVIDENCE["NO_DATA"]["refs"]


def test_cite():
    assert cite("russell1980") == "Russell (1980)"
    assert cite("esco2014") == "Esco & Flatt (2014)"
    assert cite("barry2007") == "Barry dkk. (2007)"


def test_evidence_md_is_up_to_date():
    from corva.evidence_md import OUT, render

    assert OUT.read_text(encoding="utf-8") == render(), "run: python -m corva.evidence_md"


def test_alternative_names_cite_known_sources():
    refs = references()
    assert set(ALT_NAMES) == {c[0] for c in CELLS.values()} | {NO_DATA[0]}
    for code, alts in ALT_NAMES.items():
        for name, src, kind in alts:
            assert name and kind in ("istilah", "analogi"), code
            assert src.startswith("internal:") or src in refs, f"{code}: {src}"
    assert any(src == "russell1980" and kind == "analogi" for _, src, kind in ALT_NAMES["Q2"])


def test_protocol_expectations_cite_known_sources():
    refs = references()
    assert {p["id"] for p in PROTOCOL} == set(EXPECTATION_REFS)
    for phase_id, keys in EXPECTATION_REFS.items():
        assert all(k in refs for k in keys), phase_id
