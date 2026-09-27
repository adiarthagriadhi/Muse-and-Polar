"""Electrode names, 2D head positions and channel groups for any 10-20 / 10-10 montage.

Positions use an azimuthal-equidistant projection seen from above: Cz at the centre, nose
up (+y), right ear right (+x); the "equator" ring (Fpz–T7–Oz–T8) sits at radius 0.92 so
that the head outline (radius 1) encloses it. Muse 2 recordings keep their own compact
layout so the four sensors fill the head map.
"""

from __future__ import annotations

import math
import re

MUSE_CH = ["TP9", "AF7", "AF8", "TP10"]
MUSE_POSITIONS = {"AF7": (-0.50, 0.48), "AF8": (0.50, 0.48), "TP9": (-0.82, -0.20), "TP10": (0.82, -0.20)}

EQUATOR_R = 0.92
MAX_R = 0.97
# polar angle (degrees from the vertex) of each row's midline electrode; rows behind C lie at 180°
_ROWS = {"FP": (90.0, 0), "AF": (67.5, 0), "F": (45.0, 0), "FC": (22.5, 0), "FT": (None, 0), "C": (0.0, 0),
         "T": (None, 0), "CP": (22.5, 180), "TP": (None, 180), "P": (45.0, 180), "PO": (67.5, 180),
         "O": (90.0, 180), "I": (112.5, 180)}
# azimuth (degrees from the nose, clockwise) of each row's lateral end on the equator
_EQ_AZ = {"FP": 18, "AF": 36, "F": 54, "FT": 72, "FC": 72, "C": 90, "T": 90, "CP": 108, "TP": 108,
          "P": 126, "PO": 144, "O": 162, "I": 162}
_OLD_NAMES = {"T3": "T7", "T4": "T8", "T5": "P7", "T6": "P8"}
_LABEL_RE = re.compile(r"^(FP|AF|FC|FT|CP|TP|PO|F|C|T|P|O|I)(Z|\d{1,2})$")
REGIONS = {  # display groups for many-channel recordings
    "Frontal": ("FP", "AF", "F"),
    "Sentral": ("FC", "C", "CP"),
    "Temporal": ("FT", "T", "TP"),
    "Parietal": ("P",),
    "Oksipital": ("PO", "O", "I"),
}
FRONTAL_PAIRS = [("F3", "F4"), ("AF7", "AF8"), ("AF3", "AF4"), ("Fp1", "Fp2"), ("F7", "F8"), ("F1", "F2")]


def canonical(label: str) -> str | None:
    """'EEG Fp1-REF' -> 'Fp1', 'T3' -> 'T7', 'FP1' -> 'Fp1'. None for non-electrode or bipolar labels."""
    s = str(label).strip().upper().replace(" ", "")
    for pre in ("EEG", "EEG:"):
        if s.startswith(pre):
            s = s[len(pre):]
    s = s.lstrip(":_-")
    parts = re.split(r"[-/:]", s)
    if not parts or not parts[0]:
        return None
    head = parts[0]
    if len(parts) > 1 and _LABEL_RE.match(_OLD_NAMES.get(parts[1], parts[1]) or ""):
        return None  # bipolar derivation (e.g. Fp1-F7): no single scalp position
    head = _OLD_NAMES.get(head, head)
    m = _LABEL_RE.match(head)
    if not m:
        return None
    row, col = m.groups()
    return (row.capitalize() if row == "FP" else row) + ("z" if col == "Z" else col)


def _split(name: str):
    m = _LABEL_RE.match(name.upper())
    return (m.group(1), m.group(2)) if m else (None, None)


def position(name: str) -> tuple[float, float] | None:
    row, col = _split(name)
    if row is None:
        return None
    k = 0 if col == "Z" else (int(col) + 1) // 2  # 1/2 -> 1, 3/4 -> 2, 5/6 -> 3, 7/8 -> 4, 9/10 -> 5
    side = 0 if col == "Z" else (-1 if int(col) % 2 else 1)
    theta_mid, az_mid = _ROWS[row]
    az_eq = _EQ_AZ[row]
    if row in ("FP", "O", "I") and k >= 1:
        k = 4  # Fp1/Fp2, O1/O2 lie on the equator
    if row in ("T", "FT", "TP"):
        theta_mid, k = 90.0, max(k, 4)  # T7, FT9, TP10 ... lateral rows
    if k <= 4:
        f = k / 4
        r_mid = theta_mid / 90 * EQUATOR_R
        if row == "C":
            r, az = f * EQUATOR_R, az_eq
        else:
            r = r_mid + (EQUATOR_R - r_mid) * f
            az = az_mid + (az_eq - az_mid) * f
    else:  # 9/10: below the equator
        r, az = 112.5 / 90 * EQUATOR_R, az_eq
    r = min(r, MAX_R)
    a = math.radians(az) * (side if side else 1)
    return (round(r * math.sin(a), 4), round(r * math.cos(a), 4))


def positions(channels: list[str]) -> dict[str, tuple[float, float]]:
    if set(channels) <= set(MUSE_CH):
        return {c: MUSE_POSITIONS[c] for c in channels}
    return {c: p for c in channels if (p := position(c)) is not None}


def frontal_pair(channels: list[str]) -> tuple[str, str] | None:
    have = {c.upper(): c for c in channels}
    for a, b in FRONTAL_PAIRS:
        if a.upper() in have and b.upper() in have:
            return have[a.upper()], have[b.upper()]
    return None


def region_of(name: str) -> str | None:
    row, _ = _split(name)
    for reg, rows in REGIONS.items():
        if row in rows:
            return reg
    return None


def regions(channels: list[str]) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for c in channels:
        reg = region_of(c)
        if reg:
            out.setdefault(reg, []).append(c)
    return out


# Nearest 10-20 / 10-10 substitute for each Muse 2 sensor, in order of preference.
MUSE_EQUIVALENT = {
    "TP9": ["TP9", "TP7", "T7", "P7", "FT9"],
    "AF7": ["AF7", "Fp1", "F7", "AF3", "F3"],
    "AF8": ["AF8", "Fp2", "F8", "AF4", "F4"],
    "TP10": ["TP10", "TP8", "T8", "P8", "FT10"],
}


def muse_equivalent(channels: list[str]) -> dict[str, str] | None:
    """{Muse sensor: channel used} with the 4 Muse-like positions, or None if one is missing."""
    have = {c.upper(): c for c in channels}
    out, used = {}, set()
    for muse, cands in MUSE_EQUIVALENT.items():
        pick = next((have[c.upper()] for c in cands if c.upper() in have and have[c.upper()] not in used), None)
        if pick is None:
            return None
        out[muse] = pick
        used.add(pick)
    return out
