# Muse 2 Research View

Aplikasi web lokal untuk **menganalisis rekaman** EEG: sesi dari dashboard live [`musepolar`](../README.md)
(EEG Muse 2, pulsa dahi/PPG, interval RR Polar H10) dan file **EDF / EDF+ / BDF** dengan berapa pun kanal
(mis. 16 kanal sistem 10-20). Aplikasi ini hanya membaca rekaman,
tidak merekam, dan bukan alat diagnosis.

Folder `research/` berdiri sendiri: dependensi dan virtualenv sendiri (`research/.venv`), tidak mengimpor
paket `musepolar`, hanya membaca file CSV hasil rekamannya.

## Menjalankan (macOS)

```bash
cd Muse-and-Polar/research
./run_mac.command
```

Saat pertama kali dijalankan, skrip membuat `research/.venv` dan memasang `requirements.txt`, lalu membuka
`http://127.0.0.1:8600`. Untuk ikon di Desktop, klik dua kali `Pasang Muse2 Research.command`.

Manual / opsi:

```bash
cd research
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
PYTHONPATH=src python app/server.py                         # folder default: ../recordings
PYTHONPATH=src python app/server.py --root ~/rekaman --port 8601 --no-browser
```

## Tampilan

| Bagian | Isi |
|---|---|
| **Atas** | pilih sesi, pilih folder, unggah ZIP; ekspor **Laporan Word**, **Data CSV** (ZIP), **Gambar** (PNG), **Cetak/PDF**; tema terang/gelap |
| **Pengaturan** | *Titik observasi* (memotong sesi menjadi ruas; tombol **Pakai penanda** mengisinya dari `marker.csv`), pita δ/θ/α/β, daya **absolut** (µV²) atau **relatif** (% daya 1–40 Hz), **ruas acuan**, **ambang artefak** |
| **Kanal EEG** | **Semua kanal** (mis. 16) atau **4 kanal (Muse)**: rekaman banyak kanal dibuat meniru Muse 2 — sensor TP9, AF7, AF8, TP10 dibangun ulang dari elektroda di sekitarnya (AF7 = rata-rata Fp1 & F7, AF8 = Fp2 & F8, TP9 = T7 & P7, TP10 = T8 & P8, atau elektrodanya sendiri bila ada; cadangan: AF3/AF4, TP7/TP8, satu elektroda tetangga) dan dirujuk ulang ke Fpz seperti Muse bila kanal Fpz ada. Nama kanal, peta kepala, dan ukuran uji sama dengan sesi Muse, sehingga hasilnya bisa dibandingkan langsung (gunakan *Relatif %* karena merata-rata dua elektroda sedikit menurunkan daya absolut). Rekaman Muse selalu 4 kanal |
| **Data jantung** | PPG + EKG/Polar, hanya PPG, hanya EKG/Polar, atau tanpa data jantung (label kondisi dihitung dari EEG saja). Pilihan yang datanya tidak ada dinonaktifkan |
| **Ringkasan** | durasi, mutu EEG (+ % data bersih per kanal), denyut & PRV dahi, denyut & HRV Polar, offset sinkronisasi, penanda |
| **Kartu ruas** | label kondisi, nilai pita dahi dan z terhadap acuan, denyut, jumlah jendela bersih, peta mini; klik untuk memperbesar ruas; *jadikan acuan* |
| **Sinyal** | EEG 4 lajur, daya pita per jendela, interval antar-denyut (PPG & Polar); **seret untuk zoom**, klik untuk memilih waktu peta, klik ganda untuk kembali; penanda, batas ruas, dan tooltip nilai |
| **Peta kepala** | peta **berlapis** (12 pita warna tipis biru → kuning → merah dengan garis kontur halus) untuk jendela waktu pilihan (geser / lebar 10–60 s), mode **Nilai** atau **Perubahan vs acuan** (z); setiap peta (termasuk peta mini di kartu ruas) memakai skala warnanya sendiri agar kontras; angka di elektroda menunjukkan nilainya |
| **Spektrum** | spektrum 1–40 Hz per ruas (dahi, telinga, atau per kanal) |
| **Per ruas / Uji antar ruas** | tabel nilai & denyut per ruas; Mann–Whitney berpasangan dengan p Holm dan δ Cliff, Kruskal–Wallis bila ≥ 3 ruas |

Titik observasi disimpan per sesi di browser. Semua berjalan lokal (tanpa internet).

## Data masukan

Folder default `recordings/` di akar repo (tempat musepolar menyimpan sesi), bisa diganti lewat
“Folder…”, `--root`, atau variabel lingkungan `MUSE2_RECORDINGS`. ZIP berisi satu atau beberapa folder sesi juga bisa diunggah.

| File musepolar | Dipakai sebagai |
|---|---|
| `muse_eeg.csv` | EEG TP9/AF7/AF8/TP10, **wajib** |
| `muse_ppg.csv` | pulsa dahi dari kolom `ir` (opsional; sesi `--no-ppg` tetap bisa dibuka) |
| `polar_rr.csv` | interval RR Polar H10 (opsional) |
| `marker.csv` | penanda: garis di grafik, nama ruas, isi otomatis *Titik* (penanda `SYNC …` diabaikan) |
| `session.json` | nama, catatan, waktu mulai, hasil sinkronisasi Muse−Polar |

