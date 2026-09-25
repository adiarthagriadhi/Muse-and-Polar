# Muse & Polar — Dashboard Live Recording

Dashboard lokal di MacBook untuk **melihat secara live dan merekam** data dari:

| Perangkat | Data | Laju |
|---|---|---|
| **Muse 2** | EEG 4 kanal (TP9, AF7, AF8, TP10) | 256 Hz |
| | PPG (ambient, IR, merah) | 64 Hz |
| | Akselerometer & giroskop | 52 Hz |
| | Telemetri (baterai, suhu) | ± tiap beberapa detik |
| **Polar H10** | Detak jantung + interval RR | per detak |
| | EKG mentah | 130 Hz |
| | Akselerometer | 200 Hz |

Keduanya terhubung langsung lewat Bluetooth Low Energy (via [`bleak`](https://github.com/hbldh/bleak)),
jadi **tidak perlu** Muse Direct, BlueMuse, atau aplikasi Polar. Dashboard berjalan di browser
(`http://localhost:8765`) dan menampilkan:

- EEG 4 lajur (filter tampilan HPF 1 Hz + notch 50/60 Hz, skala bisa diatur) dan perkiraan kualitas sinyal per kanal
- Daya pita relatif (delta, theta, alfa, beta, gamma)
- PPG inframerah dan akselerometer Muse
- Detak jantung, EKG, takogram RR, serta HRV (RMSSD, SDNN, pNN50 dari 60 detik terakhir)
- Akselerometer Polar H10 dan **sinkronisasi Muse ↔ Polar** berbasis gerakan (lihat di bawah)
- Tombol rekam, penanda (marker) dengan teks bebas atau tombol cepat `1`–`5`
- Arahkan kursor ke grafik untuk membaca nilainya

## Kebutuhan

- macOS 12 atau lebih baru dengan Bluetooth
- Python 3.10+ (`python3 --version`; bisa dipasang dari python.org atau `brew install python`)

## Instalasi & menjalankan

```bash
git clone https://github.com/adiarthagriadhi/Muse-and-Polar.git
cd Muse-and-Polar
./run_mac.command
```

`run_mac.command` membuat `.venv`, memasang dependensi (hanya saat pertama kali), lalu membuka
dashboard. Opsi bisa ditambahkan di belakangnya, mis. `./run_mac.command --sim --autoconnect` atau
`./run_mac.command -v`. Hentikan dengan `Ctrl+C`.

Atau secara manual:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m musepolar
```

Browser akan terbuka otomatis di `http://localhost:8765`.

**Izin Bluetooth:** saat pertama kali, macOS akan meminta izin Bluetooth untuk aplikasi
Terminal (atau iTerm / VS Code). Izinkan. Jika tidak muncul atau sebelumnya ditolak, buka
*System Settings → Privacy & Security → Bluetooth* dan aktifkan untuk aplikasi terminal Anda,
lalu jalankan ulang.

### Coba tanpa perangkat

```bash
python -m musepolar --sim --autoconnect
```

Mode simulator menghasilkan data sintetis (EEG dengan ritme alfa + kedipan mata, EKG dengan
aritmia sinus respirasi) sehingga seluruh dashboard dan perekaman bisa dicoba.

## Cara pakai

1. Nyalakan Muse 2 (tekan tombol sampai LED berkedip) dan pasang Polar H10 di dada
   (**basahi elektroda strap**, H10 hanya menyala saat menyentuh kulit).
2. Pastikan kedua perangkat **tidak sedang terhubung** ke aplikasi lain (Muse app, Polar Beat/Flow,
   ponsel). BLE hanya bisa terhubung ke satu host sekaligus.
3. Klik **Hubungkan** pada kartu Muse 2 dan Polar H10. Status berubah
   *mencari… → menghubungkan… → streaming*. Jika koneksi terputus, aplikasi mencoba menghubungkan ulang
   secara otomatis.
4. Isi nama sesi/subjek lalu klik **Mulai rekam**. Tambahkan penanda kapan saja
   (ketik lalu Enter, atau tekan tombol angka `1`–`5`).
5. Klik **Stop rekam**. Lokasi folder ditampilkan di bawah tombol.

## Sinkronisasi Muse ↔ Polar

Kedua perangkat mengirim data lewat Bluetooth dengan latensi yang berbeda (±20–100 ms), jadi
kejadian yang sama bisa tercatat pada waktu yang sedikit berbeda. Penanda dari tombol
dashboard tidak memperbaiki ini, karena penanda itu dicatat oleh Mac, bukan oleh sensor.

Solusinya adalah **kejadian fisik bersama** yang terasa di kedua akselerometer:

1. Pasang kedua perangkat, klik **Mulai sinkronisasi (10 s)**.
2. Dalam 10 detik itu lakukan **3 loncatan kecil** dengan jeda ±2 detik (atau hentakan badan yang tegas).
3. Aplikasi mencocokkan pola lonjakan akselerometer Muse dan Polar (korelasi silang) lalu
   menampilkan selisihnya, mis. **+62 ms Muse − Polar**, beserta korelasi dan jumlah kejadian yang terdeteksi.
   Hasil dianggap *berhasil* bila korelasi ≥ 0,5 dan minimal 2 kejadian terdeteksi di kedua sensor.
4. Hasilnya otomatis disimpan di `session.json` (bagian `sync`) dan sebagai penanda
   `SYNC mulai` / `SYNC selesai (...)` di `marker.csv`.

Lakukan sinkronisasi **di awal dan di akhir** rekaman. Dari dua hasil itu, `session.json` juga
menghitung `sync_drift_ms_per_hour` (seberapa jauh selisih bergeser selama rekaman).

Cara memakainya saat analisis:

```python
import json, pandas as pd
d = "recordings/20260925_101500_subjek01"
meta = json.load(open(f"{d}/session.json"))
offset = [s for s in meta["sync"] if s["ok"]][0]["muse_minus_polar_s"]
ecg = pd.read_csv(f"{d}/polar_ecg.csv")
ecg["timestamp_aligned"] = ecg["timestamp"] + offset   # sekarang sejajar dengan waktu Muse
```

Arti tanda: `muse_minus_polar_s > 0` berarti kejadian yang sama muncul **lebih lambat** di
timestamp Muse. Resolusi dibatasi oleh akselerometer Muse (52 Hz); dengan interpolasi
akurasinya biasanya beberapa milidetik bila loncatannya tegas.

Opsi baris perintah (`python -m musepolar --help`):

| Opsi | Keterangan |
|---|---|
| `--autoconnect` | langsung menghubungkan kedua perangkat saat start |
| `--data-dir DIR` | folder rekaman (default `recordings/`) |
| `--port 8765` | port dashboard |
| `--muse-name`, `--polar-name` | awalan nama BLE (default `Muse`, `Polar H10`) |
| `--muse-address`, `--polar-address` | pilih perangkat tertentu jika ada beberapa (lihat `scan` di bawah) |
| `--no-ppg` | Muse hanya EEG (preset `p21`) |
| `--no-ecg` | matikan EKG Polar |
| `--no-polar-acc` | matikan akselerometer Polar (sinkronisasi tidak bisa dipakai) |
| `--no-browser` | jangan buka browser otomatis |
| `-v` | log detail |

Mencari nama/alamat perangkat di sekitar:

```bash
python -m musepolar.scan
```

Di macOS, "alamat" berupa UUID CoreBluetooth (bukan MAC) yang tetap sama untuk Mac yang sama.

## Format data rekaman

Setiap sesi disimpan di `recordings/<YYYYMMDD_HHMMSS>_<nama>/`:

| File | Kolom |
|---|---|
| `muse_eeg.csv` | `timestamp, TP9, AF7, AF8, TP10` (µV) |
| `muse_ppg.csv` | `timestamp, ambient, ir, red` (nilai mentah 24-bit) |
| `muse_acc.csv` | `timestamp, x, y, z` (g) |
| `muse_gyro.csv` | `timestamp, x, y, z` (°/s) |
| `muse_telemetry.csv` | `timestamp, battery_pct, fuel_gauge_mv, adc_mv, temperature_c` |
| `polar_hr.csv` | `timestamp, hr_bpm, contact` (1 = kontak kulit, 0 = tidak, −1 = tidak dilaporkan) |
| `polar_rr.csv` | `timestamp, rr_ms` |
| `polar_ecg.csv` | `timestamp, ecg_uV, sensor_ns` |
| `polar_acc.csv` | `timestamp, x, y, z, sensor_ns` (g) |
| `marker.csv` | `timestamp, label` |
| `session.json` | metadata: waktu mulai/selesai, perangkat, jumlah sampel, laju efektif, hasil sinkronisasi |

- `timestamp` = waktu Unix (detik, jam Mac) **per sampel**, sama untuk semua perangkat sehingga
  Muse dan Polar bisa langsung diselaraskan.
- Waktu sampel direkonstruksi dari laju sampling nominal dan nomor urut paket (paket yang hilang
  terdeteksi dan menggeser waktu), lalu dijangkarkan ke waktu terima Bluetooth. Latensi BLE ~20–100 ms
  masih ada; untuk menyelaraskan Muse dan Polar secara presisi gunakan [sinkronisasi](#sinkronisasi-muse--polar).
- `sensor_ns` = jam internal Polar H10 (nanodetik) untuk setiap sampel EKG/akselerometer, diambil dari
  timestamp frame PMD (timestamp sampel terakhir tiap frame, jarak antarsampel mengikuti jam strap).
  Jam ini tidak terkena jitter Bluetooth, jadi cocok untuk mengukur interval dengan presisi tinggi,
  mendeteksi paket hilang, dan mengoreksi drift. Nilai absolutnya bergantung pada jam strap
  (tidak disetel oleh aplikasi ini), jadi yang bermakna adalah **selisih** antar sampel.
  Sampel yang hilang juga terdeteksi dari jam ini dan menggeser `timestamp` dengan benar.
- Semua filter di dashboard hanya untuk tampilan — CSV berisi data **mentah**.

Contoh membaca di Python:

```python
import pandas as pd
d = "recordings/20260925_101500_subjek01"
eeg = pd.read_csv(f"{d}/muse_eeg.csv")
rr = pd.read_csv(f"{d}/polar_rr.csv")
markers = pd.read_csv(f"{d}/marker.csv")
```

## Pemecahan masalah

| Gejala | Solusi |
|---|---|
| Status *tidak ditemukan* | Pastikan perangkat menyala dan tidak terhubung ke ponsel/aplikasi lain. Matikan Bluetooth ponsel sementara. Jalankan `python -m musepolar.scan`. |
| Terminal tidak diminta izin Bluetooth / error `CBManagerStateUnauthorized` | Aktifkan izin Bluetooth untuk aplikasi terminal di *Privacy & Security → Bluetooth*. |
| Polar: HR ada tapi EKG kosong | Basahi elektroda, pastikan strap terpasang kencang. Coba lepas lalu pasang lagi modul H10. EKG hanya dikirim saat ada kontak kulit. |
| Muse: EEG *buruk*/*datar* | Rapikan rambut di belakang telinga (TP9/TP10), bersihkan sensor dahi, tunggu 1–2 menit sampai sinyal stabil. |
| Sinkronisasi *gagal* / *ragu* | Pastikan kedua akselerometer tampil di dashboard, lalu loncat lebih tegas dan beri jeda jelas antar-loncatan. Diam sebelum dan sesudah setiap loncatan. |
| Laju efektif jauh di bawah nominal | Dekatkan perangkat ke Mac, kurangi perangkat Bluetooth lain (mis. headphone), atau matikan PPG dengan `--no-ppg`. |

## Struktur kode

```
musepolar/
  server.py     server web (aiohttp) + websocket + opsi CLI
  hub.py        pusat data: batching ke browser, perekam, analisis
  muse.py       protokol BLE Muse 2 (decoder EEG/PPG/IMU/telemetri)
  polar.py      protokol BLE Polar H10 (HR/RR + EKG & akselerometer via PMD)
  ble.py        loop scan/connect/reconnect bersama (bleak)
  analysis.py   daya pita EEG, kualitas sinyal, HRV, estimasi selisih waktu (sinkronisasi)
  recorder.py   penulisan CSV + session.json
  simulator.py  perangkat sintetis untuk --sim
  static/       dashboard (HTML/CSS/JS tanpa dependensi eksternal, bisa offline)
tests/          uji decoder, analisis, perekam, dan end-to-end dengan simulator
```

Menjalankan tes: `pip install pytest && python -m pytest`
