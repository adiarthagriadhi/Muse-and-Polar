# Roadmap CASS-NV (CorVa Space)

| Versi | Isi | Status |
|---|---|---|
| **v0.1 Rancangan** | Hub, model, rujukan, daftar keputusan, kode label 3 × 3 dengan uji | selesai (folder ini) |
| **v0.2 Mesin** | `labels.py` dihubungkan ke `cass_polar/engine.window_state()`: lnRMSSD, θ/β per jendela, fase dari marker, label per jendela dan per ruas, syarat data | setelah D-05 s.d. D-12 diputuskan |
| **v0.3 Tampilan** | Explorer CorVa Space: grid 3 × 3 di peta CASS, kartu label per ruas (label, arti, fase, keyakinan), tombol **Tampilkan CorVa** di dashboard, ekspor CSV/PDF | |
| **v0.4 Demo** | Sesi demo dengan fase istirahat → aktivitas → pemulihan, untuk uji coba tanpa alat | |
| **v0.5 Validasi** | Protokol kondisi-diketahui (mata terbuka/tertutup, PASAT, napas 6/menit, latihan + pemulihan) dengan pembanding subjektif; reliabilitas uji-ulang. Data dan analisis di repo riset privat, bukan di sini. | |
| **v1.0 Rilis** | Metode dikunci (`DECISIONS.md`), dokumentasi, sitasi, naskah metode | |

## Protokol validasi (usulan untuk v0.5)

| Blok | Durasi | Harapan CASS-NV |
|---|---|---|
| Istirahat mata terbuka (R0) | 3 menit | netral (acuan) |
| Mata tertutup | 2 menit | korteks melambat / Q2 |
| Aritmetika serial (PASAT) | 3 menit | Q4 |
| Napas lambat 6/menit | 3 menit | Q2 |
| Latihan submaksimal | sesuai protokol | Q4 (artefak gerak dicatat) |
| Pemulihan duduk | 10 menit | Q4 → Q3 → Q2 |

Pembanding subjektif per blok: skala arousal/afek, NASA-TLX (setelah PASAT), Karolinska Sleepiness Scale.
