#!/bin/bash
# CorVa Space (macOS/Linux): klik dua kali di Finder, atau jalankan ./corva_mac.command di Terminal.
# Terpisah dari dashboard Muse-Polar yang lama: port 8775, rekaman di corva_recordings/, virtualenv di .venv/.
# Argumen tambahan diteruskan, mis.: ./corva_mac.command --sim
set -e
cd "$(dirname "$0")"
PY="${PYTHON:-python3}"
if [ ! -d .venv ]; then
  echo "Membuat virtualenv (.venv) ..."
  "$PY" -m venv .venv
  ./.venv/bin/python -m pip install --upgrade pip >/dev/null
fi
if [ ! -f .venv/.req-installed ] || [ requirements.txt -nt .venv/.req-installed ]; then
  ./.venv/bin/python -m pip install -r requirements.txt && touch .venv/.req-installed
fi
exec ./.venv/bin/python -m musepolar --port 8775 --data-dir corva_recordings "$@"
