"""CorVa v0.5 validation tool: analyse many recorded sessions at once (D-23).

    python -m corva.validate <folder with sessions> --out <output folder> [--norms-out norms.json]

Code only: run it on data in the private research repository, never commit participant data here.

Outputs in --out:
- corva_phases.csv       one row per session × phase: label, comparison, medians, change from R0, KSS, rileks
- corva_conclusions.csv  one row per session × conclusion
- corva_errors.csv       sessions that could not be analysed, with the reason
- corva_report.json      agreement with the protocol expectation, conclusions vs subjective scales (Cohen's
                         kappa, Spearman), test–retest reliability (ICC(2,1)) for participants with ≥ 2 sessions
- corva_report.md        the same in words
--norms-out writes reference-group norms (corva/norms.py) from the first session of every participant.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path

import numpy as np

from . import norms as norms_mod
from . import protocol
from .session import analyze_session

KSS_SLEEPY = 7  # KSS ≥ 7 = sleepy (akerstedt1990)
RELAXED = 6  # rileks ≥ 6 = above the scale midpoint (assumption, D-23)
RELAX_PHASES = ("eo_deep", "ec_reg", "ec_deep")
MIN_ICC_N = 3

EVIDENCE = {
    "val_agreement": {"refs": ["barry2007", "lehrer2014", "laborde2022"],
                      "basis": "persentase fase yang sesuai harapan protokol, per fase dan keseluruhan (D-23)"},
    "val_kss_threshold": {"refs": ["akerstedt1990"],
                          "basis": "KSS ≥ 7 = mengantuk, pembanding subjektif kesimpulan kelelahan/mengantuk (D-23)"},
    "val_relax_threshold": {"refs": [], "assumption": True,
                            "basis": "rileks ≥ 6 (di atas titik tengah skala 1–9) = merasa rileks, pembanding respons rileks (D-23)"},
    "val_kappa": {"refs": ["cohen1960"],
                  "basis": "kesepakatan kesimpulan fisiologis dengan skala subjektif dinyatakan dengan Cohen's kappa (D-23)"},
    "val_correlation": {"refs": [], "assumption": True,
                        "basis": "korelasi Spearman z vagal ↔ rileks dan z θ/β ↔ KSS sebagai ringkasan deskriptif (D-23)"},
    "val_icc": {"refs": ["shrout1979", "koo2016"],
                "basis": "reliabilitas uji-ulang dengan ICC(2,1) (dua arah acak, kesepakatan absolut) pada dua sesi pertama "
                         "tiap peserta; tafsir menurut Koo & Li (D-23)"},
}

PHASE_FIELDS = ["participant", "session", "start_unix", "phase_id", "recorded", "adequate", "code", "qualifier",
                "comparison", "x_z", "y_z", "theta_beta_z", "engagement_z", "d_log_beta_alpha", "d_ln_rmssd",
                "rr_valid_s", "eeg_clean_s", "kss", "rileks"]


def find_sessions(root: Path) -> list[Path]:
    """Folders under root with EEG, RR and a marker file that contains CorVa protocol markers."""
    out = []
    for mk in sorted(Path(root).rglob("marker.csv")):
        d = mk.parent
        if (d / "muse_eeg.csv").is_file() and (d / "polar_rr.csv").is_file():
            try:
                if protocol.MARKER_PREFIX in mk.read_text(encoding="utf-8", errors="replace"):
                    out.append(d)
            except OSError:
                continue
    return out


def session_identity(folder: Path) -> tuple[str, float | None]:
    """(participant id, start time) from session.json: the session name, else the folder name."""
    try:
        meta = json.loads((folder / "session.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        meta = {}
    return (meta.get("participant") or meta.get("name") or folder.name), meta.get("start_unix")


def kappa(pairs: list[tuple[bool, bool]]) -> dict:
    """Cohen's kappa for two binary classifications (cohen1960), with the 2 × 2 counts."""
    n = len(pairs)
    a = sum(1 for x, y in pairs if x and y)
    b = sum(1 for x, y in pairs if x and not y)
    c = sum(1 for x, y in pairs if not x and y)
    d = n - a - b - c
    out = {"n": n, "both": a, "physio_only": b, "subjective_only": c, "neither": d, "agreement": None, "kappa": None}
    if not n:
        return out
    po = (a + d) / n
    pe = ((a + b) * (a + c) + (c + d) * (b + d)) / n ** 2
    out["agreement"] = round(po, 3)
    out["kappa"] = round((po - pe) / (1 - pe), 3) if pe < 1 else None
    return out


