"""Bridge to CASS Wellness: convert a recording into its upload format and send it.

CASS Wellness (separate toolkit, run with ``./jalankan.sh --port 8766``) reads
a ZIP with EEG_raw.csv + PPG_raw.csv + recording_metadata.json, the layout used
by Mind Monitor / LSL exports. PPG_2 must be the infrared channel.
"""

from __future__ import annotations

import csv
import io
import json
import re
import zipfile
from datetime import datetime
from pathlib import Path

import aiohttp

EEG_COLUMNS = ["Timestamp_LSL", "EEG_TP9", "EEG_AF7", "EEG_AF8", "EEG_TP10"]
PPG_COLUMNS = ["Timestamp_LSL", "PPG_1", "PPG_2", "PPG_3"]  # ambient, IR, red


class CassError(Exception):
    pass


def _convert(src: Path, header: list[str]) -> str:
    """Copy a recorder CSV (timestamp + channels) under CASS column names."""
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(header)
    with open(src, newline="", encoding="utf-8") as f:
        r = csv.reader(f)
        next(r, None)
        for row in r:
            if len(row) >= len(header):
                w.writerow(row[: len(header)])
    return out.getvalue()


def participant_id(session: dict, folder: Path) -> str:
    name = re.sub(r"[^A-Za-z0-9_]+", "_", session.get("name") or "").strip("_")
    return name[:40] or folder.name


def export_session(folder: Path) -> Path:
    """Write <folder>/cass_<folder name>.zip and return its path."""
    folder = Path(folder)
    eeg = folder / "muse_eeg.csv"
    if not eeg.exists():
        raise CassError("rekaman ini tidak berisi EEG Muse (muse_eeg.csv)")
    ppg = folder / "muse_ppg.csv"
    if not ppg.exists():
        raise CassError("rekaman ini tidak berisi PPG Muse (muse_ppg.csv); CASS memakai PPG untuk sumbu Y")
    session = {}
    if (folder / "session.json").exists():
        session = json.loads((folder / "session.json").read_text(encoding="utf-8"))
    start = session.get("start_unix")
    meta = {
        "participant": participant_id(session, folder),
        "recording_type": "experiment",
        "start_iso": datetime.fromtimestamp(start).isoformat(timespec="seconds") if start else "unknown",
        "source": "musepolar",
        "note": session.get("note", ""),
        "musepolar_session": folder.name,
        "sync": session.get("sync", []),
    }
    path = folder / f"cass_{folder.name}.zip"
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("EEG_raw.csv", _convert(eeg, EEG_COLUMNS))
        z.writestr("PPG_raw.csv", _convert(ppg, PPG_COLUMNS))
        z.writestr("recording_metadata.json", json.dumps(meta, indent=2))
        # not used by CASS yet; kept so a Polar-based Y axis can be added later
        for extra in ("polar_rr.csv", "marker.csv"):
            if (folder / extra).exists():
                z.write(folder / extra, extra)
    return path


async def upload(zip_path: Path, base_url: str, ruas_s: float = 30, prv_s: float = 20, timeout: float = 300) -> dict:
    """POST the ZIP to CASS Wellness /api/upload; return its JSON with an absolute html_url."""
    base = base_url.rstrip("/")
    form = aiohttp.FormData()
    form.add_field("file", Path(zip_path).read_bytes(), filename=Path(zip_path).name, content_type="application/zip")
    form.add_field("marker", "")
    form.add_field("ruas", str(ruas_s))
    form.add_field("prv", str(prv_s))
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=timeout)) as s:
            async with s.post(f"{base}/api/upload", data=form) as resp:
                text = await resp.text()
                try:
                    res = json.loads(text)
                except ValueError:
                    raise CassError(f"CASS Wellness membalas HTTP {resp.status}: {text[:200]}") from None
                if resp.status >= 400 or res.get("error"):
                    raise CassError(str(res.get("error") or f"HTTP {resp.status}"))
    except aiohttp.ClientConnectorError:
        raise CassError(f"CASS Wellness tidak berjalan di {base}. Jalankan: ./jalankan.sh --port 8766") from None
    if res.get("html_url", "").startswith("/"):
        res["html_url"] = base + res["html_url"]
    return res


async def is_running(base_url: str) -> bool:
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=2)) as s:
            async with s.get(base_url.rstrip("/") + "/api/list") as resp:
                return resp.status == 200
    except (aiohttp.ClientError, OSError, TimeoutError):
        return False
