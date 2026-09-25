#!/bin/bash
# Klik dua kali di Finder (atau jalankan ./run_mac.command) untuk memulai dashboard.
# Argumen tambahan diteruskan, mis.: ./run_mac.command --sim
set -e
cd "$(dirname "$0")"
if [ ! -d .venv ]; then
  echo "Membuat virtualenv (.venv) ..."
  python3 -m venv .venv
  ./.venv/bin/pip install --upgrade pip >/dev/null
  ./.venv/bin/pip install -r requirements.txt
fi
exec ./.venv/bin/python -m musepolar "$@"
