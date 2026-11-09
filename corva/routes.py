"""CorVa Space routes for the live dashboard (v0.3).

GET /corva                              → newest session recorded with the CorVa protocol (or a notice)
GET /corva/session/{session}            → CorVa Space page: 3 × 3 map, phase cards, timelines
GET /api/corva/sessions                 → sessions that carry CorVa protocol markers
GET /api/corva/analysis/{session}       → corva.session.analyze_session() as JSON
GET /api/corva/export/{session}?level=phases|windows|conclusions[&pre=<id>] → CSV
GET /api/corva/compare?pre=<id>&post=<id>  → change between a session before and after (D-19)
GET /corva/session/{session}?pre=<id>      → the page with the comparison against an earlier session
"""

from __future__ import annotations

import asyncio
import logging
from html import escape as html_escape
from pathlib import Path

from aiohttp import web

from cass_polar.live_routes import resolve_session, sessions

from . import protocol
from .conclusions import compare, conclusions_csv
from .session import analyze_session, phases_csv, windows_csv
from .view import build_html

log = logging.getLogger(__name__)

_CACHE: dict = {}


def has_protocol_markers(folder: Path) -> bool:
    try:
        text = (folder / "marker.csv").read_text(encoding="utf-8", errors="replace")
    except OSError:
        return False
    return protocol.MARKER_PREFIX in text


def corva_sessions(root: Path) -> list[dict]:
    """Recorded sessions (EEG + RR) that contain CorVa protocol markers, newest first."""
    out = []
    for s in sessions(root):
        if has_protocol_markers(root.resolve() / s["id"]):
            out.append({"id": s["id"], "name": s["meta"].get("name") or s["id"]})
    return out


def cached_analysis(folder: Path) -> dict:
    """analyze_session() memoised on the session's input files."""
    folder = Path(folder)
    key = tuple((f.name, f.stat().st_mtime_ns, f.stat().st_size)
                for f in (folder / n for n in ("muse_eeg.csv", "polar_rr.csv", "marker.csv")) if f.exists())
    hit = _CACHE.get(folder)
    if hit and hit[0] == key:
        return hit[1]
    result = analyze_session(folder)
    _CACHE[folder] = (key, result)
    return result


ERROR_PAGE = """<!doctype html><html lang="id"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>CorVa Space</title>
<style>body{font:15px system-ui;margin:40px 16px;color:#0b0b0b;background:#f4f4f1}p{max-width:640px}
@media (prefers-color-scheme:dark){body{color:#fff;background:#111110}a{color:#8fb8f0}}</style></head>
<body><h1>CorVa Space belum bisa ditampilkan</h1><p>{msg}</p>{list}<p><a href="/">← Muse–Polar Live</a></p></body></html>"""


def _error_page(msg: str, root: Path, status: int) -> web.Response:
    rows = corva_sessions(root)
    links = "".join(f'<li><a href="/corva/session/{html_escape(r["id"])}">{html_escape(r["name"])}</a></li>' for r in rows)
    lst = f"<p>Sesi dengan protokol CorVa:</p><ul>{links}</ul>" if rows else ""
    html = ERROR_PAGE.replace("{msg}", html_escape(msg)).replace("{list}", lst)
    return web.Response(text=html, content_type="text/html", charset="utf-8", status=status)


def add_routes(app: web.Application, data_dir) -> None:
    root = Path(data_dir)

    async def analysis_json(request):
        folder = resolve_session(root, request.match_info["session"])
        try:
            result = await asyncio.to_thread(cached_analysis, folder)
        except (ValueError, OSError) as exc:
            return web.json_response({"error": str(exc)}, status=422)
        return web.json_response(result, headers={"Cache-Control": "no-store"})

    async def export_csv(request):
        folder = resolve_session(root, request.match_info["session"])
        level = request.query.get("level", "phases")
        if level not in ("phases", "windows", "conclusions"):
            raise web.HTTPBadRequest(text="level harus phases, windows atau conclusions")
        try:
            result = await asyncio.to_thread(cached_analysis, folder)
            comparison = await asyncio.to_thread(_comparison, request.query.get("pre"), folder, result)
        except (ValueError, OSError) as exc:
            return web.json_response({"error": str(exc)}, status=422)
        if level == "conclusions":
            body = conclusions_csv(result, comparison if comparison and "error" not in comparison else None)
        else:
            body = phases_csv(result) if level == "phases" else windows_csv(result)
        name = f"{folder.name}_CorVa_{ {'phases': 'fase', 'windows': 'jendela', 'conclusions': 'kesimpulan'}[level] }.csv"
        return web.Response(text=body, content_type="text/csv", charset="utf-8",
                            headers={"Content-Disposition": f'attachment; filename="{name}"'})

    def _comparison(pre_id, folder, result):
        """compare(pre, result) for ?pre=<id>; an error dict when the earlier session cannot be analysed."""
        if not pre_id or pre_id == folder.name:
            return None
        try:
            pre_folder = resolve_session(root, pre_id)
            return compare(cached_analysis(pre_folder), result)
        except web.HTTPException:
            return {"pre": pre_id, "error": "Sesi sebelum tidak ditemukan."}
        except (ValueError, OSError) as exc:
            return {"pre": pre_id, "error": f"Sesi sebelum belum bisa dianalisis: {exc}"}

    async def compare_json(request):
        post = resolve_session(root, request.query.get("post", ""))
        pre = resolve_session(root, request.query.get("pre", ""))
        try:
            a = await asyncio.to_thread(cached_analysis, pre)
            b = await asyncio.to_thread(cached_analysis, post)
        except (ValueError, OSError) as exc:
            return web.json_response({"error": str(exc)}, status=422)
        return web.json_response(compare(a, b), headers={"Cache-Control": "no-store"})

    async def listing(_request):
        rows = await asyncio.to_thread(corva_sessions, root)
        return web.json_response({"sessions": rows})

    async def page(request):
        folder = resolve_session(root, request.match_info["session"])
        try:
            result = await asyncio.to_thread(cached_analysis, folder)
            others = await asyncio.to_thread(corva_sessions, root)
            comparison = await asyncio.to_thread(_comparison, request.query.get("pre"), folder, result)
        except (ValueError, OSError) as exc:
            return await asyncio.to_thread(_error_page, str(exc), root, 422)
        except Exception:  # noqa: BLE001
            log.exception("CorVa analysis failed")
            return await asyncio.to_thread(_error_page, "Kesalahan pemrosesan CorVa; periksa log Terminal.", root, 500)
        if not any(o["id"] == folder.name for o in others):
            others = [{"id": folder.name, "name": folder.name}, *others]
        html = build_html(result, others, current=folder.name, comparison=comparison)
        return web.Response(text=html, content_type="text/html", charset="utf-8",
                            headers={"Cache-Control": "no-store"})

    async def index(_request):
        rows = await asyncio.to_thread(corva_sessions, root)
        if rows:
            raise web.HTTPFound(f"/corva/session/{rows[0]['id']}")
        return await asyncio.to_thread(
            _error_page, "Belum ada rekaman dengan protokol CorVa. Jalankan Mulai protokol standar di dashboard.",
            root, 404)

    app.router.add_get("/api/corva/sessions", listing)
    app.router.add_get("/api/corva/analysis/{session}", analysis_json)
    app.router.add_get("/api/corva/export/{session}", export_csv)
    app.router.add_get("/api/corva/compare", compare_json)
    app.router.add_get("/corva/session/{session}", page)
    app.router.add_get("/corva", index)
