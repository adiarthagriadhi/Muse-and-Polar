# CorVa Space · CASS-NV

**#NeuroVagal** · hub pengembangan varian baru CASS dengan interpretasi kualitatif kondisi kortikal × vagal.

| | |
|---|---|
| **Merek** | **CorVa Space**: *Cortico-Vagal Space* |
| **Nama teknis** | **CASS-NV**: *CASS Neurovisceral State Map* |
| **Tagar** | **#NeuroVagal** |
| **Status** | Tahap rancangan (v0.1). Model dan label masih **sementara**; lihat [`DECISIONS.md`](DECISIONS.md). |

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
3. **Konteks fase** istirahat → aktivitas → pemulihan (*Vagal Tank Theory*, Laborde dkk., 2018). Kuadran
   yang sama dibaca berbeda tergantung fasenya.
4. **Penanda tambahan** untuk sel yang ambigu (θ/β untuk Q3).
5. **Aturan keyakinan**: label per ruas hanya keluar bila data cukup (≥ 60 s RR valid).

Model lengkap beserta rujukan ada di [`MODEL.md`](MODEL.md).

## Isi hub

| Berkas | Isi |
|---|---|
| [`MODEL.md`](MODEL.md) | model: sumbu, zona, label, fase, aturan, batasan, rujukan |
| [`DECISIONS.md`](DECISIONS.md) | keputusan yang sudah diambil dan yang masih terbuka |
| [`ROADMAP.md`](ROADMAP.md) | tahapan pengembangan dan validasi |
| [`labels.py`](labels.py) | kode pemberi label (grid 3 × 3, fase, penanda tambahan). Belum tersambung ke tampilan. |
| `../tests/test_corva_labels.py` | uji aturan label |

## Prinsip

- **Deskriptif, bukan diagnosis.** Label menggambarkan posisi relatif terhadap acuan R0 orang itu
  sendiri, bukan norma populasi.
- **Sumbu Y dari RR Polar (EKG)**, bukan PPG Muse. RMSSD ultra-singkat dari PPG dahi ditaksir berlebih
  (preprint B1).
- **Data peserta tidak masuk repo ini** (repo publik). Hub ini hanya berisi kode dan metode.
- Setiap perubahan metode dicatat di `DECISIONS.md` sebelum dikodekan.
