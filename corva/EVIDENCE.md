# Peta bukti CASS-NV (CorVa Space)

<!-- Dihasilkan oleh `python -m corva.evidence_md` dari corva/labels.py (EVIDENCE) dan
     corva/references.json. Jangan disunting langsung. -->

Setiap aturan model menunjuk rujukannya, atau dinyatakan sebagai **asumsi** yang masih harus
divalidasi. Tes `tests/test_corva_evidence.py` gagal bila ada aturan tanpa rujukan yang tidak
dinyatakan asumsi, rujukan yang tidak dikenal, rujukan yang tidak dipakai, atau berkas ini tidak mutakhir.

## Aturan → rujukan

| Unsur | Rujukan | Dasar |
|---|---|---|
| Sumbu X: log(β/α) EEG Muse | Krigolson dkk. (2017); Cannard dkk. (2021); Barry dkk. (2007); Ehrhardt dkk. (2022); Borghini dkk. (2014); Crabbe & Dishman (2004) | spektrum Muse sahih; alfa turun dan beta naik saat arousal dan beban kognitif naik; dipakai rasio karena saat latihan daya absolut semua pita ikut naik |
| Sumbu Y: RMSSD RR Polar | Laborde dkk. (2017); Shaffer & Ginsberg (2017); Munoz dkk. (2015); Esco & Flatt (2014); Griadhi dkk. (2026) | RMSSD menandai aktivitas vagal jantung pada rekaman pendek; diambil dari RR EKG Polar karena RMSSD PPG dahi ditaksir berlebih |
| Dua sumbu ortogonal (bidang CorVa) | Berntson dkk. (1991); Russell (1980); Thayer & Lane (2000); Thayer dkk. (2009); Kubota dkk. (2001); Candia-Rivera dkk. (2022) | keadaan perlu dua sumbu ortogonal; integrasi neuroviseral menghubungkan fungsi prefrontal dan vagal |
| Y memakai lnRMSSD (D-10) | Plews dkk. (2012); Esco & Flatt (2014) | lnRMSSD (transformasi log) lazim untuk pemantauan atlet; calon keputusan D-10 |
| Alternatif X: β/(α+θ) (D-09) | Pope dkk. (1995) | indeks engagement beta/(alfa + theta); calon keputusan D-09 |
| Penamaan kualitatif wilayah | Russell (1980); Bird dkk. (2018) | penamaan wilayah pada ruang dua sumbu; kelas keadaan kualitatif dari Muse |
| Ambang zona netral |z| < 0,6 (D-06) | Hopkins dkk. (2009) | zona netral |z| < 0,6 = batas 'sedang' skala besaran Hopkins; diadaptasi dari SD antarsubjek ke z robust terhadap R0 orang itu, sehingga tetap diuji di validasi v0.5 |
| Konteks fase istirahat/aktivitas/pemulihan | Laborde dkk. (2018); Stanley dkk. (2013) | kendali vagal dibaca saat istirahat, reaktivitas, dan pemulihan; kinetika pemulihan pascalatihan |
| Syarat ≥ 60 s RR valid per ruas | Esco & Flatt (2014); Munoz dkk. (2015) | lnRMSSD 60 s sesuai dengan 5 menit; 120 s hampir sempurna |
| Penanda tambahan Q3 (θ/β, fase pemulihan) | Borghini dkk. (2014); Klimesch (1999); Stanley dkk. (2013) | theta bersama delta/alfa naik saat lelah; pemulihan vagal tertinggal setelah latihan |
| `Q1` Terlibat–teratur | Thayer dkk. (2009); Kubota dkk. (2001) | keterlibatan kortikal dengan regulasi vagal yang terjaga |
| `Q2` Rileks–pulih | Barry dkk. (2007); Laborde dkk. (2018); Stanley dkk. (2013) | alfa naik (arousal turun) bersama vagal naik (istirahat/pemulihan) |
| `Q3` Hipoaktif | Borghini dkk. (2014); Stanley dkk. (2013) | korteks melambat dengan vagal rendah: lelah, atau pemulihan awal |
| `Q4` Teraktivasi–terbebani | Ehrhardt dkk. (2022); Borghini dkk. (2014); Thayer & Lane (2000); Laborde dkk. (2017) | alfa frontal turun/beta naik saat beban, disertai penarikan vagal |
| `X_HIGH` Aktivasi kortikal | Barry dkk. (2007); Ehrhardt dkk. (2022) | aktivasi kortikal saja |
| `X_LOW` Korteks melambat | Barry dkk. (2007) | perlambatan kortikal saja |
| `Y_HIGH` Vagal naik | Laborde dkk. (2017) | kenaikan vagal saja |
| `Y_LOW` Penarikan vagal | Laborde dkk. (2017) | penarikan vagal saja |
| `NEUTRAL` Netral | Hopkins dkk. (2009) | perubahan di kedua sumbu paling banyak 'kecil' (|z| < 0,6) |
| `NO_DATA` Data kurang | Esco & Flatt (2014); Munoz dkk. (2015) | RR valid atau EEG bersih terlalu sedikit untuk label |
| Protokol: baseline relaks 5 menit | Task Force (1996); Bourdillon dkk. (2017); Laborde dkk. (2017) | rekaman HRV jangka pendek standar 5 menit = 1 menit stabilisasi + 4 menit analisis |
| Protokol: tiap blok 3 menit (1 stabilisasi + 2 analisis) | Bourdillon dkk. (2017); Munoz dkk. (2015); Esco & Flatt (2014); Gudmundsson dkk. (2007) | RMSSD sah dengan jendela 2 menit setelah 1 menit stabilisasi; EEG istirahat stabil dengan epoch ≥ 40 s |
| Protokol: mata terbuka vs tertutup | Barry dkk. (2007) | membuka mata menurunkan alfa dan menaikkan arousal; mata tertutup sebagai kondisi alfa tinggi |
| Protokol: napas dalam 6/menit | Lehrer & Gevirtz (2014); Laborde dkk. (2022); Zaccaro dkk. (2018); Shaffer & Meehan (2020) | 6 napas/menit (~0,1 Hz) menaikkan HRV vagal; alfa naik dan theta turun; resonansi individual bisa berbeda |
| Protokol: efek terbawa antarblok | Laborde dkk. (2022) | efek napas lambat masih terlihat segera sesudah sesi, sehingga urutan blok bisa terbawa ke blok berikutnya |