def spearman(x: list[float], y: list[float]) -> dict:
    pts = [(a, b) for a, b in zip(x, y) if a is not None and b is not None and math.isfinite(a) and math.isfinite(b)]
    if len(pts) < 5:
        return {"n": len(pts), "rho": None, "p": None}
    from scipy.stats import spearmanr

    res = spearmanr([p[0] for p in pts], [p[1] for p in pts])
    rho, p = float(res.statistic), float(res.pvalue)
    return {"n": len(pts), "rho": round(rho, 3) if math.isfinite(rho) else None, "p": round(p, 4) if math.isfinite(p) else None}


def icc_2_1(pairs: list[tuple[float, float]]) -> float | None:
    """ICC(2,1): two-way random effects, absolute agreement, single measurement (shrout1979)."""
    data = np.array([p for p in pairs if all(v is not None and math.isfinite(v) for v in p)], dtype=float)
    n, k = data.shape if data.size else (0, 2)
    if n < MIN_ICC_N:
        return None
    grand = data.mean()
    msr = k * ((data.mean(axis=1) - grand) ** 2).sum() / (n - 1)
    msc = n * ((data.mean(axis=0) - grand) ** 2).sum() / (k - 1)
    sse = ((data - data.mean(axis=1, keepdims=True) - data.mean(axis=0, keepdims=True) + grand) ** 2).sum()
    mse = sse / ((n - 1) * (k - 1))
    denom = msr + (k - 1) * mse + k * (msc - mse) / n
    return round(float((msr - mse) / denom), 3) if denom > 0 else None


def icc_reading(v: float | None) -> str | None:
    """Koo & Li (2016): < 0.5 poor, 0.5–0.75 moderate, 0.75–0.9 good, > 0.9 excellent."""
    if v is None:
        return None
    return "buruk" if v < 0.5 else "sedang" if v < 0.75 else "baik" if v < 0.9 else "sangat baik"


