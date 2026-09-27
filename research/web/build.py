"""Build the single-file browser version of Research View.

    python research/web/build.py        ->  research/web/research-view.html

The page reuses app/static (index.html, style.css, charts.js, app.js) and adds engine.js,
which does all the analysis in the browser, so no Python server is needed. JSZip (from
cdnjs) is only used for opening ZIP files and for the CSV export.
"""

from __future__ import annotations

import re
from pathlib import Path

HERE = Path(__file__).resolve().parent
STATIC = HERE.parent / "app" / "static"
OUT = HERE / "research-view.html"
JSZIP = "https://cdnjs.cloudflare.com/ajax/libs/jszip/3.10.1/jszip.min.js"


def build(artifact: Path | None = None) -> Path:
    """Write research-view.html; with ``artifact`` also write the claude.ai page variant there
    (no document skeleton, RV_ARTIFACT flag: copy-to-clipboard instead of downloads/print)."""
    html = (STATIC / "index.html").read_text(encoding="utf-8")
    css = (STATIC / "style.css").read_text(encoding="utf-8")
    charts = (STATIC / "charts.js").read_text(encoding="utf-8")
    app = (STATIC / "app.js").read_text(encoding="utf-8")
    engine = (HERE / "engine.js").read_text(encoding="utf-8")

    charts = re.sub(r"^export\s+", "", charts, flags=re.M)  # one module scope: no import/export
    app = re.sub(r"^import\s.*?;\s*$", "", app, flags=re.M)
    for name, src in (("engine.js", engine), ("charts.js", charts), ("app.js", app)):
        assert "</script" not in src, f"{name} contains </script>"

    html = html.replace('<link rel="stylesheet" href="/static/style.css">', f"<style>\n{css}\n</style>")
    html = html.replace(
        '<script type="module" src="/static/app.js"></script>',
        f'<script src="{JSZIP}"></script>\n<script>\n{engine}\n</script>\n'
        f'<script type="module">\n{charts}\n{app}\n</script>',
    )
    assert "/static/" not in html, "unresolved /static/ reference"
    OUT.write_text(html, encoding="utf-8")
    if artifact:
        head = re.search(r"<head>(.*?)</head>", html, flags=re.S).group(1)
        body = re.search(r"<body>(.*?)</body>", html, flags=re.S).group(1)
        head = re.sub(r"<meta[^>]*>\s*", "", head)  # charset/viewport come from the host skeleton
        title = re.search(r"<title>.*?</title>", head).group(0)
        head = head.replace(title, "")
        artifact.write_text(f"{title}\n{head.strip()}\n<script>window.RV_ARTIFACT = true;</script>\n{body.strip()}\n",
                            encoding="utf-8")
    return OUT


if __name__ == "__main__":
    import sys

    art = Path(sys.argv[sys.argv.index("--artifact") + 1]) if "--artifact" in sys.argv else None
    out = build(art)
    print(f"{out} ({out.stat().st_size // 1024} KB)" + (f"; artifact page: {art}" if art else ""))
