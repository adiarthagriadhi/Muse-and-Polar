#!/usr/bin/env bash
# Menjalankan Muse–Polar dari terminal.
#
# Pemakaian:
#   bash jalankan.sh            # simulator (tanpa perangkat), http://localhost:8765
#   bash jalankan.sh sim        # sama seperti di atas
#   bash jalankan.sh live       # dashboard live dengan Muse 2 + Polar H10 (Bluetooth)
#   bash jalankan.sh research   # Research View, http://127.0.0.1:8600
#   bash jalankan.sh test       # jalankan tes (pytest)
#
# Skrip boleh dijalankan dari folder repo mana pun; jika repo belum ada,
# skrip akan meng-clone ke ~/Muse-and-Polar (ubah dengan MUSEPOLAR_DIR).

set -euo pipefail

MODE="${1:-sim}"
REPO_URL="https://github.com/adiarthagriadhi/Muse-and-Polar.git"

# --- 1. Tentukan folder repo -------------------------------------------------
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [ -f "$SCRIPT_DIR/musepolar/__main__.py" ]; then
  REPO_DIR="$SCRIPT_DIR"
else
  REPO_DIR="${MUSEPOLAR_DIR:-$HOME/Muse-and-Polar}"
  if [ ! -d "$REPO_DIR/.git" ]; then
    echo ">> Meng-clone repo ke $REPO_DIR"
    git clone "$REPO_URL" "$REPO_DIR"
  fi
fi
cd "$REPO_DIR"

# --- 2. Cari Python 3.11–3.13 ------------------------------------------------
PY=""
for cand in python3.13 python3.12 python3.11 python3; do
  if command -v "$cand" >/dev/null 2>&1; then
    if "$cand" -c 'import sys; raise SystemExit(0 if (3,11) <= sys.version_info[:2] <= (3,13) else 1)'; then
      PY="$cand"
      break
    fi
  fi
done
if [ -z "$PY" ]; then
  echo "!! Butuh Python 3.11–3.13. Pasang dulu (mis. 'brew install python@3.12')." >&2
  exit 1
fi
echo ">> Memakai $($PY --version) ($(command -v "$PY"))"

# --- 3. Virtual environment + dependensi ------------------------------------
if [ ! -d .venv ]; then
  echo ">> Membuat virtual environment .venv"
  "$PY" -m venv .venv
fi
# shellcheck disable=SC1091
source .venv/bin/activate

REQ="requirements-lock.txt"
[ "$MODE" = "test" ] && REQ="requirements-dev.txt"
STAMP=".venv/.terpasang-$(basename "$REQ" .txt)"
if [ ! -f "$STAMP" ] || [ "$REQ" -nt "$STAMP" ]; then
  echo ">> Memasang dependensi dari $REQ"
  python -m pip install --quiet --upgrade pip
  python -m pip install --quiet -r "$REQ"
  touch "$STAMP"
fi

# --- 4. Jalankan -------------------------------------------------------------
case "$MODE" in
  sim)
    echo ">> Dashboard (simulator) -> http://localhost:8765  (Ctrl+C untuk berhenti)"
    exec python -m musepolar --sim --autoconnect
    ;;
  live)
    echo ">> Dashboard live -> http://localhost:8765  (Ctrl+C untuk berhenti)"
    echo "   Nyalakan Muse 2 dan Polar H10 dulu. Di macOS, izinkan Bluetooth untuk Terminal."
    exec python -m musepolar
    ;;
  research)
    echo ">> Research View -> http://127.0.0.1:8600  (membaca folder recordings/)"
    cd research
    PYTHONPATH=src exec python app/server.py
    ;;
  test)
    exec python -m pytest
    ;;
  *)
    echo "Mode tidak dikenal: $MODE" >&2
    echo "Pilih: sim | live | research | test" >&2
    exit 1
    ;;
esac