## Protokol standar

| Fase | Durasi | Stabilisasi | Mata | Napas | Harapan | Dasar harapan |
|---|---|---|---|---|---|---|
| Relaks (baseline) | 5 menit | 60 s | open | spontaneous | `NEUTRAL` Netral | acuan R0 |
| Mata terbuka · napas biasa | 3 menit | 60 s | open | spontaneous | `NEUTRAL` Netral | kontrol |
| Mata terbuka · napas dalam | 3 menit | 60 s | open | slow | `Q2` Rileks–pulih, `Y_HIGH` Vagal naik | Lehrer & Gevirtz (2014); Laborde dkk. (2022); Zaccaro dkk. (2018) |
| Mata tertutup · napas biasa | 3 menit | 60 s | closed | spontaneous | `X_LOW` Korteks melambat, `Q2` Rileks–pulih | Barry dkk. (2007) |
| Mata tertutup · napas dalam | 3 menit | 60 s | closed | slow | `Q2` Rileks–pulih | Barry dkk. (2007); Laborde dkk. (2022); Zaccaro dkk. (2018) |

## Nama alternatif per sel (D-07)

*istilah* = istilah sumber itu sendiri; *analogi* = wilayah model dua sumbu lain (Russell: arousal × valensi).

| Sel | Nama CorVa | Nama alternatif |
|---|---|---|
| `Q1` | Terlibat–teratur | Fokus (label lama Research View, istilah); concentrating (Bird dkk. (2018), istilah); terlibat dalam tugas (engagement) (Pope dkk. (1995), istilah); regulasi diri adaptif (Thayer dkk. (2009), istilah); siaga (alert) (Russell (1980), analogi) |
| `Q2` | Rileks–pulih | Tenang (label lama Research View, istilah); relaxed (Bird dkk. (2018), istilah); pemulihan vagal (Laborde dkk. (2018), istilah); rileks / tenang (relaxed, calm) (Russell (1980), analogi) |
| `Q3` | Hipoaktif | lelah / mengantuk (Borghini dkk. (2014), istilah); pemulihan awal (Stanley dkk. (2013), istilah); mengantuk / lesu (sleepy, tired) (Russell (1980), analogi) |
| `Q4` | Teraktivasi–terbebani | Teraktivasi (label lama Research View, istilah); stres (Ehrhardt dkk. (2022), istilah); beban kerja mental tinggi (Borghini dkk. (2014), istilah); disinhibisi regulasi (Thayer & Lane (2000), istilah); tegang (tense, distressed) (Russell (1980), analogi) |
| `X_HIGH` | Aktivasi kortikal | arousal kortikal naik (Barry dkk. (2007), istilah); concentrating (Bird dkk. (2018), istilah) |
| `X_LOW` | Korteks melambat | arousal kortikal turun (Barry dkk. (2007), istilah) |
| `Y_HIGH` | Vagal naik | tonus vagal meningkat (Laborde dkk. (2017), istilah) |
| `Y_LOW` | Penarikan vagal | penarikan vagal (vagal withdrawal) (Laborde dkk. (2017), istilah) |
| `NEUTRAL` | Netral | Indeterminan (label lama Research View, istilah); neutral (Bird dkk. (2018), istilah) |
| `NO_DATA` | Data kurang | - |

