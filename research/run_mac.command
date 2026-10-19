#!/bin/bash
# Klik dua kali di Finder (atau ./run_mac.command) untuk membuka Muse 2 Research View di browser.
# Memakai virtualenv sendiri (research/.venv), terpisah dari dashboard live musepolar.
# Opsi diteruskan, mis.: ./run_mac.command --port 8601 --root ~/Desktop/rekaman
set -e
cd "$(dirname "$0")"
if [ ! -d .venv ]; then
  echo "Membuat virtualenv (research/.venv) ..."
  python3 -m venv .venv
  ./.venv/bin/pip install --upgrade pip >/dev/null
  ./.venv/bin/pip install -r requirements.txt
fi
export PYTHONPATH=src
exec ./.venv/bin/python app/server.py "$@"
