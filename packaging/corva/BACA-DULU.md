# CorVa Space · CASS-NV · #NeuroVagal

Paket mandiri untuk merekam dan menafsirkan kondisi **kortikal (EEG Muse 2) × vagal (RR Polar H10)** dengan
protokol standar CorVa. Paket ini **terpisah dari dashboard Muse-Polar yang lama**:

| | Dashboard lama | CorVa Space (paket ini) |
|---|---|---|
| Alamat | http://localhost:8765 | **http://localhost:8775** |
| Folder rekaman | `recordings/` | **`corva_recordings/`** (demo: `corva_demo/`) |
| Virtualenv | `.venv/` di folder lama | **`.venv/` di folder ini** |

Keduanya bisa dijalankan bersamaan tanpa saling mengganggu.

## Kebutuhan

- Python **3.11 atau lebih baru** (https://www.python.org/downloads/).
- Untuk merekam: Muse 2 dan Polar H10, Bluetooth aktif. Untuk mencoba tanpa alat: mode demo.
- Koneksi internet saat pertama kali dijalankan (memasang paket Python ke `.venv/`).

## Menjalankan

**macOS / Linux** (Terminal, di folder hasil ekstrak):

```bash
cd ~/Downloads/CorVa-Space-0.5.0      # sesuaikan dengan lokasi folder
./corva_demo.command                  # coba tanpa alat (data sintetis)
./corva_mac.command                   # rekam dengan Muse 2 + Polar H10
```

Di macOS bisa juga klik dua kali `corva_demo.command` / `corva_mac.command` di Finder. Bila macOS menolak
membuka berkas dari internet: klik kanan → **Open**, atau jalankan sekali
`xattr -dr com.apple.quarantine ~/Downloads/CorVa-Space-0.5.0`.

**Windows** (Command Prompt, di folder hasil ekstrak):

```bat
cd %USERPROFILE%\Downloads\CorVa-Space-0.5.0
corva_demo.bat
corva_windows.bat
```

Pertama kali, skrip membuat `.venv/` dan memasang paket (beberapa menit). Browser terbuka di
http://localhost:8775. Hentikan dengan **Ctrl+C** di terminal.

## Alur pemakaian

1. Sambungkan Muse 2 dan Polar H10 di dashboard (lihat `docs/panduan-dashboard-id.md`).
2. Isi **nama sesi** dengan kode peserta. Pakai kode yang **sama** untuk orang yang sama di setiap sesi
   (dipakai untuk perbandingan sebelum/sesudah dan uji-ulang).
3. Panel **Protokol CorVa** → **Mulai protokol standar** (± 18 menit): relaks 5 menit, lalu mata terbuka/tertutup ×
   napas biasa/dalam, masing-masing 3 menit. Setelah tiap fase peserta menilai kantuk (KSS 1–9) dan rileks (1–9).
4. Setelah selesai: **Tampilkan CorVa ↗** → halaman per layar: Kesimpulan · Perbandingan · Peta · Fase · Lintasan
   waktu · Tabel · Metode · Rujukan. Pindah halaman dengan tab, tombol Sebelumnya/Berikutnya, atau panah ←/→.
5. **Bandingkan dengan sesi sebelum** (mis. sebelum latihan meditasi) lewat pemilih di bagian atas halaman.
6. **Unduh / cetak**: CSV kesimpulan, fase, jendela, atau PDF.

## Validasi dan norma (untuk peneliti)

Jalankan pada folder rekaman Anda (simpan hasilnya di tempat privat, bukan di repo publik):

```bash
./.venv/bin/python -m corva.validate corva_recordings --out hasil_validasi --norms-out hasil_validasi/norma.json
./corva_mac.command --corva-norms hasil_validasi/norma.json     # tampilkan persentil kelompok acuan
```

Windows: `.venv\Scripts\python -m corva.validate corva_recordings --out hasil_validasi --norms-out hasil_validasi\norma.json`
lalu `corva_windows.bat --corva-norms hasil_validasi\norma.json`.

Analisis satu sesi ke JSON: `./.venv/bin/python -m corva.session corva_recordings/<folder sesi>`.

## Penting

- **Deskriptif, bukan diagnosis.** Label relatif terhadap baseline orang itu sendiri. Kesimpulan bertanda
  *diasumsikan* belum divalidasi; norma kelompok baru tersedia setelah data acuan terkumpul.
- **Versi 0.5 baru diuji dengan simulator dan data sintetis.** Anggap sesi pertama dengan alat nyata sebagai uji coba.
- **Data peserta bersifat pribadi.** Jangan unggah `corva_recordings/` ke tempat publik.
- Metode, keputusan, dan rujukan lengkap: `corva/MODEL.md`, `corva/DECISIONS.md`, `corva/EVIDENCE.md`.

Sumber: https://github.com/adiarthagriadhi/Muse-and-Polar · Lisensi: lihat `LICENSE`.
