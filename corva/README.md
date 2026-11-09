# CorVa Space · CASS-NV

**#NeuroVagal** · hub pengembangan varian baru CASS dengan interpretasi kualitatif kondisi kortikal × vagal.

| | |
|---|---|
| **Merek** | **CorVa Space**: *Cortico-Vagal Space* |
| **Nama teknis** | **CASS-NV**: *CASS Neurovisceral State Map* |
| **Tagar** | **#NeuroVagal** |
| **Status** | v0.3 (mesin + tampilan). Keputusan D-01 s.d. D-18 sudah diambil; ambang dan asumsi masih diuji di validasi v0.5. Lihat [`DECISIONS.md`](DECISIONS.md). |

## Arti nama

- **CorVa** = **Cor**tico-**Va**gal. Dua sumbu peta: kondisi **kortikal** dari EEG Muse 2 (X) dan kondisi
  **vagal** dari HRV Polar H10 (Y).
- **Space** merujuk pada *autonomic space* (Berntson, Cacioppo & Quigley, 1991). Kendali otonom tidak
  berada pada satu garis simpatis–parasimpatis, tetapi di ruang dua dimensi. Karena itu keadaan
  dipetakan di **bidang dua sumbu yang ortogonal**, bukan satu skor.
- **NV** = **Neurovisceral**, dari *model integrasi neuroviseral* (Thayer & Lane, 2000; Thayer dkk., 2009).
  Tonus vagal mencerminkan fungsi jaringan prefrontal yang mengatur kendali diri. Model ini menjadi
  jembatan teoretis antara korteks dan jantung, dan menjadi dasar penggabungan kedua sumbu.
- **#NeuroVagal** adalah tagar untuk komunikasi publik: *neuro* (otak/korteks) + *vagal* (saraf vagus,
  jantung).

## Apa bedanya dengan CASS yang sekarang

CASS (`cass_polar/`) sudah memetakan X = log(β/α) EEG dan Y = RMSSD RR Polar ke empat kuadran.
CASS-NV menambahkan:

1. **Zona netral** per sumbu (|z| < ambang), sehingga peta menjadi grid **3 × 3**: empat kuadran, empat
   zona "satu sumbu saja", dan satu zona netral.
2. **Label kualitatif** per sel, misalnya *Rileks–pulih* atau *Teraktivasi–terbebani*.
3. **Protokol standar** di dashboard, 17 menit: relaks (baseline), lalu mata terbuka/tertutup × napas
   biasa/dalam, dengan durasi dari rujukan. Fase dicatat otomatis sebagai penanda.
4. **Penanda tambahan** untuk sel yang ambigu (θ/β untuk Q3).
5. **Aturan keyakinan**: label per fase hanya keluar bila data cukup (≥ 60 s RR valid dan ≥ 40 s EEG bersih).

Model lengkap beserta rujukan ada di [`MODEL.md`](MODEL.md).

## Isi hub

| Berkas | Isi |
|---|---|
| [`MODEL.md`](MODEL.md) | model: sumbu, zona, label, fase, aturan, batasan |
| [`references.json`](references.json) | **bibliografi**, sumber kebenaran rujukan: DOI, temuan yang dipakai, status verifikasi |
| [`EVIDENCE.md`](EVIDENCE.md) | **peta bukti** aturan → rujukan, dihasilkan dari kode (`python -m corva.evidence_md`) |
| [`DECISIONS.md`](DECISIONS.md) | keputusan yang sudah diambil dan yang masih terbuka |
| [`ROADMAP.md`](ROADMAP.md) | tahapan pengembangan dan validasi |
| [`labels.py`](labels.py) | kode pemberi label (grid 3 × 3, ambang Hopkins, nama alternatif, penanda tambahan). |
| [`session.py`](session.py) | **mesin v0.2**: satu sesi rekaman → label per jendela dan per fase protokol, syarat data, perbandingan dengan harapan. `python -m corva.session <folder sesi> [--windows]` mencetak JSON. |
| [`view.py`](view.py), [`routes.py`](routes.py) | **tampilan v0.3**: halaman CorVa Space per sesi (`/corva/session/<id>`, `/corva` = sesi terbaru): peta 3 × 3, kartu label per fase, lintasan waktu, tabel, ekspor CSV (`/api/corva/export/<id>?level=phases\|windows`), cetak/PDF; JSON di `/api/corva/analysis/<id>`. Tombol **Tampilkan CorVa** ada di panel Protokol CorVa di dashboard. |
| [`protocol.py`](protocol.py) | protokol standar (fase, durasi, instruksi, harapan, rujukan); dipakai panel **Protokol CorVa** di dashboard (`musepolar/static/corva.js`) |
| `../tests/test_corva_labels.py` | uji aturan label |
| `../tests/test_corva_evidence.py` | uji keterlacakan: setiap aturan punya rujukan atau dinyatakan asumsi |
| `../tests/test_corva_protocol.py` | uji protokol: fase, durasi, penanda |
| `../tests/test_corva_view.py` | uji tampilan: halaman, JSON, CSV, rute, tombol dashboard |
| `../tests/test_corva_session.py` | uji mesin: penanda → fase → R0 → label per fase, syarat data, perbandingan dengan harapan (sesi sintetis 17 menit) |

## Prinsip

- **Bukti dulu.** Setiap aturan dibangun di atas rujukan ilmiah yang tercatat di
  [`references.json`](references.json) dan ditautkan di kode. Aturan tanpa rujukan ditandai
  *asumsi* dan wajib divalidasi. Tes otomatis menjaga keterlacakan ini (lihat D-00 di
  [`DECISIONS.md`](DECISIONS.md)).
- **Deskriptif, bukan diagnosis.** Label menggambarkan posisi relatif terhadap acuan R0 orang itu
  sendiri, bukan norma populasi.
- **Sumbu Y dari RR Polar (EKG)**, bukan PPG Muse. RMSSD ultra-singkat dari PPG dahi ditaksir berlebih
  (preprint B1).
- **Data peserta tidak masuk repo ini** (repo publik). Hub ini hanya berisi kode dan metode.
- Setiap perubahan metode dicatat di `DECISIONS.md` sebelum dikodekan.
