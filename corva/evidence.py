"""All evidence maps of CorVa Space in one place (label rules and protocol)."""

from __future__ import annotations

from . import labels, protocol


def all_evidence() -> dict:
    return {**labels.EVIDENCE, **protocol.EVIDENCE}
