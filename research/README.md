# Muse 2 Research View

Aplikasi web lokal untuk **menganalisis rekaman** yang dibuat dashboard live [`musepolar`](../README.md):
EEG Muse 2, pulsa dahi (PPG), dan bila ada, interval RR Polar H10. Aplikasi ini hanya membaca rekaman,
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
    io.py                  baca sesi musepolar, sinkronisasi Polar
    eeg.py                 filter, spektrum potongan & jendela (plus fungsi lama)
    hrv.py                 deteksi denyut PPG, pembersihan interval, HRV/PRV
    analysis.py            analisis per sesi/ruas, label, uji statistik
    report.py              ekspor CSV (ZIP), gambar PNG, laporan Word
    prv09.py, segments.py, maps.py   metode lama (dipakai legacy/)
  legacy/                  lima front-end lama, lihat legacy/README.md
  tests/                   python -m pytest research/tests
```

Versi asli paket (sebelum semua perubahan) tersimpan di riwayat git, commit `224f88e`.
