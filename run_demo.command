#!/bin/bash
# Versi demo: klik dua kali di Finder (atau jalankan: bash run_demo.command).
# Tanpa Muse/Polar: perangkat simulasi + 3 sesi contoh untuk mencoba CASS.
cd "$(dirname "$0")"
exec ./run_mac.command --demo "$@"