## Rujukan

Status: ✓ = DOI dan penulis sudah dicek; ⚠ = perlu dicek ke naskah asli sebelum dikutip.
*Dibaca* = bagian yang sudah dibaca untuk model ini.

- **[barry2007]** Barry RJ, Clarke AR, Johnstone SJ, Magee CA, Rushby JA (2007). EEG differences between eyes-closed and eyes-open resting conditions. *Clinical Neurophysiology 118(12):2765-2773*. doi:10.1016/j.clinph.2007.07.028
  ✓ · *dibaca:* abstract
  Temuan yang dipakai: Alfa rata-rata berkorelasi negatif dengan konduktansi kulit dan turun saat mata dibuka; alfa layak sebagai ukuran arousal istirahat.
  Dipakai untuk: Sumbu X: log(β/α) EEG Muse, `Q2` Rileks–pulih, `X_HIGH` Aktivasi kortikal, `X_LOW` Korteks melambat, Protokol: mata terbuka vs tertutup
- **[berntson1991]** Berntson GG, Cacioppo JT, Quigley KS (1991). Autonomic determinism: the modes of autonomic control, the doctrine of autonomic space, and the laws of autonomic constraint. *Psychological Review 98(4):459-487*. doi:10.1037/0033-295X.98.4.459
  ✓ · *dibaca:* abstract
  Temuan yang dipakai: Mode kendali otonom tidak berada pada satu kontinum simpatis-parasimpatis, tetapi di ruang dua dimensi (autonomic space).
  Dipakai untuk: Dua sumbu ortogonal (bidang CorVa)
- **[bird2018]** Bird JJ, Manso LJ, Ribeiro EP, Ekárt A, Faria DR, dkk. (daftar penulis belum lengkap) (2018). A study on mental state classification using EEG-based brain-machine interface. *IEEE International Conference on Intelligent Systems (IS)*. doi:10.1109/IS.2018.8710576
  ⚠ penulis belum lengkap · *dibaca:* abstract
  Temuan yang dipakai: Muse 4 kanal diklasifikasikan menjadi relaxed/neutral/concentrating (n = 5); preseden label kualitatif dari Muse.
  Dipakai untuk: Penamaan kualitatif wilayah
- **[borghini2014]** Borghini G, Astolfi L, Vecchiato G, Mattia D, Babiloni F (2014). Measuring neurophysiological signals in aircraft pilots and car drivers for the assessment of mental workload, fatigue and drowsiness. *Neuroscience and Biobehavioral Reviews 44:58-75*. doi:10.1016/j.neubiorev.2012.10.003
  ✓ · *dibaca:* abstract
  Temuan yang dipakai: Beban kerja tinggi: theta naik, alfa turun. Peralihan ke kelelahan: theta, delta, dan alfa naik.
  Dipakai untuk: Sumbu X: log(β/α) EEG Muse, Penanda tambahan Q3 (θ/β, fase pemulihan), `Q3` Hipoaktif, `Q4` Teraktivasi–terbebani
