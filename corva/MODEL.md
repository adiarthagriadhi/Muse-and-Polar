# Model CASS-NV (CorVa Space), rancangan v0.1

Status: **sementara**. Nama label, ambang, dan aturan masih menunggu keputusan di
[`DECISIONS.md`](DECISIONS.md).

**Fondasi rujukan.** Setiap aturan di model ini ditautkan ke rujukannya di kode
(`EVIDENCE` di [`labels.py`](labels.py)) dan di bibliografi [`references.json`](references.json).
Peta aturan → rujukan, beserta status verifikasi tiap rujukan, ada di [`EVIDENCE.md`](EVIDENCE.md)
(dihasilkan otomatis). Aturan yang belum punya dasar rujukan ditandai **asumsi** dan wajib divalidasi.

## 1. Sumbu X: kondisi kortikal (EEG Muse 2)

**Ukuran utama:** log(β/α) per kanal, rata-rata TP9, AF7, AF8, TP10, lalu diubah ke z robust terhadap R0
(median, 1,4826 × MAD). Ini sama dengan CASS sekarang.

| Dasar | Isi |
|---|---|
| Kelayakan Muse | Krigolson dkk. 2017 (ERP dengan Muse); Cannard, Wahbeh & Delorme 2021 (spektrum, frekuensi alfa individual, asimetri alfa frontal sebanding dengan sistem 64 kanal) |
| Alfa turun = arousal naik | Barry dkk. 2007: alfa berkorelasi negatif dengan konduktansi kulit; alfa rata-rata layak sebagai ukuran arousal istirahat |
| β/α sebagai indeks arousal | Ehrhardt dkk. 2022: alfa frontal turun dan beta naik saat PASAT dibanding istirahat; membedakan stres dari istirahat, kurang tajam untuk derajat stres |
| Alternatif | indeks *engagement* β/(α+θ) (Pope, Bogart & Bartolome 1995) |
| Penanda tambahan | theta naik saat beban kerja; theta, delta, dan alfa naik bersama saat kelelahan (Klimesch 1999; Borghini dkk. 2014) |
| Konteks olahraga | daya absolut **semua** pita naik saat dan sesudah latihan (Crabbe & Dishman 2004), jadi dipakai **rasio**, bukan alfa absolut |

## 2. Sumbu Y: kondisi vagal (HRV Polar H10)

**Ukuran utama:** lnRMSSD dari RR Polar, z robust terhadap R0.

| Dasar | Isi |
|---|---|
| RMSSD sebagai penanda vagal | Laborde, Mosley & Thayer 2017 (dianjurkan untuk rekaman pendek; LF/HF tidak dianjurkan; PPG bukan pengganti EKG saat bergerak); Shaffer & Ginsberg 2017 |
| Rekaman ultra-singkat | Muñoz dkk. 2015 (10 s r ≈ 0,85; 120 s hampir sempurna); Esco & Flatt 2014 (lnRMSSD 60 s sah saat istirahat dan pascalatihan) |
| Kerangka tafsir | integrasi neuroviseral (Thayer & Lane 2000; Thayer dkk. 2009); *Vagal Tank Theory*: istirahat, reaktivitas, pemulihan (Laborde, Mosley & Mertgen 2018) |
| Olahraga | reaktivasi parasimpatis pascalatihan dan lama pemulihan otonom menurut intensitas (Stanley, Peake & Buchheit 2013); tren lnRMSSD untuk memantau latihan (Plews dkk. 2012) |
| Bukan penanda vagal | denyut jantung (dipengaruhi simpatis dan vagal); ditampilkan hanya sebagai keterangan |

## 3. Penggabungan: grid 3 × 3

Dasar dua sumbu: *autonomic space* (Berntson dkk. 1991) dan model sirkumpleks (Russell 1980). Keterkaitan
korteks–jantung: Kubota dkk. 2001; Candia-Rivera dkk. 2022.

Tiap sumbu dibagi tiga zona dengan ambang **|z| < 0,6 = netral** (D-06): batas "sedang" pada skala
besaran Hopkins dkk. (2009). Besaran tiap sumbu ikut ditampilkan (trivial < 0,2 · kecil < 0,6 ·
sedang < 1,2 · besar < 2,0 · sangat besar < 4,0). Skala ini aslinya distandardisasi terhadap SD
antarsubjek; di sini diterapkan pada z robust terhadap R0 orang itu, jadi tetap diuji di validasi v0.5.

