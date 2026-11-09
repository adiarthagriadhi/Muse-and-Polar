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
| D-05 | Grid **3 × 3**. Tetap **2 dimensi** (dua sumbu, X dan Y), bukan 3D: tiap sumbu dibagi tiga zona sehingga bidang terpotong menjadi 9 sel. 3D baru terjadi bila ada sumbu ketiga (mis. denyut atau waktu). | zona netral menghindari label dari perubahan kecil | berntson1991, russell1980 | 2026-11-09 |
| D-06 | Zona netral **\|z\| < 0,6**, batas "sedang" skala besaran Hopkins; besaran tiap sumbu ditampilkan: trivial < 0,2 · kecil < 0,6 · sedang < 1,2 · besar < 2,0 · sangat besar < 4,0 | ambang yang lazim dan berdasar di ilmu olahraga, menggantikan ±0,5 z tanpa rujukan; diadaptasi dari SD antarsubjek ke z robust terhadap R0, jadi tetap diuji di v0.5 | hopkins2009 | 2026-11-09 |
| D-07 | Semua nama alternatif dari rujukan dipakai: nama CorVa sebagai label utama, ditambah istilah tiap sumber (dan analogi Russell, ditandai *analogi*) | lihat `ALT_NAMES` di `labels.py` dan tabel di `EVIDENCE.md` | bird2018, pope1995, thayer2000, thayer2009, borghini2014, ehrhardt2022, stanley2013, laborde2017, laborde2018, barry2007, russell1980 | 2026-11-09 |
| D-08 | Fase = **protokol standar** di dashboard, dicatat sebagai penanda "CorVa: …": Relaks (baseline) 5 menit; mata terbuka napas biasa, mata terbuka napas dalam, mata tertutup napas biasa, mata tertutup napas dalam, masing-masing 3 menit (menit pertama = stabilisasi, tidak dianalisis). Total 17 menit. Napas dalam = 6/menit (5 s tarik, 5 s hembus). | durasi dari standar HRV jangka pendek dan jendela minimal RMSSD; EEG istirahat stabil ≥ 40 s | taskforce1996, bourdillon2017, munoz2015, esco2014, gudmundsson2007, barry2007, lehrer2014, laborde2022, zaccaro2018 | 2026-11-09 |

## Masih terbuka (nilai sementara sudah dipakai di `labels.py`)

| Kode | Pertanyaan | Nilai sementara | Pilihan lain | Rujukan / status |
|---|---|---|---|---|
| D-09 | Sumbu X | log(β/α) rata-rata 4 kanal | hanya AF7/AF8; indeks *engagement* β/(α+θ) | ehrhardt2022, barry2007; alternatif pope1995 |
| D-10 | Y: RMSSD atau lnRMSSD | lnRMSSD | RMSSD (seperti CASS sekarang) | plews2012, esco2014 |
| D-11 | Syarat minimal label per ruas | ≥ 60 s RR valid | ≥ 120 s (Muñoz dkk. 2015) | esco2014, munoz2015 |
| D-12 | Penanda tambahan Q3 | θ/β, ambang sama dengan D-06 | θ saja; tanpa penanda | borghini2014, klimesch1999 |
| D-13 | Penanganan artefak EEG | seperti CASS (NB06) | potongan 2 s seperti Research View | crabbe2004 (konteks gerak); perlu uji banding |
| D-15 | Urutan blok protokol | sesuai urutan di D-08 (tetap) | urutan diacak/diseimbangkan antarpeserta pada studi validasi | laborde2022: efek napas lambat masih ada segera sesudah sesi, jadi bisa terbawa ke blok berikutnya |
| D-16 | Laju napas dalam | 6/menit tetap untuk semua | frekuensi resonansi individual (asesmen terpisah) | lehrer2014, shaffer2020 |
| D-14 | Hubungan dengan label lama Research View | tidak dihidupkan lagi; CASS-NV menggantikannya untuk CASS | dikembalikan sebagai pembanding | keputusan desain, tanpa rujukan |
