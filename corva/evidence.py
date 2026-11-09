"""All evidence maps of CorVa Space in one place (label rules, protocol and session engine)."""

from __future__ import annotations

from . import labels, protocol, session


def all_evidence() -> dict:
    return {**labels.EVIDENCE, **protocol.EVIDENCE, **session.EVIDENCE}
