"""CorVa Space conclusions (D-19 to D-21): a narrative that combines the phase labels of a session, and the
change between a session before and after an intervention (e.g. meditation training).

Within one session the reference is the person's own baseline R0, so a single session shows the *response
pattern* (reactivity, laborde2018): does the cortex slow when the eyes close, does vagal activity rise with
slow breathing, is there load or fatigue at rest compared with the baseline. A *state* compared with an
earlier time needs an outside reference: an earlier session (compare()) or, later, a reference group (v0.5).

Each conclusion carries its references. Where the literature supports the components (direction of each
marker in each condition) but not the combination into one conclusion, the conclusion is written as
"Diasumsikan …" and flagged ``assumed`` (D-21); it is tested against subjective scales in v0.5.
Descriptive, relative to the baseline, not a diagnosis.
"""

from __future__ import annotations

import math

from . import labels

THRESHOLD_Z = labels.THRESHOLD_Z  # same boundary as the neutral zone (D-06); between sessions an assumption
RELAX_EYES = ("ec_reg", "ec_deep")  # eyes closed: cortex expected to slow (barry2007)
RELAX_BREATH = ("eo_deep", "ec_deep")  # slow breathing: vagal expected to rise (lehrer2014, laborde2022)
REST_OPEN = "eo_reg"  # eyes open, spontaneous breathing: a rest control without task

# id -> title, status ("rujukan" = combination supported; "asumsi" = components supported, combination assumed)
CONCLUSIONS = {
    "relax_typical": ("Respons rileks khas", "rujukan"),
    "relax_cortical_difficulty": ("Sulit rileks secara kortikal", "asumsi"),
    "relax_vagal_difficulty": ("Sulit rileks secara vagal", "asumsi"),
    "cortical_load": ("Beban kortikal / berpikir berat", "rujukan"),
    "fatigue": ("Kelelahan / mengantuk", "rujukan"),
    "vagal_withdrawal_rest": ("Tegang / penarikan vagal saat istirahat", "asumsi"),
    "change_after": ("Perubahan sesudah intervensi (mis. meditasi)", "asumsi"),
}

EVIDENCE = {
    "concl_relax_typical": {"refs": ["barry2007", "lehrer2014", "laborde2022"],
                            "basis": "respons rileks khas: korteks melambat saat mata tertutup dan vagal naik saat napas "
                                     "6/menit, arah yang umumnya dijumpai (D-20)"},
    "concl_relax_cortical_difficulty": {"refs": ["barry2007"], "combination_assumed": True,
                                        "basis": "komponen: mata tertutup umumnya menaikkan alfa (korteks melambat); "
                                                 "tidak melambat = sulit rileks secara kortikal diasumsikan (D-21)"},
    "concl_relax_vagal_difficulty": {"refs": ["lehrer2014", "laborde2022", "laborde2018"], "combination_assumed": True,
                                     "basis": "komponen: napas 6/menit umumnya menaikkan HRV vagal; reaktivitas vagal "
                                              "(Vagal Tank Theory); tidak naik = sulit rileks secara vagal diasumsikan (D-21)"},
    "concl_cortical_load": {"refs": ["ehrhardt2022", "borghini2014"],
                            "basis": "alfa turun/beta naik (β/α naik) saat beban kognitif dan stres; bersama penarikan "
                                     "vagal (Q4) sesuai pola stres/beban mental (D-20)"},
    "concl_fatigue": {"refs": ["borghini2014", "klimesch1999"],
                      "basis": "Q3 dengan θ/β naik: theta naik bersama perlambatan kortikal saat lelah/mengantuk (D-20)"},
    "concl_vagal_withdrawal_rest": {"refs": ["laborde2017", "thayer2009"], "combination_assumed": True,
                                    "basis": "komponen: RMSSD turun = penarikan vagal; tonus vagal mencerminkan kapasitas "
                                             "regulasi; tanpa tugas = tegang diasumsikan (D-21)"},
    "concl_change_after": {"refs": ["laborde2022", "plews2012", "laborde2018"], "combination_assumed": True,
                           "basis": "lnRMSSD dipantau antarhari; latihan napas lambat mengubah HRV vagal; dibandingkan "
                                    "perubahan dari R0 masing-masing sesi (satuan asli), ambang 0,6 × skala R0 "
                                    "diasumsikan (D-19, D-21)"},
}