Grid 3 × 3 tetap **dua dimensi** (D-05): sumbunya dua, hanya dipotong menjadi 9 sel.

```
                 Y vagal ↑
        ┌──────────────────┬──────────────┬──────────────────┐
        │ Q2 RILEKS–PULIH  │ VAGAL NAIK   │ Q1 TERLIBAT–     │
        │                  │              │    TERATUR       │
  X ↓   ├──────────────────┼──────────────┼──────────────────┤   X ↑
        │ KORTEKS MELAMBAT │   NETRAL     │ AKTIVASI KORTIKAL│
        ├──────────────────┼──────────────┼──────────────────┤
        │ Q3 HIPOAKTIF     │ PENARIKAN    │ Q4 TERAKTIVASI–  │
        │                  │ VAGAL        │    TERBEBANI     │
        └──────────────────┴──────────────┴──────────────────┘
                 Y vagal ↓
```

| Kode | Label | X | Y | Arti singkat |
|---|---|---|---|---|
| `Q1` | Terlibat–teratur | ↑ | ↑ | korteks aktif dengan regulasi vagal terjaga (fokus tenang) |
| `Q2` | Rileks–pulih | ↓ | ↑ | korteks melambat, vagal naik (istirahat, napas lambat, pemulihan) |
| `Q3` | Hipoaktif | ↓ | ↓ | korteks melambat, vagal turun (lelah/mengantuk atau pemulihan awal) |
| `Q4` | Teraktivasi–terbebani | ↑ | ↓ | korteks aktif, penarikan vagal (stres, beban kerja, latihan) |
| `X_HIGH` | Aktivasi kortikal | ↑ | netral | perubahan hanya di korteks |
| `X_LOW` | Korteks melambat | ↓ | netral | perubahan hanya di korteks |
| `Y_HIGH` | Vagal naik | netral | ↑ | perubahan hanya di vagal |
| `Y_LOW` | Penarikan vagal | netral | ↓ | perubahan hanya di vagal |
| `NEUTRAL` | Netral | netral | netral | sekitar acuan R0 |
| `NO_DATA` | Data kurang | | | EEG bersih atau RR valid tidak cukup |

**Penanda tambahan untuk Q3:**
- θ/β naik (≥ ambang): **lelah/mengantuk** (Borghini dkk. 2014).
- Selain itu, bila fasenya pemulihan: **pemulihan awal** (vagal belum pulih; alfa naik pascalatihan).

## 4. Fase: protokol standar CorVa (D-08)

Dashboard live memandu peserta melalui lima fase dan mencatat awal tiap fase sebagai penanda
"CorVa: …" (`corva/protocol.py`, panel **Protokol CorVa**). Fase berjalan otomatis, ada instruksi di
layar peserta, pemandu napas visual dan nada, serta aba-aba suara untuk fase mata tertutup.

| # | Fase | Durasi | Mata | Napas | Harapan CorVa |
|---|---|---|---|---|---|
| 1 | Relaks (baseline) = **R0** | 5 menit | terbuka | spontan | Netral (acuan) |
| 2 | Mata terbuka · napas biasa | 3 menit | terbuka | spontan | Netral (kontrol) |
| 3 | Mata terbuka · napas dalam | 3 menit | terbuka | 6/menit | Q2 atau Vagal naik |
| 4 | Mata tertutup · napas biasa | 3 menit | tertutup | spontan | Korteks melambat atau Q2 |
| 5 | Mata tertutup · napas dalam | 3 menit | tertutup | 6/menit | Q2 |

Total 17 menit. Menit pertama tiap fase adalah **stabilisasi** dan tidak dianalisis.

**Dasar durasi:**
- **Baseline 5 menit** = standar rekaman HRV jangka pendek (Task Force 1996), atau 1 menit stabilisasi
  + 4 menit analisis (Bourdillon dkk. 2017).
