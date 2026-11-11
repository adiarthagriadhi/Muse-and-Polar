# Changelog

## [Unreleased] – calon 1.0.1 (belum dirilis; menunggu persetujuan penulis)

### Fixed
- **Sinkronisasi Muse–Polar gagal di lapangan.** `SampleClock` (stempel waktu per sampel) menjangkar
  ulang ke paket yang datang > 0,25 s terlambat lalu menolak mundur, sehingga satu keterlambatan
  pengiriman Bluetooth (pengiriman ulang, event loop sibuk) menggeser semua stempel waktu berikutnya dari
  aliran itu sebesar lamanya keterlambatan, sampai koneksi diputus. Bila pergeseran Muse dan Polar
  berbeda > 1 s, loncatan tetap terdeteksi di kedua sensor tetapi `estimate_offset` (pencarian ±1 s)
  melaporkan "korelasi rendah"; bila < 1 s, hasilnya "berhasil" dengan offset yang memuat pergeseran
  itu. Jangkar kini mengikuti batas bawah waktu terima (turun seketika, naik pelan), dan hanya
  menjangkar maju bila selisih > 5 s. Berlaku untuk semua aliran yang memakai `SampleClock`
  (EEG, PPG, ACC, giroskop Muse; EKG dan ACC Polar). RR Polar tidak terpengaruh.
- `estimate_offset`: pencarian ±3 s (sebelumnya ±1 s); puncak di tepi rentang tidak lagi diterima;
  hasil ambigu (puncak kedua ≥ 0,85 × puncak utama, mis. loncatan berjarak sama persis) ditolak.
  Keluaran baru: `second_peak`, `max_lag_s`.

### Added
- `python -m musepolar.diagnose <folder sesi>`: diagnosis teknis rekaman (laju dari stempel waktu,
  celah, pergeseran stempel waktu Polar terhadap jam strap `sensor_ns`, analisis ulang setiap jendela
  sinkronisasi dengan aturan v1.0.0 dan pencarian lebar). Hanya mencetak angka; tidak membaca nilai
  EEG/PPG/EKG/HR/RR, nama, catatan, atau penanda teks bebas.
- Tes regresi `tests/test_sync_regression.py` yang mengirim byte paket Muse/Polar asli melalui
  dekoder dengan jam terima yang disimulasikan (jitter, keterlambatan pengiriman).

### Known limitations
- Simulator (`--sim`) menulis stempel waktu ideal langsung ke hub, tidak melalui dekoder dan
  `SampleClock`; karena itu kegagalan ini tidak pernah muncul di `--sim` maupun di tes v1.0.0.

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
