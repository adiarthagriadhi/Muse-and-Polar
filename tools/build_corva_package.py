"""Build the standalone CorVa Space download (zip), separate from the Muse-Polar dashboard install.

    python tools/build_corva_package.py            # → dist/CorVa-Space-<version>.zip

Only files tracked by git are packed (so recordings or local output can never slip in), from the folders the
app needs, plus the run scripts and guide in packaging/corva/. The run scripts use port 8775 and
corva_recordings/, so the package runs next to an existing dashboard install.
"""

from __future__ import annotations

import argparse
import subprocess
import time
import zipfile
from pathlib import Path

VERSION = "0.5.0"
ROOT = Path(__file__).resolve().parents[1]
INCLUDE_DIRS = ("musepolar/", "cass_polar/", "corva/")
INCLUDE_FILES = ("requirements.txt", "requirements-lock.txt", "LICENSE", "CITATION.cff",
                 "docs/panduan-dashboard-id.md", "docs/THIRD-PARTY.md")
EXTRA = Path("packaging/corva")  # copied to the package root
EXECUTABLE = (".command",)
NEVER = ("out/", "dash_multi.html", "recordings/", "demo_recordings/", "corva_recordings/", "corva_demo/")


def tracked_files() -> list[str]:
    out = subprocess.run(["git", "ls-files"], cwd=ROOT, check=True, capture_output=True, text=True).stdout
    return out.splitlines()


def package_members() -> list[tuple[str, str]]:
    """(source path relative to the repo, path inside the package)."""
    members = []
    for f in tracked_files():
        if any(part in f for part in NEVER) or "__pycache__" in f:
            continue
        if f.startswith(INCLUDE_DIRS) or f in INCLUDE_FILES:
            members.append((f, f))
        elif f.startswith(str(EXTRA) + "/"):
            members.append((f, f[len(str(EXTRA)) + 1:]))
    return sorted(members, key=lambda m: m[1])


def build(out_dir: Path) -> Path:
    name = f"CorVa-Space-{VERSION}"
    out_dir.mkdir(parents=True, exist_ok=True)
    target = out_dir / f"{name}.zip"
    stamp = time.localtime()[:6]
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as z:
        for src, dst in package_members():
            info = zipfile.ZipInfo(f"{name}/{dst}", date_time=stamp)
            info.compress_type = zipfile.ZIP_DEFLATED
            mode = 0o755 if dst.endswith(EXECUTABLE) else 0o644
            info.external_attr = (0o100000 | mode) << 16
            z.writestr(info, (ROOT / src).read_bytes())
    return target


def main() -> None:
    ap = argparse.ArgumentParser(description="Build the CorVa Space zip")
    ap.add_argument("--out", type=Path, default=ROOT / "dist")
    target = build(ap.parse_args().out)
    with zipfile.ZipFile(target) as z:
        n = len(z.namelist())
    print(f"{target} ({n} berkas, {target.stat().st_size / 1e6:.1f} MB)")


if __name__ == "__main__":
    main()
