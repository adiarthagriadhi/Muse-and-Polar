"""CASS-NV (CorVa Space) qualitative labels: cortical (X) × vagal (Y) on a 3 × 3 grid.

X = robust z of log(beta/alpha) from Muse EEG, Y = robust z of lnRMSSD from Polar RR, both against
the person's own reference R0. Each axis is split into low / neutral / high at ±THRESHOLD_Z, giving
four quadrants, four single-axis cells and a neutral cell. The phase (rest, activity, recovery;
Vagal Tank Theory) adds a reading of the same cell in context. See corva/MODEL.md.

Values marked provisional wait for the decisions in corva/DECISIONS.md.
"""

from __future__ import annotations

import math

THRESHOLD_Z = 0.5  # provisional (D-06), same as the old Research View labels
PHASES = ("rest", "activity", "recovery")

# (x zone, y zone) -> (code, label, meaning); provisional names (D-07)
CELLS = {
    ("high", "high"): ("Q1", "Terlibat–teratur", "korteks aktif dengan regulasi vagal terjaga"),
    ("low", "high"): ("Q2", "Rileks–pulih", "korteks melambat, vagal naik"),
    ("low", "low"): ("Q3", "Hipoaktif", "korteks melambat, vagal turun"),
    ("high", "low"): ("Q4", "Teraktivasi–terbebani", "korteks aktif, penarikan vagal"),
    ("high", "neutral"): ("X_HIGH", "Aktivasi kortikal", "perubahan hanya di korteks"),
    ("low", "neutral"): ("X_LOW", "Korteks melambat", "perubahan hanya di korteks"),
    ("neutral", "high"): ("Y_HIGH", "Vagal naik", "perubahan hanya di vagal"),
    ("neutral", "low"): ("Y_LOW", "Penarikan vagal", "perubahan hanya di vagal"),
    ("neutral", "neutral"): ("NEUTRAL", "Netral", "sekitar acuan R0"),
}
NO_DATA = ("NO_DATA", "Data kurang", "EEG bersih atau RR valid tidak cukup")

# reading of a quadrant in each phase (Vagal Tank Theory: resting, reactivity, recovery)
PHASE_READING = {
    "Q1": {"rest": "siaga tenang", "activity": "keterlibatan teratur", "recovery": "pulih, sudah siaga"},
    "Q2": {"rest": "istirahat baik", "activity": "keterlibatan rendah", "recovery": "pemulihan baik"},
    "Q3": {"rest": "mengantuk", "activity": "kelelahan", "recovery": "pemulihan awal"},
    "Q4": {"rest": "tidak lazim saat istirahat, periksa", "activity": "respons wajar (reaktivitas)",
           "recovery": "pemulihan tertunda"},
}


def _finite(v) -> bool:
    return v is not None and isinstance(v, (int, float)) and math.isfinite(v)


def zone(z: float | None, threshold: float = THRESHOLD_Z) -> str | None:
    """'low', 'neutral' or 'high' for a z value; None when it is missing."""
    if not _finite(z):
        return None
    if z >= threshold:
        return "high"
    if z <= -threshold:
        return "low"
    return "neutral"


def classify(x_z: float | None, y_z: float | None, phase: str | None = None,
             theta_beta_z: float | None = None, threshold: float = THRESHOLD_Z) -> dict:
    """Qualitative label for one window or segment.

    x_z: cortical z (log beta/alpha), y_z: vagal z (lnRMSSD), phase: 'rest' | 'activity' | 'recovery',
    theta_beta_z: z of log(theta/beta), used only to qualify Q3 (fatigue/drowsiness vs. early recovery).
    """
    zx, zy = zone(x_z, threshold), zone(y_z, threshold)
    if zx is None or zy is None:
        code, label, meaning = NO_DATA
        return {"code": code, "label": label, "meaning": meaning, "x_zone": zx, "y_zone": zy,
                "phase": phase, "phase_reading": None, "qualifier": None}
    code, label, meaning = CELLS[(zx, zy)]
    phase = phase if phase in PHASES else None
    reading = PHASE_READING.get(code, {}).get(phase) if phase else None
    qualifier = None
    if code == "Q3":
        if _finite(theta_beta_z) and theta_beta_z >= threshold:
            qualifier = "lelah/mengantuk (θ/β naik)"
        elif phase == "recovery":
            qualifier = "pemulihan awal (vagal belum pulih)"
    return {"code": code, "label": label, "meaning": meaning, "x_zone": zx, "y_zone": zy,
            "phase": phase, "phase_reading": reading, "qualifier": qualifier}