- **Tiap blok 3 menit** = 1 menit stabilisasi + 2 menit analisis. RMSSD sah dengan jendela 2 menit
  (Bourdillon dkk. 2017; Muñoz dkk. 2015: 120 s hampir sempurna; Esco & Flatt 2014: 60 s cukup).
  EEG istirahat stabil dengan epoch ≥ 40 s (Gudmundsson dkk. 2007).
- **Napas dalam 6/menit** (~0,1 Hz) memberi efek HRV maksimal (Lehrer & Gevirtz 2014). Napas lambat
  menaikkan HRV vagal (Laborde dkk. 2022) dan alfa EEG (Zaccaro dkk. 2018). Frekuensi resonansi
  individual bisa berbeda (Shaffer & Meehan 2020; D-16).
- **Mata tertutup** menaikkan alfa dan menurunkan arousal dibanding mata terbuka (Barry dkk. 2007).

**Catatan urutan (D-15):** efek napas lambat masih terlihat segera sesudah sesi (Laborde dkk. 2022),
jadi blok 4 bisa terbawa efek blok 3. Menit stabilisasi mengurangi, tetapi tidak menghapus, efek ini.
Pada studi validasi, urutan sebaiknya diseimbangkan antarpeserta.

**Bacaan fase umum (Vagal Tank Theory).** Untuk protokol lain yang memuat aktivitas dan pemulihan,
`classify(phase=…)` tetap memberi bacaan kuadran per fase istirahat/aktivitas/pemulihan:

| | Istirahat | Aktivitas | Pemulihan |
|---|---|---|---|
| **Q1** | siaga tenang | keterlibatan teratur | pulih, sudah siaga |
| **Q2** | istirahat baik | keterlibatan rendah | pemulihan baik |
| **Q3** | mengantuk | kelelahan | pemulihan awal |
| **Q4** | tidak lazim saat istirahat, periksa | respons wajar (reaktivitas) | pemulihan tertunda |

## 5. Aturan label

Setiap label membawa **nama CorVa** dan **semua nama alternatif dari rujukan** (D-07), misalnya Q2 =
*Rileks–pulih*, juga disebut *Tenang* (label lama Research View), *relaxed* (Bird dkk. 2018), *pemulihan
vagal* (Laborde dkk. 2018), dan *rileks/tenang* (analogi Russell 1980). Daftar lengkapnya ada di
[`EVIDENCE.md`](EVIDENCE.md).


- **Per jendela 5 s:** titik di peta, untuk lintasan (deskriptif).
- **Per ruas:** label dari median X dan Y ruas, dengan proporsi okupansi sebagai keterangan.
- **Syarat:** ≥ 60 s RR valid (Esco & Flatt 2014) dan cukup jendela EEG bersih; bila tidak, `NO_DATA`.
- **Keyakinan:** proporsi jendela valid dan artefak ditampilkan di samping label.

## 6. Rencana validasi (ringkas, rincian di `ROADMAP.md`)

- Kondisi yang sudah diketahui:
  - mata terbuka vs tertutup;
  - aritmetika/PASAT, diharapkan Q4;
  - napas 6/menit, diharapkan Q2;
  - latihan lalu pemulihan, diharapkan lintasan Q4 → Q3 → Q2.
- Pembanding subjektif: skala arousal/afek, NASA-TLX, Karolinska Sleepiness Scale.
- Reliabilitas uji-ulang antarhari.

## 7. Batasan

- Label relatif terhadap R0 orang itu sendiri; deskriptif, bukan diagnosis.
- Gerak menimbulkan artefak Muse (AF7/AF8) dan memengaruhi napas, sehingga kedua sumbu terganggu.
- RMSSD saat latihan mendekati lantai, sehingga sumbu Y menyempit.
- Q3 secara konstruksi paling ambigu; selalu dibaca bersama penanda tambahan dan fase.
- β/α tidak khas untuk satu proses (stres, beban kerja, dan gerak bisa sama-sama menaikkannya).

## Rujukan

Daftar lengkap (penulis, tahun, judul, jurnal, DOI, temuan yang dipakai, status verifikasi, dan aturan
yang memakainya) ada di [`EVIDENCE.md`](EVIDENCE.md), dihasilkan dari [`references.json`](references.json).
Rujukan bertanda ⚠ perlu dicek ke naskah asli sebelum dikutip di manuskrip.
