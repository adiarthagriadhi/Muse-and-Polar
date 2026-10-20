"""Safe export and cumulative session registry for the experimental CASS–Polar workflow."""
from __future__ import annotations
import asyncio
import io
import json
import re
import zipfile
from html import escape as html_escape
from pathlib import Path
from aiohttp import web

# muse_ppg.csv is kept for reference (PRV); the CASS Y axis uses Polar RR only
FILES = ("muse_eeg.csv", "muse_ppg.csv", "polar_rr.csv", "polar_ecg.csv", "marker.csv", "session.json")
def sessions(root: Path):
    root = root.resolve()
    result = []
    if not root.is_dir():
        return result
    for d in sorted(root.iterdir(), reverse=True):
        if not d.is_dir() or d.is_symlink():
            continue
        eeg, rr = d/"muse_eeg.csv", d/"polar_rr.csv"
        if not (eeg.is_file() and rr.is_file()):
            continue
        meta = {}
        try:
            if (d/"session.json").is_file():
                meta = json.loads((d/"session.json").read_text())
        except (ValueError, OSError):
            pass
        result.append({"id":d.name,"name":d.name,"has_eeg":True,"has_polar_rr":True,
                       "has_cass_state":bool(list(d.glob("cass_state_*_polar.csv"))),
                       "meta":{k:meta[k] for k in ("name","note") if k in meta}})
    return result

def resolve_session(root, name):
    if not isinstance(name,str) or not re.fullmatch(r"[\w.\-]+",name) or name in (".",".."):
        raise web.HTTPBadRequest(text="Invalid session ID")
    root=root.resolve()
    folder=(root/name).resolve()
    if folder.parent != root or not folder.is_dir():
        raise web.HTTPNotFound(text="Session not found")
    return folder

def export_zip(folder: Path) -> bytes:
    if not (folder/"muse_eeg.csv").is_file() or not (folder/"polar_rr.csv").is_file():
        raise web.HTTPConflict(text="EEG Muse dan RR Polar wajib tersedia")
    out=io.BytesIO()
    with zipfile.ZipFile(out,"w",zipfile.ZIP_DEFLATED) as z:
        for filename in FILES:
            file=folder/filename
            if file.is_file() and not file.is_symlink():
                z.write(file,filename)
        z.writestr("cass_polar_export.json",json.dumps({
            "format":"CASS_POLAR_INPUT_0.1",
            "session_id":folder.name,
            "cortical_source":"Muse 2 EEG",
            "autonomic_source":"Polar H10 ECG-derived RR",
            "ppg":"muse_ppg.csv stored for reference only; not used for the autonomic axis",
            "analysis_status":"raw_input_only; CASS state not yet calculated",
            "timestamp":"Unix seconds, shared host clock",
        },indent=2))
    return out.getvalue()

def add_routes(app, data_dir):
    root=Path(data_dir)
    async def listing(_request):
        return web.json_response({"sessions":sessions(root)})
    async def export(request):
        folder=resolve_session(root,request.match_info["session"])
        body=export_zip(folder)
        return web.Response(body=body,content_type="application/zip",
                            headers={"Content-Disposition":f'attachment; filename="{folder.name}_CASS_Polar.zip"'})
    async def export_save(request):
        folder=resolve_session(root,request.match_info["session"])
        try:
            body=await asyncio.to_thread(export_zip,folder)
        except web.HTTPConflict as exc:
            return web.json_response({"error":exc.text},status=409)
        path=folder/f"{folder.name}_CASS_Polar.zip"
        await asyncio.to_thread(path.write_bytes,body)
        return web.json_response({"zip":str(path)})
    async def analysis(request):
        folder = resolve_session(root, request.match_info["session"])
        try:
            r0_end = float(request.query.get("r0", "60"))
            if not (10 <= r0_end <= 86400):
                raise ValueError("Akhir baseline R0 harus antara 10 dan 86400 detik.")
            from .engine import analyze
            payload = await asyncio.to_thread(analyze, folder, r0_end)
            return web.json_response(payload, headers={"Cache-Control": "no-store"})
        except (ValueError, OSError) as exc:
            return web.json_response({"error": str(exc)}, status=422)
        except Exception:
            import logging
            logging.getLogger(__name__).exception("CASS analysis failed")
            return web.json_response({"error": "Kesalahan pemrosesan CASS; periksa log Terminal."}, status=500)

    async def session_view(request):
        """Wellness Explorer with a participant selector: the chosen session first, then all others."""
        folder = resolve_session(root, request.match_info["session"])
        from .explorer import build_html, cached_payload

        def build():
            first = cached_payload(folder)  # errors for the chosen session are shown
            payloads, labels = [first], {first["session_id"]}
            for s in sessions(root):
                other = root.resolve() / s["id"]
                if other == folder.resolve():
                    continue
                try:
                    p = cached_payload(other)
                except ValueError:
                    continue  # unusable recording: leave it out of the selector
                if p["session_id"] in labels:
                    p = {**p, "session_id": f'{p["session_id"]} ({s["id"]})'}
                labels.add(p["session_id"])
                payloads.append(p)
            return build_html(payloads if len(payloads) > 1 else first)

        try:
            html = await asyncio.to_thread(build)
        except ValueError as exc:
            return web.Response(text=ERROR_PAGE.replace("{msg}", html_escape(str(exc))), content_type="text/html",
                                charset="utf-8", status=422)
        return web.Response(text=html, content_type="text/html", charset="utf-8",
                            headers={"Cache-Control": "no-store"})

    async def explorer(request):
        # like the toolkit: open the Wellness Explorer (newest session first, others in the selector)
        rows=sessions(root)
        if rows and "daftar" not in request.query:
            raise web.HTTPFound(f"/cass/session/{rows[0]['id']}")
        return web.Response(text=EXPLORER,content_type="text/html",charset="utf-8")
    app.router.add_get("/api/cass/sessions",listing)
    app.router.add_get("/api/cass/export/{session}",export)
    app.router.add_post("/api/cass/export/{session}",export_save)
    app.router.add_get("/api/cass/analysis/{session}",analysis)
    app.router.add_get("/cass/session/{session}",session_view)
    app.router.add_get("/cass",explorer)

