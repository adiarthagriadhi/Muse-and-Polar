# Changelog

## [1.0.0] – 2026-10-08

First open release.

### Live dashboard (`musepolar`)
- Direct BLE recording of Muse 2 (EEG, PPG, accelerometer, gyroscope, telemetry) and Polar H10
  (HR/RR, ECG, accelerometer with sensor timestamps) on one host clock; raw CSV + `session.json`.
- Markers, automatic reconnection, movement-based Muse–Polar clock synchronisation with drift
  estimate, simulator (`--sim`).

### Research View (`research/`)
- Segment-wise EEG band power with artefact rejection, change vs. a reference segment, head maps,
  Mann–Whitney tests with Holm correction and Cliff's δ, Kruskal–Wallis; CSV/PNG/Word export.
- Input: musepolar sessions, EDF/EDF+/BDF, Mind Monitor, muselsl, OpenBCI and generic EEG CSV,
  Polar Sensor Logger files joined by clock time.
- Heart: forehead PPG with the B1 reference pipeline (`ppg_b1.py`), reported as PRV; the same
  interval rule for Polar RR/ECG (HRV). Single-file browser version with identical results.
- No condition/state labels.

### Tools
- `tools/penanda-waktu-tari.html`: time markers with movement-quality rating on a video.

### Project
- MIT licence, citation metadata, contributing guide, CI on Linux and macOS, pinned dependencies.
