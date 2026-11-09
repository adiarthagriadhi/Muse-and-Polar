"""CorVa Space standard protocol: the phases the live dashboard guides the participant through.

Relaks (baseline) followed by a 2 × 2 of eyes (open/closed) × breathing (spontaneous/slow-deep).
Durations follow the literature in EVIDENCE: a 5 min baseline (1 min settling + 4 min analysis) and
3 min per condition (1 min settling + 2 min analysis). Each phase start is written as a marker
"CorVa: <name>" so the explorer can rebuild the phases from marker.csv.
"""

from __future__ import annotations

MARKER_PREFIX = "CorVa: "
SCALE_PREFIX = "CorVa skala: "  # subjective ratings after a phase, e.g. "CorVa skala: ec_reg KSS=7 rileks=6"
RATING_TIMEOUT_S = 45  # unanswered ratings are skipped so the protocol keeps moving

# subjective scales asked after every phase (D-22): id, question, low/high anchor, labels per value
SCALES = [
    {"id": "KSS", "question": "Seberapa mengantuk Anda selama fase tadi?",
     "labels": {1: "sangat waspada", 3: "waspada", 5: "tidak waspada, tidak mengantuk",
                7: "mengantuk, tanpa usaha untuk tetap terjaga", 9: "sangat mengantuk, melawan kantuk"}},
    {"id": "rileks", "question": "Seberapa rileks Anda selama fase tadi?",
     "labels": {1: "sangat tegang", 3: "tegang", 5: "biasa saja", 7: "rileks", 9: "sangat rileks"}},
]
SLOW_BREATHS_PER_MIN = 6.0  # resonance region, ~0.1 Hz (lehrer2014); individual resonance may differ (shaffer2020)

# id, name, seconds, settle_s (excluded from analysis), eyes, breathing, instruction, expected cells
PROTOCOL = [
    {"id": "baseline", "name": "Relaks (baseline)", "seconds": 300, "settle_s": 60, "eyes": "open", "breathing": "spontaneous",
     "instruction": "Duduk tenang dan rileks, mata terbuka menatap satu titik, bernapas biasa. Jangan berbicara atau bergerak.",
     "expected": ["NEUTRAL"], "reference": True},
    {"id": "eo_reg", "name": "Mata terbuka · napas biasa", "seconds": 180, "settle_s": 60, "eyes": "open", "breathing": "spontaneous",
     "instruction": "Mata tetap terbuka, bernapas biasa dan teratur, tanpa mengatur iramanya.",
     "expected": ["NEUTRAL"], "reference": False},
    {"id": "eo_deep", "name": "Mata terbuka · napas dalam", "seconds": 180, "settle_s": 60, "eyes": "open", "breathing": "slow",
     "instruction": "Mata terbuka. Ikuti pemandu: tarik napas dalam 5 detik, hembuskan 5 detik (6 napas per menit).",
     "expected": ["Q2", "Y_HIGH"], "reference": False},
    {"id": "ec_reg", "name": "Mata tertutup · napas biasa", "seconds": 180, "settle_s": 60, "eyes": "closed", "breathing": "spontaneous",
     "instruction": "Tutup mata, bernapas biasa dan teratur. Bunyi akan menandai pergantian fase.",
     "expected": ["X_LOW", "Q2"], "reference": False},
    {"id": "ec_deep", "name": "Mata tertutup · napas dalam", "seconds": 180, "settle_s": 60, "eyes": "closed", "breathing": "slow",
     "instruction": "Mata tetap tertutup. Ikuti bunyi pemandu: nada naik = tarik napas 5 detik, nada turun = hembuskan 5 detik.",
     "expected": ["Q2"], "reference": False},
]