EXPLORER = """<!doctype html><html lang="id"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>CASS–Polar | Sesi penelitian</title><style>
body{font:15px system-ui;background:#f4f6fa;color:#172338;margin:0}header{background:#162c4b;color:white;padding:24px max(20px,5vw)}main{max-width:1050px;margin:30px auto;padding:0 20px}.card{background:white;padding:20px;margin:12px 0;border-radius:12px;box-shadow:0 2px 10px #18294318}a{color:#1665bc}header a{color:#fff}table{width:100%;border-collapse:collapse}td,th{text-align:left;padding:12px;border-bottom:1px solid #ddd}small{color:#607080}.notice{border-left:4px solid #ce8c22;padding:12px;background:#fff6e6}
</style></head><body><header><a href="/">← Muse–Polar Live</a><h1>CASS–Polar · Sesi Penelitian</h1><p>Daftar kumulatif sesi yang memiliki EEG Muse dan RR Polar H10</p></header><main><div class="notice">Tampilan ini adalah indeks kumulatif rekaman. Gunakan <b>Lihat CASS</b> untuk visualisasi per sesi. Perhitungan CASS lintas-sesi memerlukan baseline R0, segmentasi dan pemrosesan yang tervalidasi per sesi; hasil tidak boleh digabung tanpa normalisasi yang sesuai.</div><div class="card"><h2>Rekaman yang tersedia</h2><div id="result">Memuat…</div></div></main><script>
fetch('/api/cass/sessions').then(r=>{if(!r.ok)throw Error('HTTP '+r.status);return r.json()}).then(data=>{
let rows=data.sessions.map(s=>{let id=encodeURIComponent(s.id);let td=document.createElement('tr');let n=document.createElement('td');n.textContent=s.name;let state=document.createElement('td');state.textContent=s.has_cass_state?'CSV CASS–Polar tersedia':'Siap dianalisis dari rekaman';let view=document.createElement('td');let v=document.createElement('a');v.href='/cass/session/'+id;v.textContent='Lihat CASS';v.style.fontWeight='700';view.append(v);let dl=document.createElement('td');let a=document.createElement('a');a.href='/api/cass/export/'+id;a.textContent='Ekspor ZIP';dl.append(a);td.append(n,state,view,dl);return td});
let box=document.getElementById('result');box.textContent='';if(!rows.length){box.textContent='Belum ada rekaman Muse EEG + Polar RR.';return}let table=document.createElement('table');table.innerHTML='<thead><tr><th>Sesi</th><th>Status analisis</th><th>CASS</th><th>Ekspor</th></tr></thead>';let body=document.createElement('tbody');rows.forEach(r=>body.append(r));table.append(body);box.append(table);
}).catch(e=>document.getElementById('result').textContent='Gagal memuat: '+e.message);
</script></body></html>"""

ERROR_PAGE = """<!doctype html><html lang="id"><head><meta charset="utf-8"><title>CASS Wellness Explorer</title>
<style>body{font:15px system-ui;margin:40px;color:#0b0b0b;background:#f9f9f7}p{max-width:640px}</style></head>
<body><h1>CASS belum bisa ditampilkan</h1><p>{msg}</p><p><a href="/">← Muse–Polar Live</a></p></body></html>"""
