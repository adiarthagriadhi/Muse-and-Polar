# Muse 2 Research View (standalone)

Penampil riset per sampel. Bukan GUI klien dan bukan pengganti Polar H10.

## Instalasi (env muse2-env)

```bash
source ~/muse2-env/bin/activate
pip install streamlit
cd muse2-research-app
PYTHONPATH=src streamlit run app/streamlit_app.py
```

Atau salin folder ini ke `~/muse2-research/app-standalone/`.

## Data

- Folder lokal default: `~/muse2-research/data/raw/trials/Pxx_Trial/experiment/{EEG,PPG}_raw.csv`
- Atau unggah ZIP dengan struktur yang sama

## Isi paket

- `src/muse2_pipeline/` — load, filter EEG, bandpower, peta, 09-lite PRV, statistik ruas
- `app/streamlit_app.py` — GUI browser
