# Roadmap CASS-NV (CorVa Space)

| Versi | Isi | Status |
|---|---|---|
| **v0.1 Rancangan** | Hub, model, rujukan, daftar keputusan, kode label 3 × 3 dengan uji, protokol standar di dashboard | selesai (folder ini) |
| **v0.2 Mesin** | `corva/session.py` menghubungkan `labels.py` ke `cass_polar/engine.window_state()`: lnRMSSD, θ/β (dan β/(α+θ) pembanding) per jendela, fase protokol dari penanda "CorVa: …" (R0 = baseline setelah menit stabilisasi), label per jendela dan per fase, syarat data (D-11), perbandingan dengan harapan; `python -m corva.session <folder>` | selesai (D-09 s.d. D-17) |
| **v0.3 Tampilan** | Explorer CorVa Space: grid 3 × 3 di peta CASS, kartu label per ruas (label, arti, fase, keyakinan), tombol **Tampilkan CorVa** di dashboard, ekspor CSV/PDF | |
| **v0.4 Demo** | Sesi demo dengan fase istirahat → aktivitas → pemulihan, untuk uji coba tanpa alat | |
| **v0.5 Validasi** | Protokol kondisi-diketahui (mata terbuka/tertutup, PASAT, napas 6/menit, latihan + pemulihan) dengan pembanding subjektif; reliabilitas uji-ulang. Data dan analisis di repo riset privat, bukan di sini. | |
| **v1.0 Rilis** | Metode dikunci (`DECISIONS.md`), dokumentasi, sitasi, naskah metode | |

## Protokol validasi (usulan untuk v0.5)

Inti validasi memakai **protokol standar** (D-08, 17 menit) dengan urutan blok diseimbangkan antarpeserta
(D-15). Bila perlu, protokol bisa diperluas dengan blok yang memunculkan kuadran lain:

| Blok tambahan | Durasi | Harapan CASS-NV |
|---|---|---|
| Aritmetika serial (PASAT) | 3 menit | Q4 |
| Latihan submaksimal | sesuai protokol | Q4 (artefak gerak dicatat) |
| Pemulihan duduk | 10 menit | Q4 → Q3 → Q2 |

Pembanding subjektif per blok: skala arousal/afek, NASA-TLX (setelah PASAT), Karolinska Sleepiness Scale.
