# Muse 2 Research View

Penampil riset **offline** per sesi untuk rekaman yang dibuat oleh dashboard live
[`musepolar`](../README.md). Aplikasi ini tidak merekam, bukan GUI klien, dan bukan pengganti HRV Polar H10.

Folder `research/` berdiri sendiri. Ia punya dependensi dan virtualenv sendiri (`research/.venv`),
tidak mengimpor paket `musepolar`, dan yang dibaca hanya file CSV hasil rekamannya.

## Menjalankan (macOS)

```bash
cd Muse-and-Polar/research
./run_mac.command
```

Saat pertama kali dijalankan, skrip membuat `research/.venv` dan memasang `requirements.txt`, lalu
membuka `http://localhost:8501`. Untuk ikon di Desktop, klik dua kali `Pasang Muse2 Research.command`.

Manual:

```bash
cd research
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
PYTHONPATH=src streamlit run app/streamlit_app.py
```

Front-end lain (semuanya memakai pipeline yang sama):

| Perintah (dari `research/`, dengan `PYTHONPATH=src`) | Tampilan |
|---|---|
| `streamlit run app/streamlit_app.py` | lengkap: tabel ruas, PSD, unduh PNG/PDF/Word |
| `streamlit run app/dashboard_riset.py --server.port 8502` | satu layar ringkas + Kruskal–Wallis |
| `uvicorn app.api:app --port 8000` | FastAPI, buka `http://127.0.0.1:8000/` |
| `python app/tk_riset.py` | desktop Tk (bisa juga dari Jupyter) |
| `python app/nicegui_dashboard.py` | NiceGUI (`pip install nicegui`) |

## Data masukan

Folder default adalah `recordings/` di akar repo, yaitu tempat `musepolar` menyimpan sesi.
Folder lain bisa dipilih di aplikasi, atau diatur lewat variabel lingkungan `MUSE2_RECORDINGS`.
Bisa juga mengunggah ZIP berisi satu atau beberapa folder sesi.

Satu sesi = satu folder `recordings/<YYYYMMDD_HHMMSS>_<nama>/`:

| File musepolar | Dipakai sebagai |
|---|---|
| `muse_eeg.csv` (`timestamp, TP9, AF7, AF8, TP10`) | EEG, **wajib** |
| `muse_ppg.csv` (`timestamp, ambient, ir, red`) | `PPG1`/`PPG2`/`PPG3`; denyut & PRV dari `ir` (= PPG2). Opsional: sesi `--no-ppg` tetap bisa dibuka, PRV tampil *n/a* |
| `marker.csv` (`timestamp, label`) | waktu penanda ditampilkan sebagai saran *Titik* (penanda `SYNC …` diabaikan) |
| `session.json` | nama sesi (`name`), catatan (`note`), waktu mulai |

- Waktu (`time_s`) dihitung dari sampel EEG pertama. PPG dan penanda memakai titik nol yang sama,
  sehingga tetap sejajar (semua `timestamp` musepolar memakai jam Mac yang sama).
- Status **EEG/PPG** dihitung dari laju sampel efektif dibanding laju nominal (256/64 Hz):
  `VALID` ≥ 90 %, `WARNING` ≥ 50 %, selain itu `INVALID`.
- File Polar (`polar_*.csv`) belum dipakai. PRV di sini berasal dari dahi (PPG Muse), bukan HRV Polar.

## Isi paket

- `src/muse2_pipeline/`: baca sesi (`io.py`), filter EEG & daya pita, peta, PRV 09-lite, statistik ruas
- `app/`: front-end di atas
- `tests/`: uji pembacaan format musepolar (`python -m pytest research/tests`)