NOTE = ("Deskriptif: relatif terhadap baseline (R0) sesi ini, bukan norma populasi dan bukan diagnosis. "
        "Kesimpulan bertanda asumsi menggabungkan temuan rujukan dengan cara yang belum divalidasi (v0.5).")


def _fz(v) -> str:
    return "–" if v is None else ("−" if v < 0 else "+") + f"{abs(v):.2f}".replace(".", ",")


def _fn(v, nd=2) -> str:
    return "–" if v is None else f"{v:.{nd}f}".replace(".", ",")


def _num(v):
    return None if v is None or not math.isfinite(v) else round(float(v), 4)


def _item(cid: str, narrative: str, phases: list[str], extra_refs=(), title: str | None = None,
          short: str | None = None) -> dict:
    """title/short override the conclusion's title (used by compare() for each change)."""
    default_title, status = CONCLUSIONS[cid]
    title = title or default_title
    assumed = status == "asumsi"
    if assumed and not narrative.startswith("Diasumsikan"):
        narrative = "Diasumsikan " + narrative[0].lower() + narrative[1:]
    ev = EVIDENCE["concl_" + cid]
    refs = list(dict.fromkeys([*ev["refs"], *extra_refs]))
    return {"id": cid, "title": title, "status": status, "assumed": assumed, "narrative": narrative,
            "short": short or title.lower(), "phases": phases, "refs": refs}


def _phase_num(pid: str) -> int:
    from .protocol import PROTOCOL

    return next(i + 1 for i, p in enumerate(PROTOCOL) if p["id"] == pid)


def _where(p: dict) -> str:
    return f"fase {_phase_num(p['id'])} {p['name'].lower()}"


def conclude(result: dict) -> dict:
    """Conclusions for one session from its adequate phases. Returns {items, summary, note, missing}."""
    phases = {p["id"]: p for p in result["phases"]}
    ok = {k: p for k, p in phases.items() if p.get("adequate") and not p.get("reference")}
    missing = [p["name"] for p in result["phases"] if not p.get("reference") and not p.get("adequate")]
    if not result["r0"]["adequate"]:
        return {"items": [], "summary": "Belum ada kesimpulan: baseline R0 tidak memenuhi syarat data.",
                "note": NOTE, "missing": missing}
    items = []
    xz = lambda p: p["medians"]["x_z"]  # noqa: E731
    yz = lambda p: p["medians"]["y_z"]  # noqa: E731

    eyes = [ok[k] for k in RELAX_EYES if k in ok]
    breath = [ok[k] for k in RELAX_BREATH if k in ok]
    relax = {p["id"]: p for p in eyes + breath}

    # respons rileks khas: every adequate relaxation phase as expected (at least two of the three)
    if len(relax) >= 2 and all(p["comparison"] == "sesuai harapan" for p in relax.values()):
        parts = []
        if eyes:
            parts.append("saat mata tertutup korteks melambat (" + "; ".join(f"{_where(p)}: X {_fz(xz(p))}" for p in eyes) + ")")
        if breath:
            parts.append("saat napas dalam vagal naik (" + "; ".join(f"{_where(p)}: Y {_fz(yz(p))}" for p in breath) + ")")
        text = " dan ".join(parts)
        items.append(_item("relax_typical", text[0].upper() + text[1:] + ", sesuai respons yang umumnya dijumpai.",
                           list(relax)))

    slow_fail = [p for p in eyes if p["label"]["x_zone"] != "low"]
    if slow_fail:
        part = "sebagian: " if len(slow_fail) < len(eyes) else ""
        items.append(_item("relax_cortical_difficulty",
                           f"sulit rileks secara kortikal ({part}saat mata tertutup korteks tidak melambat seperti yang umumnya "
                           "terjadi: " + "; ".join(f"{_where(p)}: X {_fz(xz(p))}, {p['label']['x_magnitude']}" for p in slow_fail) + ").",
                           [p["id"] for p in slow_fail]))

    vagal_fail = [p for p in breath if p["label"]["y_zone"] != "high"]
    if vagal_fail:
        part = "sebagian: " if len(vagal_fail) < len(breath) else ""
        items.append(_item("relax_vagal_difficulty",
                           f"sulit rileks secara vagal ({part}saat napas dalam 6/menit vagal tidak naik seperti yang umumnya "
                           "terjadi: " + "; ".join(f"{_where(p)}: Y {_fz(yz(p))}, {p['label']['y_magnitude']}" for p in vagal_fail) + ").",
                           [p["id"] for p in vagal_fail]))

    load = [p for p in ok.values() if p["label"]["x_zone"] == "high"]
    if load:
        q4 = [p for p in load if p["label"]["code"] == "Q4"]
        text = ("Pola beban kortikal (berpikir berat): aktivasi kortikal naik dibanding baseline ("
                + "; ".join(f"{_where(p)}: X {_fz(xz(p))}" for p in load) + ")")
        if q4:
            text += ", disertai penarikan vagal di " + ", ".join(_where(p) for p in q4) + " (Q4, pola stres/beban mental)"
        if any(p["id"] != REST_OPEN for p in load):
            text += "; aktivasi tetap naik saat diminta rileks"
        items.append(_item("cortical_load", text + ".", [p["id"] for p in load]))

    tired = [p for p in ok.values() if p["label"]["code"] == "Q3" and (p["label"]["qualifier"] or "").startswith("lelah")]
    if tired:
        items.append(_item("fatigue", "Tanda kelelahan/mengantuk: korteks melambat dan vagal turun dengan θ/β naik ("
                           + "; ".join(f"{_where(p)}: X {_fz(xz(p))}, Y {_fz(yz(p))}, θ/β {_fz(p['medians']['theta_beta_z'])}"
                                       for p in tired) + ").", [p["id"] for p in tired]))

    rest = ok.get(REST_OPEN)
    if rest and rest["label"]["y_zone"] == "low":
        items.append(_item("vagal_withdrawal_rest",
                           f"tegang: vagal turun saat istirahat tanpa tugas ({_where(rest)}: Y {_fz(yz(rest))}, "
                           f"{rest['label']['y_magnitude']}).", [REST_OPEN]))

    if items:
        summary = "Relatif terhadap baseline sesi ini: " + "; ".join(
            i["title"].lower() + (" (diasumsikan)" if i["assumed"] else "") for i in items) + "."
    elif ok:
        summary = "Relatif terhadap baseline sesi ini tidak tampak pola khusus."
    else:
        summary = "Belum ada kesimpulan: tidak ada fase yang memenuhi syarat data."
    return {"items": items, "summary": summary, "note": NOTE, "missing": missing}


