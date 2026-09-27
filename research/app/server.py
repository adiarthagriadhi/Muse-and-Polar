"""Muse 2 Research View: local web app for analysing musepolar recordings.

Reads musepolar session folders and EDF/EDF+/BDF files (any 10-20 / 10-10 montage).

Run from the research/ folder:

    PYTHONPATH=src python app/server.py            # opens http://127.0.0.1:8600
    PYTHONPATH=src python app/server.py --root /path/to/recordings --port 8600 --no-browser
"""

from __future__ import annotations

import argparse
import hashlib
import sys
import tempfile
import threading
import webbrowser
from collections import OrderedDict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from fastapi import FastAPI, File, HTTPException, Query, UploadFile  # noqa: E402
from fastapi.responses import FileResponse, JSONResponse, Response  # noqa: E402
from fastapi.staticfiles import StaticFiles  # noqa: E402

from muse2_pipeline.analysis import Session  # noqa: E402
from muse2_pipeline.io import DEFAULT_RECORDINGS, EDF_SUFFIXES, list_recordings, unpack_zip  # noqa: E402
from muse2_pipeline import report  # noqa: E402

STATIC = Path(__file__).with_name("static")

app = FastAPI(title="Muse 2 Research View")
app.mount("/static", StaticFiles(directory=STATIC), name="static")

STATE = {"default_root": DEFAULT_RECORDINGS}
FOLDERS: dict[str, Path] = {}  # session id -> folder
ROOTS: set[Path] = set()  # folders scanned so far (rescanned when an unknown id is requested)
CACHE: OrderedDict[str, tuple[float, Session]] = OrderedDict()
CACHE_SIZE = 4
LOCK = threading.Lock()


def _sid(folder: Path) -> str:
    return hashlib.sha1(str(Path(folder).resolve()).encode()).hexdigest()[:12]


def _scan(root: Path) -> list[dict]:
    ROOTS.add(Path(root))
    out = []
    for r in list_recordings(root):
        sid = _sid(r["path"])
        FOLDERS[sid] = Path(r["path"])
        out.append({
            "id": sid, "label": r["label"], "name": r["name"], "note": r["note"], "start": r["start"],
            "duration": r["duration"], "has_ppg": r["has_ppg"], "has_polar": r["has_heart"],
            "kind": r["kind"], "n_channels": r["n_channels"],
        })
    out.sort(key=lambda s: (s["start"] or "", s["label"]), reverse=True)  # newest first
    return out


def session(sid: str) -> Session:
    folder = FOLDERS.get(sid)
    if folder is None:  # e.g. server restarted while the page stayed open
        for root in {STATE["default_root"], *ROOTS}:
            if Path(root).exists():
                _scan(root)
        folder = FOLDERS.get(sid)
    data_file = folder / "muse_eeg.csv" if folder is not None and folder.is_dir() else folder
    if data_file is None or not data_file.exists():
        raise HTTPException(404, "Sesi tidak ditemukan. Muat ulang daftar sesi.")
    mtime = data_file.stat().st_mtime
    with LOCK:
        hit = CACHE.get(sid)
        if hit and hit[0] == mtime:
            CACHE.move_to_end(sid)
            return hit[1]
    try:
        sess = Session(folder)
    except Exception as e:  # malformed or empty CSV
        raise HTTPException(422, f"Sesi tidak bisa dibaca: {e}") from e
    with LOCK:
        CACHE[sid] = (mtime, sess)
        while len(CACHE) > CACHE_SIZE:
            CACHE.popitem(last=False)
    return sess


def _settings(titik: str, band: str, metric: str, ref: int, art: float) -> dict:
    return {"titik": titik, "band": band, "metric": metric, "ref": ref, "art_uv": art}


@app.get("/")
def index():
    return FileResponse(STATIC / "index.html", headers={"Cache-Control": "no-store"})