EVIDENCE = {
    "protocol_baseline": {"refs": ["taskforce1996", "bourdillon2017", "laborde2017"],
                          "basis": "rekaman HRV jangka pendek standar 5 menit = 1 menit stabilisasi + 4 menit analisis"},
    "protocol_block": {"refs": ["bourdillon2017", "munoz2015", "esco2014", "gudmundsson2007"],
                       "basis": "RMSSD sah dengan jendela 2 menit setelah 1 menit stabilisasi; EEG istirahat stabil dengan epoch ≥ 40 s"},
    "protocol_eyes": {"refs": ["barry2007"],
                      "basis": "membuka mata menurunkan alfa dan menaikkan arousal; mata tertutup sebagai kondisi alfa tinggi"},
    "protocol_slow_breathing": {"refs": ["lehrer2014", "laborde2022", "zaccaro2018", "shaffer2020"],
                                "basis": "6 napas/menit (~0,1 Hz) menaikkan HRV vagal; alfa naik dan theta turun; resonansi individual bisa berbeda"},
    "scale_kss": {"refs": ["akerstedt1990"],
                  "basis": "Karolinska Sleepiness Scale 1–9 setelah tiap fase sebagai pembanding subjektif kesimpulan "
                           "kelelahan/mengantuk (D-22); terjemahan label bahasa Indonesia belum divalidasi"},
    "scale_relax": {"refs": [], "assumption": True,
                    "basis": "skala rileks satu butir 1–9 setelah tiap fase sebagai pembanding kesimpulan respons rileks "
                             "dan sulit rileks (D-22); asumsi, belum ada versi tervalidasi yang dipakai"},
    "protocol_carryover": {"refs": ["laborde2022"],
                           "basis": "efek napas lambat masih terlihat segera sesudah sesi, sehingga urutan blok bisa terbawa ke blok berikutnya"},
}

# what each block should show if the model behaves as the literature predicts
EXPECTATION_REFS = {"eo_deep": ["lehrer2014", "laborde2022", "zaccaro2018"], "ec_reg": ["barry2007"],
                    "ec_deep": ["barry2007", "laborde2022", "zaccaro2018"], "eo_reg": [], "baseline": []}


def total_seconds() -> int:
    return sum(p["seconds"] for p in PROTOCOL)


def marker_label(phase_id: str) -> str:
    return MARKER_PREFIX + next(p["name"] for p in PROTOCOL if p["id"] == phase_id)


def phase_from_marker(label: str) -> str | None:
    """Phase id from a marker written by the dashboard, or None."""
    if not label.startswith(MARKER_PREFIX):
        return None
    name = label[len(MARKER_PREFIX):].strip()
    return next((p["id"] for p in PROTOCOL if p["name"] == name), None)


def compare(phase_id: str, code: str) -> str | None:
    """'sesuai harapan' / 'berbeda dari harapan' for an observed cell in a protocol phase."""
    p = next((p for p in PROTOCOL if p["id"] == phase_id), None)
    if p is None or code == "NO_DATA":
        return None
    return "sesuai harapan" if code in p["expected"] else "berbeda dari harapan"


def scale_label(phase_id: str, ratings: dict | None) -> str:
    """Marker for the ratings after a phase; None ratings = skipped."""
    if not ratings:
        return f"{SCALE_PREFIX}{phase_id} dilewati"
    return SCALE_PREFIX + phase_id + "".join(f" {k}={int(v)}" for k, v in ratings.items())


def parse_scale(label: str) -> tuple[str, dict] | None:
    """(phase id, {scale id: value}) from a ratings marker, {} when skipped; None for other markers."""
    if not label.startswith(SCALE_PREFIX):
        return None
    parts = label[len(SCALE_PREFIX):].split()
    if not parts or parts[0] not in {p["id"] for p in PROTOCOL}:
        return None
    known = {s["id"] for s in SCALES}
    values = {}
    for part in parts[1:]:
        k, _, v = part.partition("=")
        if k in known and v.isdigit() and 1 <= int(v) <= 9:
            values[k] = int(v)
    return parts[0], values


def as_json() -> dict:
    """Protocol for the dashboard (GET /api/corva/protocol)."""
    return {"marker_prefix": MARKER_PREFIX, "scale_prefix": SCALE_PREFIX, "rating_timeout_s": RATING_TIMEOUT_S,
            "scales": SCALES, "slow_breaths_per_min": SLOW_BREATHS_PER_MIN,
            "total_seconds": total_seconds(), "phases": PROTOCOL}