AXES = {"log_beta_alpha": ("kortikal", "log(β/α)"), "ln_rmssd": ("vagal", "lnRMSSD")}


def compare(pre: dict, post: dict) -> dict:
    """Change between a session before (pre) and after (post) an intervention (D-19).

    Compares the change from each session's own R0 in natural units (log ratios, comparable between days)
    and the R0 levels themselves, in units of the mean R0 window scale of the two sessions.
    """
    out = {"pre": pre["session_id"], "post": post["session_id"], "items": [], "table": [], "note":
           "Perbandingan antarsesi memakai perubahan dari R0 masing-masing dalam satuan asli; level R0 EEG antarhari "
           "dipengaruhi posisi headband, jadi dibaca hati-hati."}
    if not (pre["r0"]["adequate"] and post["r0"]["adequate"]):
        out["summary"] = "Belum bisa dibandingkan: R0 salah satu sesi tidak memenuhi syarat data."
        return out
    scale = {}
    for k in AXES:
        vals = [s["r0"]["raw_scale"][k] for s in (pre, post) if s["r0"]["raw_scale"].get(k)]
        scale[k] = sum(vals) / len(vals) if vals else None
    rel = lambda d, k: None if d is None or not scale[k] else d / scale[k]  # noqa: E731

    # table: change from R0 per phase, before and after
    pp, qp = ({p["id"]: p for p in s["phases"]} for s in (pre, post))
    for pid, p in pp.items():
        if p.get("reference"):
            continue
        q = qp.get(pid, {})
        row = {"id": pid, "name": p["name"]}
        for k in AXES:
            a, b = (p.get("delta") or {}).get(k), (q.get("delta") or {}).get(k)
            row[k] = {"pre": a, "post": b, "diff": _num(b - a) if a is not None and b is not None else None,
                      "diff_rel": _num(rel(b - a, k)) if a is not None and b is not None else None}
        row["pre_code"], row["post_code"] = p["label"]["code"], q.get("label", {}).get("code")
        out["table"].append(row)

    items = []
    # R0 level: vagal tone at rest, cortical activation at rest
    for k, word_up, word_down, extra in (
            ("ln_rmssd", "lebih tinggi", "lebih rendah", ["plews2012"]),
            ("log_beta_alpha", "lebih tinggi (lebih teraktivasi)", "lebih rendah (lebih tenang)", ["ehrhardt2022", "barry2007"])):
        a, b = pre["r0"]["raw"][k], post["r0"]["raw"][k]
        r = rel(b - a, k) if a is not None and b is not None else None
        if r is not None and abs(r) >= THRESHOLD_Z:
            axis, unit = AXES[k]
            text = (f"{'tonus vagal' if k == 'ln_rmssd' else 'aktivasi kortikal'} saat istirahat (R0) {word_up if r > 0 else word_down} "
                    f"sesudah: {unit} {_fn(a)} → {_fn(b)} ({_fz(r)} × skala R0)")
            if k == "ln_rmssd":
                text += f", RMSSD ≈ {math.exp(a):.0f} → {math.exp(b):.0f} ms"
            else:
                text += "; level EEG antarhari dipengaruhi posisi headband"
            what = "Tonus vagal istirahat" if k == "ln_rmssd" else "Aktivasi kortikal istirahat"
            items.append(_item("change_after", text + ".", ["baseline"], extra, title=what,
                               short=f"{what.lower()} {(word_up if r > 0 else word_down).split(' (')[0]}"))
    # change in the response of each phase, per axis (cortical down = slower, vagal up = higher)
    for row in out["table"]:
        shifts, refs = [], []
        x, y = row["log_beta_alpha"]["diff_rel"], row["ln_rmssd"]["diff_rel"]
        if x is not None and abs(x) >= THRESHOLD_Z:
            shifts.append(f"korteks {'lebih melambat' if x < 0 else 'lebih teraktivasi'} ({_fz(x)} × skala R0)")
            refs.append("barry2007" if x < 0 else "ehrhardt2022")
        if y is not None and abs(y) >= THRESHOLD_Z:
            shifts.append(f"vagal {'lebih tinggi' if y > 0 else 'lebih rendah'} ({_fz(y)} × skala R0)")
            refs.append("lehrer2014" if row["id"] in RELAX_BREATH else "laborde2017")
        if shifts:
            num = _phase_num(row["id"])
            items.append(_item("change_after", f"respons berbeda sesudah pada fase {num} {row['name'].lower()}: dibanding "
                               "perubahan dari R0 sebelumnya, " + " dan ".join(shifts) + ".", [row["id"]], refs,
                               title=f"Fase {num} · {row['name']}",
                               short=f"respons fase {num} berubah (" + ", ".join(x.split(" (")[0] for x in shifts) + ")"))
    # conclusions that appear or disappear
    before = {i["id"]: i for i in pre.get("conclusions", {}).get("items", [])}
    after = {i["id"]: i for i in post.get("conclusions", {}).get("items", [])}
    for cid in [c for c in CONCLUSIONS if c != "change_after"]:
        if (cid in before) != (cid in after):
            title = CONCLUSIONS[cid][0]
            when = "tampak sebelum, tidak tampak sesudah" if cid in before else "tidak tampak sebelum, tampak sesudah"
            items.append(_item("change_after", f"{title.lower()}: {when}.", (before.get(cid) or after[cid])["phases"],
                               EVIDENCE["concl_" + cid]["refs"], title=title,
                               short=f"{title.lower()} {'tidak lagi tampak' if cid in before else 'kini tampak'}"))
    out["items"] = items
    out["summary"] = ("Diasumsikan, dibanding sesi sebelum: " + "; ".join(i["short"] for i in items) + "."
                      if items else "Dibanding sesi sebelum tidak tampak perubahan yang melewati ambang.")
    return out


def conclusions_csv(result: dict, comparison: dict | None = None) -> str:
    """One row per conclusion of the session, then per change against the earlier session."""
    import csv
    import io

    f = io.StringIO()
    w = csv.writer(f)
    w.writerow(["scope", "session", "pre_session", "id", "title", "status", "narrative", "phases", "refs"])
    for i in result.get("conclusions", {}).get("items", []):
        w.writerow(["sesi", result["session_id"], "", i["id"], i["title"], i["status"], i["narrative"],
                    " ".join(i["phases"]), " ".join(i["refs"])])
    for i in (comparison or {}).get("items", []):
        w.writerow(["perbandingan", result["session_id"], comparison["pre"], i["id"], i["title"], i["status"],
                    i["narrative"], " ".join(i["phases"]), " ".join(i["refs"])])
    return f.getvalue()
