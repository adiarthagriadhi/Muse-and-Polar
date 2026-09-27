#!/bin/bash
set -e
PROJ="$(cd "$(dirname "$0")" && pwd)"
APP="$HOME/Desktop/Muse2 Research.app"
SCRIPT="/tmp/muse2_research_launcher.applescript"

cat > "$SCRIPT" <<EOF
set proj to "$PROJ"
do shell script "source " & quoted form of "$HOME/muse2-env/bin/activate" & " && cd " & quoted form of proj & " && PYTHONPATH=src /usr/bin/env streamlit run app/streamlit_app.py --server.headless true >/tmp/muse2-streamlit.log 2>&1 &"
delay 2.5
open location "http://localhost:8501"
EOF

osacompile -o "$APP" "$SCRIPT"
echo "Aplikasi terpasang di: $APP"
echo "Klik dua kali ikon di Desktop. Jangan hapus folder:"
echo "  $PROJ"
open "$HOME/Desktop"
EOF
