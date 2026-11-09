"""Write corva/EVIDENCE.md from EVIDENCE (labels.py) and references.json.

    python -m corva.evidence_md

tests/test_corva_evidence.py fails when EVIDENCE.md is out of date, so the evidence map people read
is always the one the code uses.
"""

from __future__ import annotations

from pathlib import Path

from .labels import CELLS, EVIDENCE, NO_DATA, cite, references

OUT = Path(__file__).with_name("EVIDENCE.md")
ELEMENT_NAMES = {
    "axis_x": "Sumbu X: log(β/α) EEG Muse",
    "axis_y": "Sumbu Y: RMSSD RR Polar",
    "y_log": "Y memakai lnRMSSD (D-10)",
    "x_alternative": "Alternatif X: β/(α+θ) (D-09)",
    "two_axes": "Dua sumbu ortogonal (bidang CorVa)",
    "qualitative_labels": "Penamaan kualitatif wilayah",
    "threshold": "Ambang zona netral ±0,5 z (D-06)",
    "phases": "Konteks fase istirahat/aktivitas/pemulihan",
    "min_rr": "Syarat ≥ 60 s RR valid per ruas",
    "q3_qualifier": "Penanda tambahan Q3 (θ/β, fase pemulihan)",
}


def _label(code: str) -> str:
    for c, label, _ in [*CELLS.values(), NO_DATA]:
        if c == code:
            return f"`{c}` {label}"
    return ELEMENT_NAMES.get(code, code)


def render() -> str:
    refs = references()
    lines = [
        "# Peta bukti CASS-NV (CorVa Space)",
        "",
        "<!-- Dihasilkan oleh `python -m corva.evidence_md` dari corva/labels.py (EVIDENCE) dan",
        "     corva/references.json. Jangan disunting langsung. -->",
        "",
        "Setiap aturan model menunjuk rujukannya, atau dinyatakan sebagai **asumsi** yang masih harus",
        "divalidasi. Tes `tests/test_corva_evidence.py` gagal bila ada aturan tanpa rujukan yang tidak",
        "dinyatakan asumsi, rujukan yang tidak dikenal, rujukan yang tidak dipakai, atau berkas ini tidak mutakhir.",
        "",
        "## Aturan → rujukan",
        "",
        "| Unsur | Rujukan | Dasar |",
        "|---|---|---|",
    ]
    for key, ev in EVIDENCE.items():
        cites = "; ".join(cite(k) for k in ev["refs"]) if ev["refs"] else "**asumsi**"
        lines.append(f"| {_label(key)} | {cites} | {ev['basis']} |")
    lines += [
        "",
        "## Rujukan",
        "",
        "Status: ✓ = DOI dan penulis sudah dicek; ⚠ = perlu dicek ke naskah asli sebelum dikutip.",
        "*Dibaca* = bagian yang sudah dibaca untuk model ini.",
        "",
    ]
    for key in sorted(refs):
        r = refs[key]
        authors = ", ".join(a for a in r["authors"] if a != "et al.")
        if not r["authors_complete"]:
            authors += ", dkk. (daftar penulis belum lengkap)"
        where = r["journal"] + "".join([f" {r['volume']}" if r.get("volume") else "",
                                         f"({r['issue']})" if r.get("issue") else "",
                                         f":{r['pages']}" if r.get("pages") else ""])
        doi = f" doi:{r['doi']}" if r["doi"] else " (tanpa DOI)"
        ok = r["authors_complete"] and r["doi_verified"]
        flags = [] if ok else [x for x, bad in (("DOI belum terverifikasi", r["doi"] and not r["doi_verified"]),
                                                  ("penulis belum lengkap", not r["authors_complete"]),
                                                  ("tanpa DOI", not r["doi"])) if bad]
        status = "✓" if ok else "⚠ " + ", ".join(flags)
        used = ", ".join(_label(k) for k, ev in EVIDENCE.items() if key in ev["refs"])
        lines += [
            f"- **[{key}]** {authors} ({r['year']}). {r['title']}. *{where}*.{doi}",
            f"  {status} · *dibaca:* {r['read']}",
            f"  Temuan yang dipakai: {r['finding']}",
            f"  Dipakai untuk: {used}",
        ]
    return "\n".join(lines) + "\n"


def main() -> None:
    OUT.write_text(render(), encoding="utf-8")
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
