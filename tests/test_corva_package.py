"""Standalone CorVa Space download: the app folders, the run scripts, and nothing private."""

import importlib.util
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("build_corva_package", ROOT / "tools" / "build_corva_package.py")
build_mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(build_mod)


def test_package_contents(tmp_path):
    target = build_mod.build(tmp_path)
    top = f"CorVa-Space-{build_mod.VERSION}/"
    with zipfile.ZipFile(target) as z:
        names = z.namelist()
        assert all(n.startswith(top) for n in names)
        rel = {n[len(top):] for n in names}
        for need in ("BACA-DULU.md", "corva_mac.command", "corva_demo.command", "corva_windows.bat", "corva_demo.bat",
                     "requirements.txt", "musepolar/server.py", "musepolar/static/corva.js", "cass_polar/engine.py",
                     "corva/session.py", "corva/validate.py", "corva/references.json"):
            assert need in rel, need
        assert not any(r.startswith(("research/", "tests/", "out/", ".github/", "packaging/")) or "dash_multi" in r
                       for r in rel)
        assert (z.getinfo(top + "corva_mac.command").external_attr >> 16) & 0o111
        assert b"\r\n" in z.read(top + "corva_windows.bat")
        mac = z.read(top + "corva_mac.command").decode()
        assert "--port 8775" in mac and "--data-dir corva_recordings" in mac  # separate from the old dashboard
