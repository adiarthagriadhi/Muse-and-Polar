# Front-end lama (legacy)

Lima tampilan dari paket asli *muse2-research-app*, sudah disesuaikan untuk membaca rekaman musepolar
tetapi **memakai metode analisis lama** (jendela utuh dibuang bila ada artefak, klasifikasi dengan selisih
mentah, uji tanpa koreksi Holm). Disimpan untuk perbandingan; aplikasi utama sekarang `../app/server.py`.

Kode asli yang belum diubah sama sekali tersimpan di riwayat git, commit `224f88e`
(`git show 224f88e --stat`, atau `git checkout 224f88e -- research` untuk mengambilnya kembali).

Menjalankan (dari folder `research/`, setelah `pip install -r requirements.txt -r legacy/requirements.txt`):

| Perintah (dengan `PYTHONPATH=src`) | Tampilan |
|---|---|
| `streamlit run legacy/streamlit_app.py` | lengkap + unduh PNG/PDF/Word |
| `streamlit run legacy/dashboard_riset.py --server.port 8502` | satu layar ringkas |
| `uvicorn legacy.api:app --port 8000` | FastAPI + HTML |
| `python legacy/tk_riset.py` | desktop Tk |
| `python legacy/nicegui_dashboard.py` | NiceGUI (`pip install nicegui`) |
