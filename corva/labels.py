"""CASS-NV (CorVa Space) qualitative labels: cortical (X) × vagal (Y) on a 3 × 3 grid.

X = robust z of log(beta/alpha) from Muse EEG, Y = robust z of lnRMSSD from Polar RR, both against
the person's own reference R0. Each axis is split into low / neutral / high at ±THRESHOLD_Z, giving
four quadrants, four single-axis cells and a neutral cell (still two dimensions). A generic phase
(rest, activity, recovery; Vagal Tank Theory) adds a reading of the same cell in context; the standard
protocol phases live in corva/protocol.py. See corva/MODEL.md and corva/DECISIONS.md.

Every rule is tied to its literature in EVIDENCE (keys of corva/references.json) or is listed there
as an assumption that still needs validation; tests/test_corva_evidence.py enforces this.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

THRESHOLD_Z = 0.6  # D-06: "moderate" boundary of the standardized-magnitude scale (hopkins2009)
# magnitude grades of |z| (hopkins2009); below THRESHOLD_Z a change is at most "small" and the axis stays neutral
MAGNITUDES = ((0.2, "trivial"), (0.6, "kecil"), (1.2, "sedang"), (2.0, "besar"), (4.0, "sangat besar"))
MIN_RR_S = 60.0  # minimum valid RR per segment for a label (esco2014, munoz2015)
PHASES = ("rest", "activity", "recovery")

# (x zone, y zone) -> (code, label, meaning); CorVa names, alternatives from each source in ALT_NAMES (D-07)
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


# D-07: every alternative name the sources give for a cell. kind: "istilah" = the source's own term,
# "analogi" = a region of a different two-axis model (Russell: arousal × valence, not cortical × vagal).
# A source starting with "internal:" is a label from this project, not from the literature.
ALT_NAMES = {
    "Q1": [("Fokus", "internal:research-view-v1", "istilah"), ("concentrating", "bird2018", "istilah"),
           ("terlibat dalam tugas (engagement)", "pope1995", "istilah"),
           ("regulasi diri adaptif", "thayer2009", "istilah"), ("siaga (alert)", "russell1980", "analogi")],
    "Q2": [("Tenang", "internal:research-view-v1", "istilah"), ("relaxed", "bird2018", "istilah"),
           ("pemulihan vagal", "laborde2018", "istilah"), ("rileks / tenang (relaxed, calm)", "russell1980", "analogi")],
    "Q3": [("lelah / mengantuk", "borghini2014", "istilah"), ("pemulihan awal", "stanley2013", "istilah"),
           ("mengantuk / lesu (sleepy, tired)", "russell1980", "analogi")],
    "Q4": [("Teraktivasi", "internal:research-view-v1", "istilah"), ("stres", "ehrhardt2022", "istilah"),
           ("beban kerja mental tinggi", "borghini2014", "istilah"), ("disinhibisi regulasi", "thayer2000", "istilah"),
           ("tegang (tense, distressed)", "russell1980", "analogi")],
    "X_HIGH": [("arousal kortikal naik", "barry2007", "istilah"), ("concentrating", "bird2018", "istilah")],
    "X_LOW": [("arousal kortikal turun", "barry2007", "istilah")],
    "Y_HIGH": [("tonus vagal meningkat", "laborde2017", "istilah")],
    "Y_LOW": [("penarikan vagal (vagal withdrawal)", "laborde2017", "istilah")],
    "NEUTRAL": [("Indeterminan", "internal:research-view-v1", "istilah"), ("neutral", "bird2018", "istilah")],
    "NO_DATA": [],
}

# Literature behind each rule: element -> {"refs": [...], "basis": why}. An element without refs must
# say "assumption": True and name the decision or validation step that will settle it.
EVIDENCE = {
    "axis_x": {"refs": ["krigolson2017", "cannard2021", "barry2007", "ehrhardt2022", "borghini2014", "crabbe2004"],
               "basis": "X = rata-rata z log(β/α) empat kanal (D-09); spektrum Muse sahih; alfa turun dan beta naik "
                        "saat arousal dan beban kognitif naik; dipakai rasio karena saat latihan daya absolut semua pita ikut naik"},
    "axis_y": {"refs": ["laborde2017", "shaffer2017", "munoz2015", "esco2014", "griadhi2026"],
               "basis": "RMSSD menandai aktivitas vagal jantung pada rekaman pendek; diambil dari RR EKG Polar "
                        "karena RMSSD PPG dahi ditaksir berlebih"},
    "two_axes": {"refs": ["berntson1991", "russell1980", "thayer2000", "thayer2009", "kubota2001", "candiarivera2022"],
                 "basis": "keadaan perlu dua sumbu ortogonal; integrasi neuroviseral menghubungkan fungsi prefrontal dan vagal"},
    "y_log": {"refs": ["plews2012", "esco2014"],
              "basis": "Y = z lnRMSSD terhadap R0 (D-10): transformasi log lazim untuk pemantauan atlet dan "
                       "membuat sebaran RMSSD lebih simetris"},
    "x_alternative": {"refs": ["pope1995"],
                      "basis": "indeks engagement beta/(alfa + theta) dihitung per jendela sebagai pembanding, tidak dipakai "
                               "untuk label (D-09)"},
    "qualitative_labels": {"refs": ["russell1980", "bird2018"],
                           "basis": "penamaan wilayah pada ruang dua sumbu; kelas keadaan kualitatif dari Muse"},
    "threshold": {"refs": ["hopkins2009"],
                  "basis": "zona netral |z| < 0,6 = batas 'sedang' skala besaran Hopkins; diadaptasi dari SD antarsubjek "
                           "ke z robust terhadap R0 orang itu, sehingga tetap diuji di validasi v0.5"},
    "phases": {"refs": ["laborde2018", "stanley2013"],
               "basis": "kendali vagal dibaca saat istirahat, reaktivitas, dan pemulihan; kinetika pemulihan pascalatihan"},
    "min_rr": {"refs": ["esco2014", "munoz2015"],
               "basis": "label per fase hanya bila ruas analisis memiliki ≥ 60 s RR valid (D-11): lnRMSSD 60 s sesuai "
                        "dengan 5 menit; 120 s hampir sempurna"},
    "q3_qualifier": {"refs": ["borghini2014", "klimesch1999", "stanley2013"],
                     "basis": "z log(θ/β) ≥ 0,6 (ambang D-06) = lelah/mengantuk (D-12): theta bersama delta/alfa naik saat "
                              "lelah; pemulihan vagal tertinggal setelah latihan"},
    "Q1": {"refs": ["thayer2009", "kubota2001"], "basis": "keterlibatan kortikal dengan regulasi vagal yang terjaga"},
    "Q2": {"refs": ["barry2007", "laborde2018", "stanley2013"], "basis": "alfa naik (arousal turun) bersama vagal naik (istirahat/pemulihan)"},
    "Q3": {"refs": ["borghini2014", "stanley2013"], "basis": "korteks melambat dengan vagal rendah: lelah, atau pemulihan awal"},
    "Q4": {"refs": ["ehrhardt2022", "borghini2014", "thayer2000", "laborde2017"],
           "basis": "alfa frontal turun/beta naik saat beban, disertai penarikan vagal"},
    "X_HIGH": {"refs": ["barry2007", "ehrhardt2022"], "basis": "aktivasi kortikal saja"},
    "X_LOW": {"refs": ["barry2007"], "basis": "perlambatan kortikal saja"},
    "Y_HIGH": {"refs": ["laborde2017"], "basis": "kenaikan vagal saja"},
    "Y_LOW": {"refs": ["laborde2017"], "basis": "penarikan vagal saja"},
    "NEUTRAL": {"refs": ["hopkins2009"], "basis": "perubahan di kedua sumbu paling banyak 'kecil' (|z| < 0,6)"},
    "NO_DATA": {"refs": ["esco2014", "munoz2015"], "basis": "RR valid atau EEG bersih terlalu sedikit untuk label"},
}

_REFS_FILE = Path(__file__).with_name("references.json")


def references() -> dict:
    """The bibliography (corva/references.json) without its _about note."""
    data = json.loads(_REFS_FILE.read_text(encoding="utf-8"))
    return {k: v for k, v in data.items() if not k.startswith("_")}


def cite(key: str) -> str:
    """Short citation, e.g. 'Barry dkk. (2007)'."""
    r = references()[key]
    if len(r["authors"]) == 1 and len(r["authors"][0].split()) > 2:  # corporate author, e.g. a task force
        return f"{' '.join(r['authors'][0].split()[:2])} ({r['year']})"
    names = [a.split()[0] for a in r["authors"] if a != "et al."]
    if "et al." in r["authors"] or not r["authors_complete"] and len(names) < 3:
        return f"{names[0]} dkk. ({r['year']})"
    who = names[0] if len(names) == 1 else f"{names[0]} & {names[1]}" if len(names) == 2 else f"{names[0]} dkk."
    return f"{who} ({r['year']})"


def magnitude(z: float | None) -> str | None:
    """Hopkins grade of |z|: trivial, kecil, sedang, besar, sangat besar, amat sangat besar."""
    if not _finite(z):
        return None
    for limit, name in MAGNITUDES:
        if abs(z) < limit:
            return name
    return "amat sangat besar"


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
                "x_magnitude": magnitude(x_z), "y_magnitude": magnitude(y_z), "alternatives": [],
                "phase": phase, "phase_reading": None, "qualifier": None, "refs": EVIDENCE[code]["refs"]}
    code, label, meaning = CELLS[(zx, zy)]
    phase = phase if phase in PHASES else None
    reading = PHASE_READING.get(code, {}).get(phase) if phase else None
    qualifier = None
    if code == "Q3":
        if _finite(theta_beta_z) and theta_beta_z >= threshold:
            qualifier = "lelah/mengantuk (θ/β naik)"
        elif phase == "recovery":
            qualifier = "pemulihan awal (vagal belum pulih)"
    refs = list(EVIDENCE[code]["refs"])
    if reading:
        refs += [r for r in EVIDENCE["phases"]["refs"] if r not in refs]
    if qualifier:
        refs += [r for r in EVIDENCE["q3_qualifier"]["refs"] if r not in refs]
    alternatives = [{"name": n, "source": src, "kind": kind} for n, src, kind in ALT_NAMES[code]]
    return {"code": code, "label": label, "meaning": meaning, "x_zone": zx, "y_zone": zy,
            "x_magnitude": magnitude(x_z), "y_magnitude": magnitude(y_z), "alternatives": alternatives,
            "phase": phase, "phase_reading": reading, "qualifier": qualifier, "refs": refs}
