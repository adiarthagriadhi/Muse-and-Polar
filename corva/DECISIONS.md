# Keputusan CASS-NV (CorVa Space)

Setiap perubahan metode dicatat di sini **sebelum** dikodekan. Format: kode, keputusan, alasan,
tanggal, status.

## Sudah diputuskan

| Kode | Keputusan | Alasan | Tanggal |
|---|---|---|---|
| D-01 | Nama: merek **CorVa Space**, nama teknis **CASS-NV** (*CASS Neurovisceral State Map*), tagar **#NeuroVagal** | *autonomic space* (Berntson dkk. 1991) dan integrasi neuroviseral (Thayer & Lane 2000) | 2026-11-09 |
| D-02 | Hub di folder `corva/` dalam repo Muse-and-Polar; kode dan metode saja, tanpa data peserta | repo publik; dekat dengan `cass_polar/` dan dashboard | 2026-11-09 |
| D-03 | Sumbu Y dari **RR Polar H10** (lnRMSSD), bukan PPG Muse | RMSSD ultra-singkat PPG dahi ditaksir berlebih (preprint B1); PPG bukan pengganti EKG saat bergerak (Laborde dkk. 2017) | 2026-11-09 |
| D-04 | Denyut jantung **bukan** komponen label, hanya keterangan | denyut bukan penanda vagal; label lama Research View mencampurnya | 2026-11-09 |

## Masih terbuka (nilai sementara sudah dipakai di `labels.py`)

| Kode | Pertanyaan | Nilai sementara | Pilihan lain |
|---|---|---|---|
| D-05 | Grid 3 × 3 atau 4 kuadran + netral? | 3 × 3 | 4 kuadran + satu zona netral |
| D-06 | Ambang zona netral | ±0,5 z | ±1,0 z; ambang per sumbu |
| D-07 | Nama label (terutama Q3) | lihat `MODEL.md` §3 | nama sesuai bahasa naskah |
| D-08 | Sumber fase | marker dashboard (*Baseline mulai*, *Tugas mulai*, *Pemulihan mulai*) | dipilih manual di explorer |
| D-09 | Sumbu X | log(β/α) rata-rata 4 kanal | hanya AF7/AF8; indeks *engagement* β/(α+θ) |
| D-10 | Y: RMSSD atau lnRMSSD | lnRMSSD | RMSSD (seperti CASS sekarang) |
| D-11 | Syarat minimal label per ruas | ≥ 60 s RR valid | ≥ 120 s (Muñoz dkk. 2015) |
| D-12 | Penanda tambahan Q3 | θ/β, ambang sama dengan D-06 | θ saja; tanpa penanda |
| D-13 | Penanganan artefak EEG | seperti CASS (NB06) | potongan 2 s seperti Research View |
| D-14 | Hubungan dengan label lama Research View | tidak dihidupkan lagi; CASS-NV menggantikannya untuk CASS | dikembalikan sebagai pembanding |