- **[bourdillon2017]** Bourdillon N, dkk. (daftar penulis belum lengkap) (2017). Minimal window duration for accurate HRV recording in athletes. *Frontiers in Neuroscience 11:456*. doi:10.3389/fnins.2017.00456
  ⚠ penulis belum lengkap · *dibaca:* abstract
  Temuan yang dipakai: RMSSD cukup dengan jendela analisis 2 menit (posisi berbaring); perlu 1 menit stabilisasi sebelumnya, jadi 3 menit = 1 + 2; ukuran ranah frekuensi perlu 5 menit = 1 + 4.
  Dipakai untuk: Protokol: baseline relaks 5 menit, Protokol: tiap blok 3 menit (1 stabilisasi + 2 analisis)
- **[candiarivera2022]** Candia-Rivera D, Catrambone V, Thayer JF, Gentili C, Valenza G (2022). Cardiac sympathetic-vagal activity initiates a functional brain-body response to emotional arousal. *Proceedings of the National Academy of Sciences 119(21):e2119599119*. doi:10.1073/pnas.2119599119
  ✓ · *dibaca:* abstract
  Temuan yang dipakai: Interaksi otak-jantung dua arah; aktivitas simpatis-vagal jantung memodulasi respons otak terhadap arousal.
  Dipakai untuk: Dua sumbu ortogonal (bidang CorVa)
- **[cannard2021]** Cannard C, Wahbeh H, Delorme A (2021). Validating the wearable MUSE headset for EEG spectral analysis and Frontal Alpha Asymmetry. *IEEE International Conference on Bioinformatics and Biomedicine (BIBM):3603-3610*. doi:10.1109/BIBM52615.2021.9669778
  ✓ · *dibaca:* abstract
  Temuan yang dipakai: Muse menangkap spektrum daya, frekuensi alfa individual, dan asimetri alfa frontal sebanding dengan BioSemi 64 kanal.
  Dipakai untuk: Sumbu X: log(β/α) EEG Muse
- **[crabbe2004]** Crabbe JB, Dishman RK (2004). Brain electrocortical activity during and after exercise: a quantitative synthesis. *Psychophysiology 41(4):563-574*. doi:10.1111/j.1469-8986.2004.00176.x
  ⚠ DOI belum terverifikasi · *dibaca:* abstract
  Temuan yang dipakai: Saat dan sesudah latihan daya absolut alfa naik, tetapi delta, theta, dan beta juga naik; tidak khas alfa.
  Dipakai untuk: Sumbu X: log(β/α) EEG Muse
- **[ehrhardt2022]** Ehrhardt NM, Fietz J, Kopf-Beck J, Kappelmann N, Brem AK (2022). Separating EEG correlates of stress: cognitive effort, time pressure, and social-evaluative threat. *European Journal of Neuroscience 55(9-10):2464-2473*. doi:10.1111/ejn.15211
  ✓ · *dibaca:* abstract
  Temuan yang dipakai: Saat PASAT dibanding istirahat, alfa frontal turun dan beta naik; daya EEG frontal membedakan stres dari istirahat, tetapi tidak membedakan derajat stres (n = 38).
  Dipakai untuk: Sumbu X: log(β/α) EEG Muse, `Q4` Teraktivasi–terbebani, `X_HIGH` Aktivasi kortikal
- **[esco2014]** Esco MR, Flatt AA (2014). Ultra-short-term heart rate variability indexes at rest and post-exercise in athletes: evaluating the agreement with accepted recommendations. *Journal of Sports Science and Medicine 13(3):535-541*. (tanpa DOI)
  ⚠ tanpa DOI · *dibaca:* abstract
  Temuan yang dipakai: lnRMSSD 60 s sesuai dengan rekaman 5 menit pada atlet, saat istirahat dan pascalatihan.
  Dipakai untuk: Sumbu Y: RMSSD RR Polar, Y memakai lnRMSSD (D-10), Syarat ≥ 60 s RR valid per ruas, `NO_DATA` Data kurang, Protokol: tiap blok 3 menit (1 stabilisasi + 2 analisis)
