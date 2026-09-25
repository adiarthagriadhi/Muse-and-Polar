"""Writes every stream to its own CSV file inside a session folder."""

from __future__ import annotations

import csv
import json
import re
import time
from datetime import datetime
from pathlib import Path

from .streams import STREAMS


def _safe(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9_-]+", "_", name.strip())[:60].strip("_")


class Recorder:
    def __init__(self, base_dir: Path, name: str = "", note: str = "", devices: dict | None = None):
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        folder = f"{stamp}_{_safe(name)}" if _safe(name) else stamp
        self.dir = Path(base_dir) / folder
        self.dir.mkdir(parents=True, exist_ok=True)
        self.name = name
        self.note = note
        self.devices = devices or {}
        self.started = time.time()
        self.stopped: float | None = None
        self.files: dict[str, tuple] = {}
        self.counts: dict[str, int] = {}
        self._write_meta()

    def _writer(self, stream: str):
        if stream not in self.files:
            f = open(self.dir / f"{stream}.csv", "w", newline="", encoding="utf-8")
            w = csv.writer(f)
            w.writerow(["timestamp", *STREAMS[stream]["columns"]])
            self.files[stream] = (f, w)
            self.counts[stream] = 0
        return self.files[stream][1]

    def write(self, stream: str, ts: list[float], rows: list[list]) -> None:
        w = self._writer(stream)
        for t, row in zip(ts, rows):
            w.writerow([f"{t:.6f}", *(round(v, 6) if isinstance(v, float) else v for v in row)])
        self.counts[stream] += len(rows)

    def flush(self) -> None:
        for f, _ in self.files.values():
            f.flush()

    @property
    def elapsed(self) -> float:
        return (self.stopped or time.time()) - self.started

    def info(self) -> dict:
        return {
            "active": self.stopped is None,
            "name": self.name,
            "dir": str(self.dir),
            "elapsed": self.elapsed,
            "counts": dict(self.counts),
        }

    def _write_meta(self) -> None:
        meta = {
            "name": self.name,
            "note": self.note,
            "start_unix": self.started,
            "start_local": datetime.fromtimestamp(self.started).isoformat(timespec="seconds"),
            "end_unix": self.stopped,
            "duration_sec": self.elapsed if self.stopped else None,
            "devices": self.devices,
            "samples": self.counts,
            "effective_rate_hz": {
                s: round(n / self.elapsed, 2) for s, n in self.counts.items() if STREAMS[s]["rate"] and self.stopped
            },
            "streams": {s: STREAMS[s] for s in self.counts} if self.stopped else STREAMS,
            "timestamp": "Unix time in seconds (host clock), per sample",
        }
        (self.dir / "session.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")

    def close(self) -> None:
        if self.stopped is not None:
            return
        self.stopped = time.time()
        for f, _ in self.files.values():
            f.close()
        self._write_meta()