@app.get("/api/sessions")
def sessions(root: str = ""):
    path = Path(root).expanduser() if root.strip() else STATE["default_root"]
    if not path.exists():
        return {"root": str(path), "exists": False, "sessions": [], "default_root": str(STATE["default_root"])}
    return {"root": str(path), "exists": True, "sessions": _scan(path), "default_root": str(STATE["default_root"])}


@app.post("/api/upload")
async def upload(file: UploadFile = File(...)):
    data = await file.read()
    name = Path(file.filename or "rekaman").name
    if name.lower().endswith(EDF_SUFFIXES):  # a single EDF/BDF file
        root = Path(tempfile.mkdtemp(prefix="muse2_edf_"))
        (root / name).write_bytes(data)
    else:
        try:
            root = unpack_zip(data)
        except Exception as e:
            raise HTTPException(400, f"File tidak bisa dibuka (ZIP atau EDF/BDF): {e}") from e
    found = _scan(root)
    if not found:
        raise HTTPException(400, "Tidak ada rekaman (folder musepolar atau file EDF/BDF) di dalam file ini.")
    return {"root": str(root), "exists": True, "sessions": found, "uploaded": True}


@app.get("/api/session/{sid}")
def overview(sid: str):
    return JSONResponse(session(sid).overview())


@app.get("/api/signal/{sid}")
def signal(sid: str, t0: float = 0.0, t1: float = 1e9, n: int = 1600):
    return JSONResponse(session(sid).signal(t0, t1, n))


@app.get("/api/analysis/{sid}")
def analysis(sid: str, titik: str = "", band: str = "alpha", metric: str = "abs",
             ref: int = 0, art: float = Query(100.0, ge=10, le=2000)):
    return JSONResponse(session(sid).analyze(titik, band, metric, ref, art))


def _download(data: bytes, name: str, mime: str) -> Response:
    return Response(data, media_type=mime, headers={"Content-Disposition": f'attachment; filename="{name}"'})


@app.get("/api/export/{sid}")
def export(sid: str, titik: str = "", band: str = "alpha", metric: str = "abs", ref: int = 0, art: float = 100.0):
    s = session(sid)
    res = s.analyze(titik, band, metric, ref, art)
    data = report.export_zip(s, res, _settings(titik, band, metric, ref, art))
    return _download(data, f"{s.folder.name}_{band}_analisis.zip", "application/zip")


@app.get("/api/report/{sid}")
def word(sid: str, titik: str = "", band: str = "alpha", metric: str = "abs", ref: int = 0, art: float = 100.0,
         scale: str = "map"):
    s = session(sid)
    res = s.analyze(titik, band, metric, ref, art)
    return _download(report.report_docx(s, res, scale), f"{s.folder.name}_{band}_laporan.docx",
                     "application/vnd.openxmlformats-officedocument.wordprocessingml.document")


@app.get("/api/figure/{sid}")
def figure(sid: str, titik: str = "", band: str = "alpha", metric: str = "abs", ref: int = 0, art: float = 100.0,
           scale: str = "map"):
    s = session(sid)
    res = s.analyze(titik, band, metric, ref, art)
    return _download(report.figure_png(s, res, scale), f"{s.folder.name}_{band}.png", "image/png")


def main(argv=None):
    ap = argparse.ArgumentParser(description="Muse 2 Research View")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8600)
    ap.add_argument("--root", help=f"folder rekaman (default {DEFAULT_RECORDINGS})")
    ap.add_argument("--no-browser", action="store_true")
    args = ap.parse_args(argv)
    if args.root:
        STATE["default_root"] = Path(args.root).expanduser()
    url = f"http://{'127.0.0.1' if args.host in ('0.0.0.0', '::') else args.host}:{args.port}/"
    print(f"Muse 2 Research View: {url}  (folder rekaman: {STATE['default_root']})")
    if not args.no_browser:
        threading.Timer(1.2, lambda: webbrowser.open(url)).start()
    import uvicorn

    uvicorn.run(app, host=args.host, port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