- **[griadhi2026]** Griadhi, Suadnyana, Wahyuni, dkk. (daftar penulis belum lengkap) (2026). Muse 2 versus Polar H10 validation study (B1). *medRxiv (preprint, not peer reviewed)*. doi:10.64898/2026.10.05.26364782
  ⚠ penulis belum lengkap · *dibaca:* full text
  Temuan yang dipakai: Denyut Muse 2 sesuai dengan Polar H10, tetapi RMSSD ultra-singkat (60 s) dari PPG dahi ditaksir berlebih.
  Dipakai untuk: Sumbu Y: RMSSD RR Polar
- **[gudmundsson2007]** Gudmundsson S, dkk. (daftar penulis belum lengkap) (2007). Reliability of quantitative EEG features. *Clinical Neurophysiology 118:2162-2171*. (tanpa DOI)
  ⚠ penulis belum lengkap, tanpa DOI · *dibaca:* abstract
  Temuan yang dipakai: Reliabilitas fitur EEG istirahat naik dengan panjang epoch sampai 40 s; 60 s tidak menambah reliabilitas.
  Dipakai untuk: Protokol: tiap blok 3 menit (1 stabilisasi + 2 analisis)
- **[hopkins2009]** Hopkins WG, Marshall SW, Batterham AM, Hanin J (2009). Progressive statistics for studies in sports medicine and exercise science. *Medicine and Science in Sports and Exercise 41(1):3-12*. doi:10.1249/MSS.0b013e31818cb278
  ⚠ DOI belum terverifikasi · *dibaca:* secondary summaries
  Temuan yang dipakai: Ambang besaran perbedaan terstandar: 0,2 kecil, 0,6 sedang, 1,2 besar, 2,0 sangat besar, 4,0 amat sangat besar (distandardisasi terhadap SD antarsubjek).
  Dipakai untuk: Ambang zona netral |z| < 0,6 (D-06), `NEUTRAL` Netral
- **[klimesch1999]** Klimesch W (1999). EEG alpha and theta oscillations reflect cognitive and memory performance: a review and analysis. *Brain Research Reviews 29(2-3):169-195*. doi:10.1016/S0165-0173(98)00056-3
  ✓ · *dibaca:* abstract
  Temuan yang dipakai: Theta terkait penyandian informasi baru; alfa atas terkait pencarian memori; pita alfa sebaiknya individual.
  Dipakai untuk: Penanda tambahan Q3 (θ/β, fase pemulihan)
- **[krigolson2017]** Krigolson OE, Williams CC, Norton A, Hassall CD, Colino FL, dkk. (daftar penulis belum lengkap) (2017). Choosing MUSE: validation of a low-cost, portable EEG system for ERP research. *Frontiers in Neuroscience 11:109*. doi:10.3389/fnins.2017.00109
  ⚠ penulis belum lengkap · *dibaca:* abstract
  Temuan yang dipakai: Muse (TP9, AF7, AF8, TP10) menangkap N200, P300, dan reward positivity pada 60 peserta.
  Dipakai untuk: Sumbu X: log(β/α) EEG Muse
- **[kubota2001]** Kubota Y, dkk. (daftar penulis belum lengkap) (2001). Frontal midline theta rhythm is correlated with cardiac autonomic activities during the performance of an attention demanding meditation procedure. *Cognitive Brain Research 11(2):281-287*. doi:10.1016/S0926-6410(00)00086-0
  ⚠ penulis belum lengkap · *dibaca:* abstract
  Temuan yang dipakai: Saat theta frontal-midline muncul pada meditasi atentif, indeks vagal dan simpatis berubah; korteks frontal medial terkait fungsi otonom jantung.
  Dipakai untuk: Dua sumbu ortogonal (bidang CorVa), `Q1` Terlibat–teratur
- **[laborde2017]** Laborde S, Mosley E, Thayer JF (2017). Heart rate variability and cardiac vagal tone in psychophysiological research: recommendations for experiment planning, data analysis, and data reporting. *Frontiers in Psychology 8:213*. doi:10.3389/fpsyg.2017.00213
  ✓ · *dibaca:* abstract and secondary summaries
  Temuan yang dipakai: RMSSD dianjurkan untuk rekaman pendek; LF/HF tidak dianjurkan sebagai keseimbangan simpatovagal; PPG bukan pengganti EKG saat bergerak.
  Dipakai untuk: Sumbu Y: RMSSD RR Polar, `Q4` Teraktivasi–terbebani, `Y_HIGH` Vagal naik, `Y_LOW` Penarikan vagal, Protokol: baseline relaks 5 menit