Semua stream memakai titik nol yang sama (sampel EEG pertama). Data Polar digeser dengan
`muse_minus_polar_s` dari sinkronisasi pertama yang berhasil, bila ada.

### File EDF / EDF+ / BDF (mis. 16 kanal)

Letakkan file `.edf`/`.bdf` di folder rekaman (atau pilih foldernya lewat “Folder…”), atau unggah langsung
dengan tombol **Unggah EDF/ZIP**. Setiap file menjadi satu sesi.

| Isi file | Dipakai sebagai |
|---|---|
| kanal bernama 10-20 / 10-10 (`Fp1`, `EEG F3-REF`, `T3`→`T7`, `T5`→`P7`, …) | kanal EEG + posisinya di peta kepala; satuan (µV/mV/V) dikonversi ke µV |
| kanal `ECG`/`EKG` | deteksi puncak R → interval RR, denyut & HRV |
| kanal `PPG`/`Pleth` | denyut & PRV |
| anotasi EDF+ | penanda (garis di grafik, nama ruas, tombol **Pakai penanda**) |
| nama pasien di header | nama sesi |

Kanal bipolar (mis. `Fp1-F7`) dilewati karena tidak punya satu posisi di kepala. Bila tidak ada nama 10-20 sama sekali,
semua kanal bersatuan volt dianalisis dengan nama aslinya (tanpa peta kepala).
Pasangan frontal untuk asimetri dan label kondisi dipilih otomatis: F3/F4, lalu AF7/AF8, AF3/AF4, Fp1/Fp2, F7/F8.
Dengan lebih dari 4 kanal, lajur EEG diwarnai per area kepala dan grafik daya pita menampilkan rata-rata per area
(frontal, sentral, temporal, parietal, oksipital); tabel dan uji tetap per kanal.

## Metode

- **EEG.** Notch 50 Hz + bandpass 1–40 Hz. Spektrum dihitung pada potongan 2 s (Hann, geser 0,25 s).
  Potongan yang melewati ambang artefak (kedip, gerak) atau terlalu datar (< 0,5 µV) dibuang. Daya pita per
  jendela 4 s (geser 2 s) = rerata potongan bersih di dalamnya, sehingga satu kedipan hanya membuang ±2 s data,
  bukan seluruh jendela.
- **Ruas.** Nilai kanal = median jendela bersih. Asimetri AF = (AF8 − AF7)/(AF8 + AF7).
- **Uji.** Mann–Whitney dua sisi memakai jendela yang tidak tumpang tindih (min. 5 per ruas); p dikoreksi
  Holm per ukuran (AF rata-rata, AF7, AF8, TP9, TP10, asimetri); besar efek δ Cliff; Kruskal–Wallis bila ≥ 3 ruas.
- **Label kondisi.** Dibandingkan terhadap ruas acuan dalam satuan z
  (median ruas − median acuan)/SD jendela acuan, pada log daya α, β, θ, rasionya, dan denyut
  (Polar bila ada, selain itu PPG). Bobot skor sama dengan versi asli:
  Teraktivasi = β, α/β, −θ/β, denyut · Fokus = β, α, −θ/α · Tenang = α, θ/β, −denyut; dipilih bila
  skor tertinggi ≥ 0,5 z dan unggul ≥ 0,25 z.
- **Jantung.** PPG inframerah difilter 0,5–3,5 Hz lalu dideteksi puncaknya dengan prominensi adaptif (per 10 s).
  Interval PPG dan RR Polar di luar 35–180 bpm, atau berbeda > 25 % dari median sekitarnya, ditandai tidak valid.
  RMSSD hanya dari pasangan interval valid yang berurutan. PRV dahi ≠ HRV Polar.

## Struktur

```
research/
  app/server.py            server web (FastAPI) + CLI
  app/static/              halaman (HTML/CSS/JS tanpa dependensi eksternal)
  src/muse2_pipeline/
    io.py                  baca sesi musepolar dan file EDF, sinkronisasi Polar
    edf.py                 pembaca/penulis EDF, EDF+ (anotasi) dan BDF tanpa dependensi tambahan
    montage.py             nama & posisi elektroda 10-20/10-10, pasangan frontal, area kepala
    eeg.py                 filter, spektrum potongan & jendela (plus fungsi lama)
    hrv.py                 deteksi denyut PPG dan puncak R EKG, pembersihan interval, HRV/PRV
    analysis.py            analisis per sesi/ruas, label, uji statistik
    report.py              ekspor CSV (ZIP), gambar PNG, laporan Word
    prv09.py, segments.py, maps.py   metode lama (dipakai legacy/)
  legacy/                  lima front-end lama, lihat legacy/README.md
  tests/                   python -m pytest research/tests
```

Versi asli paket (sebelum semua perubahan) tersimpan di riwayat git, commit `224f88e`.
