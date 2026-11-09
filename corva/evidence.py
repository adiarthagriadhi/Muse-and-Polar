"""All evidence maps of CorVa Space in one place (label rules, protocol, session engine, conclusions)."""

from __future__ import annotations

from . import conclusions, labels, norms, protocol, session, validate


def all_evidence() -> dict:
    return {**labels.EVIDENCE, **protocol.EVIDENCE, **session.EVIDENCE, **conclusions.EVIDENCE,
            **norms.EVIDENCE, **validate.EVIDENCE}
