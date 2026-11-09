"""All evidence maps of CorVa Space in one place (label rules, protocol, session engine, conclusions)."""

from __future__ import annotations

from . import conclusions, labels, protocol, session


def all_evidence() -> dict:
    return {**labels.EVIDENCE, **protocol.EVIDENCE, **session.EVIDENCE, **conclusions.EVIDENCE}
