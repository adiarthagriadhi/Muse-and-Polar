#!/bin/bash
# Klik dua kali di Finder (atau ./run_mac.command) untuk membuka Muse 2 Research View.
# Memakai virtualenv sendiri (research/.venv), terpisah dari dashboard live musepolar.
# Argumen tambahan diteruskan ke streamlit, mis.: ./run_mac.command --server.port 8502
set -e
cd "$(dirname "$0")"
if [ ! -d .venv ]; then
  echo "Membuat virtualenv (research/.venv) ..."
  python3 -m venv .venv
  ./.venv/bin/pip install --upgrade pip >/dev/null
  ./.venv/bin/pip install -r requirements.txt
fi
export PYTHONPATH=src
exec ./.venv/bin/streamlit run app/streamlit_app.py "$@"
