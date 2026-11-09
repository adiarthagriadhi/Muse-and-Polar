# Keputusan CASS-NV (CorVa Space)

Setiap perubahan metode dicatat di sini **sebelum** dikodekan. Format: kode, keputusan, alasan,
tanggal, status.

## Aturan kerja: bukti dulu (D-00)

1. Setiap keputusan metode menyebut **kunci rujukan** dari [`references.json`](references.json).
2. Rujukan baru dimasukkan ke `references.json` lengkap dengan DOI, temuan yang dipakai, bagian yang
   sudah dibaca, dan status verifikasi.
3. Aturan di kode ditautkan lewat `EVIDENCE` di [`labels.py`](labels.py). Aturan tanpa rujukan harus
   ditandai `assumption` dan masuk rencana validasi.
4. Setelah mengubah rujukan atau aturan, jalankan `python -m corva.evidence_md` untuk memperbarui
   [`EVIDENCE.md`](EVIDENCE.md).
5. `tests/test_corva_evidence.py` menolak:
   - aturan tanpa rujukan yang tidak dinyatakan asumsi;
   - kunci rujukan yang tidak ada;
   - rujukan yang tidak dipakai;
   - `EVIDENCE.md` yang tidak mutakhir.
6. Rujukan bertanda ⚠ (DOI atau penulis belum terverifikasi) tidak dikutip di manuskrip sebelum dicek.

## Sudah diputuskan

| Kode | Keputusan | Alasan | Rujukan | Tanggal |
|---|---|---|---|---|
| D-00 | Aturan kerja *bukti dulu* (di atas) | model harus bisa dilacak ke literatur | | 2026-11-09 |
| D-01 | Nama: merek **CorVa Space**, nama teknis **CASS-NV** (*CASS Neurovisceral State Map*), tagar **#NeuroVagal** | ruang dua sumbu dan integrasi neuroviseral | berntson1991, thayer2000 | 2026-11-09 |
| D-02 | Hub di folder `corva/` dalam repo Muse-and-Polar; kode dan metode saja, tanpa data peserta | repo publik; dekat dengan `cass_polar/` dan dashboard | | 2026-11-09 |
| D-03 | Sumbu Y dari **RR Polar H10**, bukan PPG Muse | RMSSD ultra-singkat PPG dahi ditaksir berlebih; PPG bukan pengganti EKG saat bergerak | griadhi2026, laborde2017 | 2026-11-09 |
| D-04 | Denyut jantung **bukan** komponen label, hanya keterangan | denyut bukan penanda vagal; label lama Research View mencampurnya | laborde2017, shaffer2017 | 2026-11-09 |

## Masih terbuka (nilai sementara sudah dipakai di `labels.py`)

| Kode | Pertanyaan | Nilai sementara | Pilihan lain | Rujukan / status |
|---|---|---|---|---|
| D-05 | Grid 3 × 3 atau 4 kuadran + netral? | 3 × 3 | 4 kuadran + satu zona netral | russell1980, berntson1991 |
| D-06 | Ambang zona netral | ±0,5 z | ±1,0 z; ambang per sumbu | **asumsi**, belum ada rujukan |
| D-07 | Nama label (terutama Q3) | lihat `MODEL.md` §3 | nama sesuai bahasa naskah | bird2018, russell1980 |
| D-08 | Sumber fase | marker dashboard (*Baseline mulai*, *Tugas mulai*, *Pemulihan mulai*) | dipilih manual di explorer | laborde2018 |
| D-09 | Sumbu X | log(β/α) rata-rata 4 kanal | hanya AF7/AF8; indeks *engagement* β/(α+θ) | ehrhardt2022, barry2007; alternatif pope1995 |
| D-10 | Y: RMSSD atau lnRMSSD | lnRMSSD | RMSSD (seperti CASS sekarang) | plews2012, esco2014 |
| D-11 | Syarat minimal label per ruas | ≥ 60 s RR valid | ≥ 120 s (Muñoz dkk. 2015) | esco2014, munoz2015 |
| D-12 | Penanda tambahan Q3 | θ/β, ambang sama dengan D-06 | θ saja; tanpa penanda | borghini2014, klimesch1999 |
| D-13 | Penanganan artefak EEG | seperti CASS (NB06) | potongan 2 s seperti Research View | crabbe2004 (konteks gerak); perlu uji banding |
| D-14 | Hubungan dengan label lama Research View | tidak dihidupkan lagi; CASS-NV menggantikannya untuk CASS | dikembalikan sebagai pembanding | keputusan desain, tanpa rujukan |
