"""CorVa Space standard protocol: the phases the live dashboard guides the participant through.

Relaks (baseline) followed by a 2 × 2 of eyes (open/closed) × breathing (spontaneous/slow-deep).
Durations follow the literature in EVIDENCE: a 5 min baseline (1 min settling + 4 min analysis) and
3 min per condition (1 min settling + 2 min analysis). Each phase start is written as a marker
"CorVa: <name>" so the explorer can rebuild the phases from marker.csv.
"""

from __future__ import annotations

MARKER_PREFIX = "CorVa: "
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


def as_json() -> dict:
    """Protocol for the dashboard (GET /api/corva/protocol)."""
    return {"marker_prefix": MARKER_PREFIX, "slow_breaths_per_min": SLOW_BREATHS_PER_MIN,
            "total_seconds": total_seconds(), "phases": PROTOCOL}
