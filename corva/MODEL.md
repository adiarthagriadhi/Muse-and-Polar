# Model CASS-NV (CorVa Space), rancangan v0.1

Status: **sementara**. Nama label, ambang, dan aturan masih menunggu keputusan di
[`DECISIONS.md`](DECISIONS.md). Rujukan sudah dicek keberadaannya; sebagian baru dibaca abstraknya, jadi
angka spesifik perlu dicek ke naskah asli sebelum dikutip di manuskrip.

## 1. Sumbu X: kondisi kortikal (EEG Muse 2)

**Ukuran utama:** log(β/α) per kanal, rata-rata TP9, AF7, AF8, TP10, lalu diubah ke z robust terhadap R0
(median, 1,4826 × MAD). Ini sama dengan CASS sekarang.

| Dasar | Isi |
|---|---|
| Kelayakan Muse | Krigolson dkk. 2017 (ERP dengan Muse); Cannard, Wahbeh & Delorme 2021 (spektrum, frekuensi alfa individual, asimetri alfa frontal sebanding dengan sistem 64 kanal) |
| Alfa turun = arousal naik | Barry dkk. 2007: alfa berkorelasi negatif dengan konduktansi kulit; alfa rata-rata layak sebagai ukuran arousal istirahat |
| β/α sebagai indeks arousal | alfa frontal turun dan beta naik saat tugas kognitif (PASAT) dibanding istirahat; membedakan stres dari istirahat, kurang tajam untuk derajat stres |
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

Tiap sumbu dibagi tiga zona dengan ambang ±0,5 z (sama dengan ambang label lama Research View):

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

## 4. Konteks fase (Vagal Tank Theory)

| | Istirahat (R0) | Aktivitas | Pemulihan |
|---|---|---|---|
| **Q1** | siaga tenang | keterlibatan teratur | pulih, sudah siaga |
| **Q2** | istirahat baik | keterlibatan rendah | pemulihan baik |
| **Q3** | mengantuk | kelelahan | pemulihan awal |
| **Q4** | tidak lazim saat istirahat, periksa | respons wajar (reaktivitas) | pemulihan tertunda |

Fase diambil dari marker dashboard (usulan: *Baseline mulai* = istirahat, *Tugas mulai* = aktivitas,
*Pemulihan mulai* = pemulihan); keputusan D-05.

## 5. Aturan label

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

1. Barry RJ, Clarke AR, Johnstone SJ, Magee CA, Rushby JA (2007). EEG differences between eyes-closed and eyes-open resting conditions. *Clin Neurophysiol* 118(12):2765–2773.
2. Berntson GG, Cacioppo JT, Quigley KS (1991). Autonomic determinism: the modes of autonomic control, the doctrine of autonomic space, and the laws of autonomic constraint. *Psychol Rev* 98(4):459–487.
3. Bird JJ, Manso LJ, Ribeiro EP, Ekárt A, Faria DR (2018). A study on mental state classification using EEG-based brain-machine interface. *IEEE Intelligent Systems (IS)*.
4. Borghini G, Astolfi L, Vecchiato G, Mattia D, Babiloni F (2014). Measuring neurophysiological signals in aircraft pilots and car drivers for the assessment of mental workload, fatigue and drowsiness. *Neurosci Biobehav Rev* 44:58–75.
5. Candia-Rivera D, Catrambone V, Thayer JF, Gentili C, Valenza G (2022). Cardiac sympathetic-vagal activity initiates a functional brain–body response to emotional arousal. *PNAS* 119(21):e2119599119.
6. Cannard C, Wahbeh H, Delorme A (2021). Validating the wearable MUSE headset for EEG spectral analysis and frontal alpha asymmetry. *IEEE BIBM* 3603–3610.
7. Crabbe JB, Dishman RK (2004). Brain electrocortical activity during and after exercise: a quantitative synthesis. *Psychophysiology* 41(4):563–574.
8. Esco MR, Flatt AA (2014). Ultra-short-term heart rate variability indexes at rest and post-exercise in athletes: evaluating the agreement with accepted recommendations. *J Sports Sci Med* 13:535–541.
9. Klimesch W (1999). EEG alpha and theta oscillations reflect cognitive and memory performance: a review and analysis. *Brain Res Rev* 29(2–3):169–195.
10. Krigolson OE, Williams CC, Norton A, Hassall CD, Colino FL (2017). Choosing MUSE: validation of a low-cost, portable EEG system for ERP research. *Front Neurosci* 11:109.
11. Kubota Y, Sato W, Toichi M, dkk. (2001). Frontal midline theta rhythm is correlated with cardiac autonomic activities during the performance of an attention demanding meditation procedure. *Cogn Brain Res* 11(2):281–287.
12. Laborde S, Mosley E, Thayer JF (2017). Heart rate variability and cardiac vagal tone in psychophysiological research: recommendations for experiment planning, data analysis, and data reporting. *Front Psychol* 8:213.
13. Laborde S, Mosley E, Mertgen A (2018). Vagal Tank Theory: the three Rs of cardiac vagal control functioning, resting, reactivity, and recovery. *Front Neurosci* 12:458.
14. Muñoz ML, van Roon A, Riese H, dkk. (2015). Validity of (ultra-)short recordings for heart rate variability measurements. *PLoS ONE* 10(9):e0138921.
15. Plews DJ, Laursen PB, Kilding AE, Buchheit M (2012). Heart rate variability in elite triathletes, is variation in variability the key to effective training? A case comparison. *Eur J Appl Physiol*.
16. Pope AT, Bogart EH, Bartolome DS (1995). Biocybernetic system evaluates indices of operator engagement in automated task. *Biol Psychol* 40:187–195.
17. Russell JA (1980). A circumplex model of affect. *J Pers Soc Psychol* 39(6):1161–1178.
18. Shaffer F, Ginsberg JP (2017). An overview of heart rate variability metrics and norms. *Front Public Health* 5:258.
19. Stanley J, Peake JM, Buchheit M (2013). Cardiac parasympathetic reactivation following exercise: implications for training prescription. *Sports Med* 43(12):1259–1277.
20. Thayer JF, Lane RD (2000). A model of neurovisceral integration in emotion regulation and dysregulation. *J Affect Disord* 61:201–216.
21. Thayer JF, Hansen AL, Saus-Rose E, Johnsen BH (2009). Heart rate variability, prefrontal neural function, and cognitive performance: the neurovisceral integration perspective on self-regulation, adaptation, and health. *Ann Behav Med* 37(2):141–153.
22. Griadhi, Suadnyana & Wahyuni (2026). Validasi Muse 2 vs Polar H10 (studi B1). medRxiv preprint, doi:10.64898/2026.10.05.26364782.

Nama penulis yang ditulis "dkk." dan halaman Bird dkk. (2018) perlu dilengkapi dari naskah aslinya.
