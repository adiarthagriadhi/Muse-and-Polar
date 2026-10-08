# Muse–Polar

[![tests](https://github.com/adiarthagriadhi/Muse-and-Polar/actions/workflows/tests.yml/badge.svg)](https://github.com/adiarthagriadhi/Muse-and-Polar/actions/workflows/tests.yml)

Open research software for **recording and analysing a Muse 2 EEG headband together with a Polar H10
chest strap**. It has three parts:

| Part | Folder | What it does |
|---|---|---|
| **Live dashboard** (`musepolar`) | [`musepolar/`](musepolar/) | Connects directly to Muse 2 and Polar H10 over Bluetooth Low Energy, shows the signals live in the browser, records raw CSV with per-sample timestamps, event markers, and a movement-based Muse–Polar clock synchronisation. Includes a simulator. |
| **Research View** (`muse2_pipeline`) | [`research/`](research/README.md) | Offline analysis of musepolar recordings and of EDF/EDF+/BDF and other EEG CSV files: EEG band power per segment, head maps, artefact rejection, between-segment tests, pulse (PRV) and Polar (HRV) intervals, CSV/PNG/Word export. Also available as a single HTML file that runs in the browser without Python. |
| **Tools** | [`tools/`](tools/) | `penanda-waktu-tari.html`: a browser tool to mark time points (and a 1–5 movement-quality rating) on a video, exported as CSV for alignment with EEG recordings. |

> **Not a medical device.** This software is for research and teaching. It does not diagnose, monitor
> or treat any condition and must not be used for clinical decisions.

## Statement of need

Consumer EEG headbands and chest-strap heart-rate sensors are increasingly used in field studies of
brain–heart physiology, but researchers usually need several vendor apps (Muse Direct, Mind Monitor,
Polar apps) that record on separate clocks, export different formats and hide the raw timestamps.
Muse–Polar records **both devices in one session on one host clock**, keeps the **raw data and
per-sample timestamps** (including the Polar H10 sensor clock), lets the experimenter add markers and
measure the residual Muse–Polar offset with a shared physical event, and provides an open,
tested analysis pipeline for the resulting files. It is intended for physiologists and
psychophysiology researchers who need a transparent, scriptable alternative to closed consumer apps.

## Features

- Muse 2: EEG 4 channels (TP9, AF7, AF8, TP10) at 256 Hz, PPG (ambient, infrared, red) at 64 Hz,
  accelerometer and gyroscope at 52 Hz, telemetry.
- Polar H10: heart rate and RR intervals, raw ECG at 130 Hz, accelerometer at 200 Hz, sensor timestamps.
- Live view: EEG traces with display filters and signal-quality estimate, relative band power,
  PPG, ECG, RR tachogram, short-term HRV from Polar RR (RMSSD, SDNN, pNN50 over the last 60 s).
- Recording to plain CSV + `session.json`; markers from the keyboard; automatic BLE reconnection.
- Muse–Polar synchronisation by cross-correlating both accelerometers during 2–3 small jumps;
  drift estimate when synchronised at start and end.
- Research View: segment-wise EEG band power with artefact rejection, Mann–Whitney tests with
  Holm correction and Cliff's δ, head maps, PRV/HRV intervals, multi-channel EDF/BDF with a
  "Muse-like" 4-channel mode, Polar Sensor Logger files joined by clock time, reports.
- The B1 reference PPG pipeline (`research/src/muse2_pipeline/ppg_b1.py`), see
  [Heart-rate and PRV](#heart-rate-and-pulse-rate-variability).

## Installation

Python 3.11–3.13. Live Bluetooth recording has been tested on **macOS only** (12 or later); the
underlying library ([`bleak`](https://github.com/hbldh/bleak)) also supports Linux and Windows, but
those platforms have not been tested with the real devices. The simulator, the Research View and the
tests run on macOS and Linux (CI).

```bash
git clone https://github.com/adiarthagriadhi/Muse-and-Polar.git
cd Muse-and-Polar
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-lock.txt     # exact tested versions (or requirements-dev.txt for version ranges)
```

On macOS you can instead double-click `run_mac.command` (dashboard) or `research/run_mac.command`
(Research View); they create their own virtual environments.

## Example with the simulator (no devices needed)

```bash
python -m musepolar --sim --autoconnect
```

The browser opens at `http://localhost:8765` with synthetic EEG (alpha rhythm and eye blinks), PPG,
and ECG with respiratory sinus arrhythmia. Click **Mulai rekam** (start recording), add markers with
keys `1`–`5`, then stop. The session is written to `recordings/<date_time>_<name>/`. Analyse it:

```bash
cd research
PYTHONPATH=src python app/server.py          # opens http://127.0.0.1:8600, reads ../recordings
```

Or open `research/web/research-view.html` directly in a browser and press **Data contoh** (example
data, synthetic).

Reading a recording in Python:

```python
import pandas as pd
d = "recordings/20260925_101500_demo"
eeg = pd.read_csv(f"{d}/muse_eeg.csv")      # timestamp, TP9, AF7, AF8, TP10 (µV)
rr = pd.read_csv(f"{d}/polar_rr.csv")       # timestamp, rr_ms
markers = pd.read_csv(f"{d}/marker.csv")
```

The full file format, command-line options, synchronisation procedure and troubleshooting are in the
user guide [`docs/panduan-dashboard-id.md`](docs/panduan-dashboard-id.md) and
[`research/README.md`](research/README.md) (currently in Indonesian).

## Heart rate and pulse-rate variability

The Muse 2 forehead PPG gives **pulse-rate variability (PRV)**, not heart-rate variability (HRV);
only the Polar H10 (ECG-derived RR) gives HRV. In the validation study B1 (Griadhi, Suadnyana &
Wahyuni, 2026, medRxiv preprint, [doi:10.64898/2026.10.05.26364782](https://doi.org/10.64898/2026.10.05.26364782)),
Muse 2 agreed with Polar H10 for **heart rate**, but **ultra-short (60 s) RMSSD from the
forehead PPG was overestimated**. The preprint has not been peer reviewed. Do not use Muse PRV indices as a substitute for HRV.

- `research/src/muse2_pipeline/ppg_b1.py` is the pre-specified B1 pipeline (PPG_2/infrared,
  Butterworth 3rd order 0.6–3.5 Hz zero-phase, peaks ≥ 60/160 s apart with prominence 1.4826 × MAD,
  intervals 300–2000 ms and ≤ 20 % change from the preceding interval, RMSSD from successive valid
  intervals only). It reproduces the B1 analysis functions exactly (checked against the B1 analysis
  script on synthetic signals) and is the only PPG pipeline.
- The Research View (Python and the single-file browser version) uses this pipeline for the
  forehead PPG and applies the same interval rule to Polar RR and ECG intervals; a test checks that
  the browser engine gives the same pulse times as the Python code.
- Known properties of the B1 pipeline on synthetic signals: pulse times are quantised to the 64 Hz
  sample grid (≈16 ms), which by itself adds RMSSD of the order of 10 ms even for perfectly regular
  pulses; and at low heart rates very narrow pulses on a flat, noise-free baseline can produce extra
  detections (documented by an expected-failure test). Both are consistent with treating PPG RMSSD
  with caution.

## Limitations

- Live BLE recording tested on macOS only.
- Timestamps are anchored to Bluetooth receive time; BLE latency (≈20–100 ms) remains unless the
  movement synchronisation is used. Sync resolution is limited by the Muse accelerometer (52 Hz).
- The Muse 2 BLE protocol is not publicly documented by the manufacturer; it was implemented
  following the open-source muse-js and muselsl projects and may break with firmware updates.
- Forehead PPG: see above (PRV ≠ HRV; ultra-short RMSSD overestimated).
- The Research View reports band power, changes relative to a reference segment and statistics; it
  does not assign condition or state labels.
- User interface text is in Indonesian.

## Tests

```bash
pip install -r requirements-dev.txt
python -m pytest
```

Tests cover the BLE decoders, an end-to-end run with the simulator, the research pipeline (CSV, EDF,
Polar files, statistics, the B1 PPG pipeline) and, when Node.js is installed, equality of the browser
engine with the Python pipeline. They run in GitHub Actions on every push.

## Data and privacy

The repository contains no participant data. Example data are generated by the simulator or the
synthetic demo in the Research View. `recordings/` and common raw-data formats are git-ignored.

## Third-party notices

Muse is a trademark of Interaxon Inc.; Polar and H10 are trademarks of Polar Electro Oy. This project
is independent and not affiliated with or endorsed by either company. See
[`docs/THIRD-PARTY.md`](docs/THIRD-PARTY.md).

## How this software was developed

The code was written with the assistance of Claude Code (Anthropic), an AI coding assistant, under
the direction of the author, who specified the requirements and reviewed and verified the code and
its behaviour. The author takes responsibility for the software.

## Citation, licence and contributing

- Cite as described in [`CITATION.cff`](CITATION.cff).
- Licence: MIT, see [`LICENSE`](LICENSE).
- Contributions and bug reports: see [`CONTRIBUTING.md`](CONTRIBUTING.md).

Author: I Putu Adiartha Griadhi, Department of Physiology, Faculty of Medicine, Universitas Udayana,
Bali, Indonesia ([ORCID 0000-0002-9895-9353](https://orcid.org/0000-0002-9895-9353)).