- **[laborde2018]** Laborde S, Mosley E, Mertgen A (2018). Vagal Tank Theory: the three Rs of cardiac vagal control functioning - resting, reactivity, and recovery. *Frontiers in Neuroscience 12:458*. doi:10.3389/fnins.2018.00458
  ✓ · *dibaca:* abstract
  Temuan yang dipakai: Kendali vagal dinilai pada tiga tingkat: istirahat, reaktivitas, pemulihan.
  Dipakai untuk: Konteks fase istirahat/aktivitas/pemulihan, `Q2` Rileks–pulih
- **[laborde2022]** Laborde S, Allen MS, Borges U, dkk. (daftar penulis belum lengkap) (2022). Effects of voluntary slow breathing on heart rate and heart rate variability: a systematic review and a meta-analysis. *Neuroscience and Biobehavioral Reviews 138:104711*. doi:10.1016/j.neubiorev.2022.104711
  ⚠ DOI belum terverifikasi, penulis belum lengkap · *dibaca:* abstract
  Temuan yang dipakai: Napas lambat sukarela menaikkan HRV vagal selama sesi, segera sesudah satu sesi, dan setelah intervensi (223 studi).
  Dipakai untuk: Protokol: napas dalam 6/menit, Protokol: efek terbawa antarblok
- **[lehrer2014]** Lehrer PM, Gevirtz R (2014). Heart rate variability biofeedback: how and why does it work?. *Frontiers in Psychology 5:756*. doi:10.3389/fpsyg.2014.00756
  ✓ · *dibaca:* abstract
  Temuan yang dipakai: Efek maksimal pada napas sekitar 0,1 Hz (6 napas/menit); napas spontan umumnya 0,15-0,4 Hz (9-24/menit); amplitudo osilasi denyut naik berlipat.
  Dipakai untuk: Protokol: napas dalam 6/menit
- **[munoz2015]** Munoz ML, van Roon A, Riese H, Thio C, Oostenbroek E, Westrik I, de Geus EJC, Gansevoort R, Lefrandt J, Nolte IM, Snieder H (2015). Validity of (ultra-)short recordings for heart rate variability measurements. *PLoS ONE 10(9):e0138921*. doi:10.1371/journal.pone.0138921
  ✓ · *dibaca:* abstract
  Temuan yang dipakai: RMSSD 10 s r = 0,85-0,86 terhadap 4-5 menit; tiga potongan 10 s r = 0,94; 120 s hampir sempurna (n = 3.387).
  Dipakai untuk: Sumbu Y: RMSSD RR Polar, Syarat ≥ 60 s RR valid per ruas, `NO_DATA` Data kurang, Protokol: tiap blok 3 menit (1 stabilisasi + 2 analisis)
- **[plews2012]** Plews DJ, Laursen PB, Kilding AE, Buchheit M (2012). Heart rate variability in elite triathletes, is variation in variability the key to effective training? A case comparison. *European Journal of Applied Physiology 112(11):3729-3741*. doi:10.1007/s00421-012-2354-4
  ✓ · *dibaca:* abstract
  Temuan yang dipakai: Rata-rata 7 hari lnRMSSD menurun pada atlet yang mengalami non-functional overreaching.
  Dipakai untuk: Y memakai lnRMSSD (D-10)
- **[pope1995]** Pope AT, Bogart EH, Bartolome DS (1995). Biocybernetic system evaluates indices of operator engagement in automated task. *Biological Psychology 40:187-195*. doi:10.1016/0301-0511(95)05116-3
  ⚠ DOI belum terverifikasi · *dibaca:* abstract
  Temuan yang dipakai: Di antara indeks yang diuji, beta/(alpha + theta) paling baik mencerminkan keterlibatan tugas.
  Dipakai untuk: Alternatif X: β/(α+θ) (D-09)
- **[russell1980]** Russell JA (1980). A circumplex model of affect. *Journal of Personality and Social Psychology 39(6):1161-1178*. doi:10.1037/h0077714
  ✓ · *dibaca:* abstract
  Temuan yang dipakai: Keadaan afektif dipetakan pada dua dimensi (valensi, arousal) dengan penamaan kualitatif per wilayah.
  Dipakai untuk: Dua sumbu ortogonal (bidang CorVa), Penamaan kualitatif wilayah
