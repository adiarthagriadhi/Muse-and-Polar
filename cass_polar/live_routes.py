"""Safe export and cumulative session registry for the experimental CASS–Polar workflow."""
from __future__ import annotations
import csv
import io
import json
import re
import zipfile
from pathlib import Path
from aiohttp import web

FILES = ("muse_eeg.csv", "polar_rr.csv", "polar_ecg.csv", "marker.csv", "session.json")
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

def add_routes(app, data_dir):
    root=Path(data_dir)
    async def listing(_request):
        return web.json_response({"sessions":sessions(root)})
    async def export(request):
        folder=resolve_session(root,request.match_info["session"])
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
                "analysis_status":"raw_input_only; CASS state not yet calculated",
                "timestamp":"Unix seconds, shared host clock",
            },indent=2))
        return web.Response(body=out.getvalue(),content_type="application/zip",
                            headers={"Content-Disposition":f'attachment; filename="{folder.name}_CASS_Polar.zip"'})
    async def explorer(_request):
        return web.Response(text=EXPLORER,content_type="text/html",charset="utf-8")
    app.router.add_get("/api/cass/sessions",listing)
    app.router.add_get("/api/cass/export/{session}",export)
    app.router.add_get("/cass",explorer)

EXPLORER = """<!doctype html><html lang="id"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>CASS–Polar | Sesi penelitian</title><style>
body{font:15px system-ui;background:#f4f6fa;color:#172338;margin:0}header{background:#162c4b;color:white;padding:24px max(20px,5vw)}main{max-width:1050px;margin:30px auto;padding:0 20px}.card{background:white;padding:20px;margin:12px 0;border-radius:12px;box-shadow:0 2px 10px #18294318}a{color:#1665bc}header a{color:#fff}table{width:100%;border-collapse:collapse}td,th{text-align:left;padding:12px;border-bottom:1px solid #ddd}small{color:#607080}.notice{border-left:4px solid #ce8c22;padding:12px;background:#fff6e6}
</style></head><body><header><a href="/">← Muse–Polar Live</a><h1>CASS–Polar · Sesi Penelitian</h1><p>Daftar kumulatif sesi yang memiliki EEG Muse dan RR Polar H10</p></header><main><div class="notice">Tampilan ini adalah indeks kumulatif rekaman, <b>bukan</b> peta state CASS gabungan. Perhitungan CASS lintas-sesi memerlukan baseline R0, segmentasi dan pemrosesan yang tervalidasi per sesi; hasil tidak boleh digabung tanpa normalisasi yang sesuai.</div><div class="card"><h2>Rekaman yang tersedia</h2><div id="result">Memuat…</div></div></main><script>
fetch('/api/cass/sessions').then(r=>{if(!r.ok)throw Error('HTTP '+r.status);return r.json()}).then(data=>{
let rows=data.sessions.map(s=>{let id=encodeURIComponent(s.id);let td=document.createElement('tr');let n=document.createElement('td');n.textContent=s.name;let state=document.createElement('td');state.textContent=s.has_cass_state?'CSV CASS–Polar tersedia':'Belum dianalisis';let dl=document.createElement('td');let a=document.createElement('a');a.href='/api/cass/export/'+id;a.textContent='Ekspor ZIP';dl.append(a);td.append(n,state,dl);return td});
let box=document.getElementById('result');box.textContent='';if(!rows.length){box.textContent='Belum ada rekaman Muse EEG + Polar RR.';return}let table=document.createElement('table');table.innerHTML='<thead><tr><th>Sesi</th><th>Status analisis</th><th>Ekspor</th></tr></thead>';let body=document.createElement('tbody');rows.forEach(r=>body.append(r));table.append(body);box.append(table);
}).catch(e=>document.getElementById('result').textContent='Gagal memuat: '+e.message);
</script></body></html>"""