def run(root: Path, out: Path, norms_out: Path | None = None) -> dict:
    out.mkdir(parents=True, exist_ok=True)
    rows, concl_rows, errors, sessions = [], [], [], []
    for folder in find_sessions(root):
        pid, start = session_identity(folder)
        try:
            res = analyze_session(folder)
        except (ValueError, OSError) as exc:
            errors.append({"session": str(folder), "error": str(exc)})
            continue
        sessions.append({"participant": pid, "session": folder.name, "start_unix": start, "result": res})
        for p in res["phases"]:
            subj, med, delta, lab = p.get("subjective") or {}, p.get("medians") or {}, p.get("delta") or {}, p["label"]
            rows.append({"participant": pid, "session": folder.name, "start_unix": start, "phase_id": p["id"],
                         "recorded": p["recorded"], "adequate": p["adequate"], "code": lab["code"],
                         "qualifier": lab["qualifier"], "comparison": p["comparison"],
                         "x_z": med.get("x_z"), "y_z": med.get("y_z"), "theta_beta_z": med.get("theta_beta_z"),
                         "engagement_z": med.get("engagement_z"), "d_log_beta_alpha": delta.get("log_beta_alpha"),
                         "d_ln_rmssd": delta.get("ln_rmssd"), "rr_valid_s": (p.get("data") or {}).get("rr_valid_s"),
                         "eeg_clean_s": (p.get("data") or {}).get("eeg_clean_s"),
                         "kss": subj.get("KSS"), "rileks": subj.get("rileks")})
        for c in res["conclusions"]["items"]:
            concl_rows.append({"participant": pid, "session": folder.name, "id": c["id"], "status": c["status"],
                               "phases": " ".join(c["phases"]), "narrative": c["narrative"]})

    _write_csv(out / "corva_phases.csv", rows, PHASE_FIELDS)
    _write_csv(out / "corva_conclusions.csv", concl_rows, ["participant", "session", "id", "status", "phases", "narrative"])
    _write_csv(out / "corva_errors.csv", errors, ["session", "error"])

    adequate = [r for r in rows if r["adequate"]]
    report = {"n_sessions": len(sessions), "n_participants": len({s["participant"] for s in sessions}),
              "n_errors": len(errors), "n_adequate_phases": len(adequate)}

    # agreement with the protocol expectation
    per_phase = {}
    for ph in protocol.PROTOCOL:
        if ph["reference"]:
            continue
        cmp_ = [r for r in adequate if r["phase_id"] == ph["id"] and r["comparison"] in ("sesuai harapan", "berbeda dari harapan")]
        ok = sum(r["comparison"] == "sesuai harapan" for r in cmp_)
        per_phase[ph["id"]] = {"name": ph["name"], "n": len(cmp_), "as_expected": ok,
                               "pct": round(100 * ok / len(cmp_), 1) if cmp_ else None}
    tot = sum(v["n"] for v in per_phase.values())
    report["expectation"] = {"per_phase": per_phase, "n": tot,
                             "pct": round(100 * sum(v["as_expected"] for v in per_phase.values()) / tot, 1) if tot else None}

    # conclusions vs subjective scales (phase level)
    fat = [(r["code"] == "Q3" and (r["qualifier"] or "").startswith("lelah"), r["kss"] >= KSS_SLEEPY)
           for r in adequate if r["kss"] is not None]
    rel = [(r["comparison"] == "sesuai harapan", r["rileks"] >= RELAXED)
           for r in adequate if r["phase_id"] in RELAX_PHASES and r["rileks"] is not None]
    report["subjective"] = {
        "fatigue_vs_kss": {**kappa(fat), "rule": f"fisiologis: Q3 dengan θ/β naik; subjektif: KSS ≥ {KSS_SLEEPY}"},
        "relax_vs_rating": {**kappa(rel), "rule": f"fisiologis: fase rileks sesuai harapan; subjektif: rileks ≥ {RELAXED}"},
        "vagal_z_vs_rileks": spearman([r["y_z"] for r in adequate], [r["rileks"] for r in adequate]),
        "theta_beta_z_vs_kss": spearman([r["theta_beta_z"] for r in adequate], [r["kss"] for r in adequate]),
    }

    # test–retest: first two sessions per participant, change from R0 per phase and R0 level
    by_p: dict = {}
    for s in sorted(sessions, key=lambda s: (s["start_unix"] or 0, s["session"])):
        by_p.setdefault(s["participant"], []).append(s["result"])
    pairs_ = [v[:2] for v in by_p.values() if len(v) >= 2]
    icc = {}
    for k in norms_mod.KEYS:
        icc[f"R0_{k}"] = icc_2_1([(a["r0"]["raw"][k], b["r0"]["raw"][k]) for a, b in pairs_
                                  if a["r0"]["adequate"] and b["r0"]["adequate"]])
        for ph in protocol.PROTOCOL:
            if ph["reference"]:
                continue
            vals = []
            for a, b in pairs_:
                pa = next(p for p in a["phases"] if p["id"] == ph["id"])
                pb = next(p for p in b["phases"] if p["id"] == ph["id"])
                if pa["adequate"] and pb["adequate"]:
                    vals.append((pa["delta"][k], pb["delta"][k]))
            icc[f"{ph['id']}_{k}"] = icc_2_1(vals)
    report["test_retest"] = {"n_participants": len(pairs_),
                             "icc": {k: {"icc": v, "reading": icc_reading(v)} for k, v in icc.items()}}

    if norms_out:
        first = [v[0] for v in by_p.values()]
        norm_rows = [{"participant": i, "phase_id": p["id"], **(p.get("delta") or {})}
                     for i, res in enumerate(first) for p in res["phases"] if p.get("adequate") and not p.get("reference")]
        nm = norms_mod.build(norm_rows)
        norms_out.parent.mkdir(parents=True, exist_ok=True)
        norms_out.write_text(json.dumps(nm, indent=2, ensure_ascii=False), encoding="utf-8")
        report["norms"] = {"file": str(norms_out), "n_participants": nm["n_participants"], "provisional": nm["provisional"]}

    (out / "corva_report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    (out / "corva_report.md").write_text(report_md(report), encoding="utf-8")
    return report


def _fmt(v, nd=2):
    return "–" if v is None else f"{v:.{nd}f}".replace(".", ",")


def report_md(r: dict) -> str:
    e, s, t = r["expectation"], r["subjective"], r["test_retest"]
    lines = ["# Laporan validasi CorVa", "",
             f"{r['n_sessions']} sesi dari {r['n_participants']} peserta; {r['n_adequate_phases']} fase memenuhi syarat data; "
             f"{r['n_errors']} sesi gagal dianalisis (lihat corva_errors.csv).", "",
             "## Kesesuaian dengan harapan protokol", "",
             f"Keseluruhan: {_fmt(e['pct'], 1)} % dari {e['n']} fase.", "", "| Fase | n | Sesuai | % |", "|---|---|---|---|"]
    lines += [f"| {v['name']} | {v['n']} | {v['as_expected']} | {_fmt(v['pct'], 1)} |" for v in e["per_phase"].values()]
    lines += ["", "## Kesimpulan vs skala subjektif", ""]
    for key, title in (("fatigue_vs_kss", "Kelelahan/mengantuk vs KSS"), ("relax_vs_rating", "Respons rileks vs skala rileks")):
        k = s[key]
        lines.append(f"- **{title}** ({k['rule']}): n = {k['n']}, kesepakatan {_fmt(k['agreement'])}, "
                     f"κ = {_fmt(k['kappa'])} (keduanya {k['both']}, hanya fisiologis {k['physio_only']}, "
                     f"hanya subjektif {k['subjective_only']}, tidak keduanya {k['neither']}).")
    for key, title in (("vagal_z_vs_rileks", "z vagal ↔ rileks"), ("theta_beta_z_vs_kss", "z θ/β ↔ KSS")):
        c = s[key]
        lines.append(f"- **{title}**: Spearman ρ = {_fmt(c['rho'])} (n = {c['n']}, p = {_fmt(c['p'], 4)}).")
    lines += ["", "## Reliabilitas uji-ulang (ICC(2,1), dua sesi pertama per peserta)", "",
              f"Peserta dengan ≥ 2 sesi: {t['n_participants']}. Tafsir menurut Koo & Li (2016).", "",
              "| Ukuran | ICC | Tafsir |", "|---|---|---|"]
    lines += [f"| {k} | {_fmt(v['icc'])} | {v['reading'] or '–'} |" for k, v in t["icc"].items()]
    if r.get("norms"):
        n = r["norms"]
        lines += ["", f"Norma kelompok ditulis ke `{n['file']}` (N = {n['n_participants']}"
                  + (", **sementara**: N < 20" if n["provisional"] else "") + ")."]
    lines += ["", "Deskriptif; data peserta tidak boleh di-commit ke repo publik."]
    return "\n".join(lines) + "\n"


def _write_csv(path: Path, rows: list[dict], fields: list[str]) -> None:
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow({k: "" if r.get(k) is None else r.get(k) for k in fields})


def main() -> None:
    ap = argparse.ArgumentParser(description="Validasi CorVa: analisis banyak sesi sekaligus")
    ap.add_argument("folder", type=Path, help="folder berisi sesi rekaman (dicari rekursif)")
    ap.add_argument("--out", type=Path, required=True, help="folder keluaran (di repo riset privat)")
    ap.add_argument("--norms-out", type=Path, help="tulis norma kelompok acuan ke berkas ini")
    args = ap.parse_args()
    report = run(args.folder, args.out, args.norms_out)
    print(report_md(report))


if __name__ == "__main__":
    main()
