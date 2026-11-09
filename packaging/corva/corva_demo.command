#!/bin/bash
# CorVa Space versi demo (tanpa Muse/Polar): perangkat simulasi + sesi contoh, termasuk dua sesi protokol CorVa.
cd "$(dirname "$0")"
exec ./corva_mac.command --demo --data-dir corva_demo "$@"
