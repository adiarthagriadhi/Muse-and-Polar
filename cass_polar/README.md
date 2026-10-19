# CASS–Polar H10 (experimental branch)

**Branch:** `feature/cass-polar-h10`. The `main` branch and original Muse–PPG CASS toolkit remain unchanged.

This initial adapter replaces CASS NB10's PPG-based autonomic Y with **Polar H10 ECG-derived RR RMSSD**, while retaining the existing NB06/NB10 cortical X and 5 s / 2.5 s windows. The original toolkit has **not yet been copied into this repository**: run it separately to produce a `cass_state_*.csv`, then run this adapter.

## Usage

Install `numpy` and `pandas`, then:

```bash
python cass_polar/polar_adapter.py \
  --state path/to/cass_state_P01.csv \
  --rr recordings/SESSION/polar_rr.csv \
  --eeg recordings/SESSION/muse_eeg.csv \
  --output cass_state_P01_polar.csv
```

The input CASS state must be generated from **the same EEG session**, with baseline `PRE`/R0. The Muse–Polar live CSV files use Unix timestamps. The first Muse EEG timestamp anchors the shared relative clock; use `--offset-s` **only** for a measured, validated Muse-minus-Polar correction. Do not shift timestamps without evidence. Input Polar RR timestamps denote interval endpoints.

The output contains `polar_rr_rmssd`, `polar_n_ibi`, `polar_hr`, recomputed `autonomic_state`, `quadrant`, `distance_reference`, and `autonomic_valid`; the companion `.provenance.json` records methods and sources. Missing HRV remains NaN, never zero.

**Methodology:** the Polar RR filter retains 300–2000 ms intervals and only adjacent valid intervals differing by ≤20%. At least eight valid intervals per span are required, and at least one consecutive valid pair is required for RMSSD. Default span 20 s (exploratory ultra-short HRV, **not equivalent to standard 5-minute HRV**). R0 median centers Y; robust scale uses all valid windows. This is a new Polar-specific method, not an unchanged NB10 PRV calculation.

**Important limitations:** This adapter operates on a precomputed CASS CSV, not raw Muse EEG. The original toolkit's HTML generator may still display hardcoded PPG labels unless updated. Do **not** label old HTML as Polar without regenerating its metadata and captions. No clinical inference. Validate with real synchronized recordings and compare numerical results before publication.

## In the live dashboard

The dashboard (`python -m musepolar`) serves this engine directly: after a recording, the CASS panel
has **Ekspor sesi** (saves `<session>_CASS_Polar.zip`, including `muse_ppg.csv` for reference) and
**Tampilkan CASS** (opens `/cass/session/<session>`, computed by `engine.py` from `muse_eeg.csv` and
`polar_rr.csv`). No separate CASS toolkit process is needed for this view.

## Next integration step

Port the uploaded CASS toolkit source into this branch (excluding participant datasets), connect its ZIP ingestion and HTML payload to `polar_rr_rmssd`, and add end-to-end integration tests. Until then this is a functional offline Polar Y adapter, **not** a finished one-click CASS–Polar dashboard.