- **[shaffer2017]** Shaffer F, Ginsberg JP (2017). An overview of heart rate variability metrics and norms. *Frontiers in Public Health 5:258*. doi:10.3389/fpubh.2017.00258
  ✓ · *dibaca:* abstract
  Temuan yang dipakai: Norma HRV bergantung pada panjang rekaman, usia, dan jenis kelamin; norma 24 jam, jangka pendek, dan ultra-pendek tidak bisa dipertukarkan.
  Dipakai untuk: Sumbu Y: RMSSD RR Polar
- **[shaffer2020]** Shaffer F, Meehan ZM (2020). A practical guide to resonance frequency assessment for heart rate variability biofeedback. *Frontiers in Neuroscience 14:570400*. doi:10.3389/fnins.2020.570400
  ✓ · *dibaca:* abstract
  Temuan yang dipakai: Frekuensi resonansi tiap orang tidak selalu 6 napas/menit; bisa lebih rendah atau lebih tinggi.
  Dipakai untuk: Protokol: napas dalam 6/menit
- **[stanley2013]** Stanley J, Peake JM, Buchheit M (2013). Cardiac parasympathetic reactivation following exercise: implications for training prescription. *Sports Medicine 43(12):1259-1277*. doi:10.1007/s40279-013-0083-4
  ✓ · *dibaca:* abstract
  Temuan yang dipakai: Reaktivasi parasimpatis pascalatihan; pemulihan otonom penuh hingga 24 jam (intensitas rendah), 24-48 jam (ambang), dan >= 48 jam (intensitas tinggi).
  Dipakai untuk: Konteks fase istirahat/aktivitas/pemulihan, Penanda tambahan Q3 (θ/β, fase pemulihan), `Q2` Rileks–pulih, `Q3` Hipoaktif
- **[taskforce1996]** Task Force of the European Society of Cardiology and the North American Society of Pacing and Electrophysiology (1996). Heart rate variability: standards of measurement, physiological interpretation and clinical use. *Circulation 93(5):1043-1065*. doi:10.1161/01.CIR.93.5.1043
  ⚠ DOI belum terverifikasi · *dibaca:* secondary summaries
  Temuan yang dipakai: Rekaman jangka pendek standar adalah 5 menit; metode harus distandardisasi.
  Dipakai untuk: Protokol: baseline relaks 5 menit
- **[thayer2000]** Thayer JF, Lane RD (2000). A model of neurovisceral integration in emotion regulation and dysregulation. *Journal of Affective Disorders 61(3):201-216*. doi:10.1016/S0165-0327(00)00338-4
  ✓ · *dibaca:* abstract
  Temuan yang dipakai: Model integrasi neuroviseral: sistem otonom, atensi, dan afek dalam satu jaringan; kegagalan inhibisi memunculkan aktivasi simpatis relatif.
  Dipakai untuk: Dua sumbu ortogonal (bidang CorVa), `Q4` Teraktivasi–terbebani
- **[thayer2009]** Thayer JF, Hansen AL, Saus-Rose E, Johnsen BH (2009). Heart rate variability, prefrontal neural function, and cognitive performance: the neurovisceral integration perspective on self-regulation, adaptation, and health. *Annals of Behavioral Medicine 37(2):141-153*. doi:10.1007/s12160-009-9101-z
  ✓ · *dibaca:* abstract
  Temuan yang dipakai: HRV berkaitan dengan fungsi prefrontal dan kinerja eksekutif; mengubah HRV istirahat mengubah kinerja eksekutif.
  Dipakai untuk: Dua sumbu ortogonal (bidang CorVa), `Q1` Terlibat–teratur
- **[zaccaro2018]** Zaccaro A, dkk. (daftar penulis belum lengkap) (2018). How breath-control can change your life: a systematic review on psycho-physiological correlates of slow breathing. *Frontiers in Human Neuroscience 12:353*. doi:10.3389/fnhum.2018.00353
  ⚠ penulis belum lengkap · *dibaca:* abstract
  Temuan yang dipakai: Napas lambat (< 10/menit): EEG alfa naik dan theta turun; HRV dan RSA naik; rasa rileks naik.
  Dipakai untuk: Protokol: napas dalam 6/menit
