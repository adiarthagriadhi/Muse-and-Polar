#!/bin/bash
# Membuat ikon "Muse2 Research.app" di Desktop yang menjalankan run_mac.command di latar belakang.
set -e
PROJ="$(cd "$(dirname "$0")" && pwd)"
APP="$HOME/Desktop/Muse2 Research.app"
SCRIPT="$(mktemp -t muse2_research_launcher).applescript"

if [ ! -d "$PROJ/.venv" ]; then
  echo "Memasang dependensi pertama kali ..."
  python3 -m venv "$PROJ/.venv"
  "$PROJ/.venv/bin/pip" install --upgrade pip >/dev/null
  "$PROJ/.venv/bin/pip" install -r "$PROJ/requirements.txt"
fi

cat > "$SCRIPT" <<APPLESCRIPT
set proj to "$PROJ"
do shell script "cd " & quoted form of proj & " && ./run_mac.command --server.headless true >/tmp/muse2-streamlit.log 2>&1 &"
delay 2.5
open location "http://localhost:8501"
APPLESCRIPT

osacompile -o "$APP" "$SCRIPT"
echo "Aplikasi terpasang di: $APP"
echo "Klik dua kali ikon di Desktop. Jangan pindahkan folder:"
echo "  $PROJ"
open "$HOME/Desktop"
