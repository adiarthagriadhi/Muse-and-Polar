@echo off
rem CorVa Space (Windows): klik dua kali, atau jalankan corva_windows.bat di Command Prompt.
rem Terpisah dari dashboard lama: port 8775, rekaman di corva_recordings\, virtualenv di .venv\
cd /d "%~dp0"
if exist .venv\Scripts\python.exe goto deps
echo Membuat virtualenv .venv ...
py -3 -m venv .venv 2>nul || python -m venv .venv
if not exist .venv\Scripts\python.exe goto nopython
.venv\Scripts\python -m pip install --upgrade pip
:deps
if exist .venv\.req-installed goto run
.venv\Scripts\python -m pip install -r requirements.txt || goto fail
type nul > .venv\.req-installed
:run
.venv\Scripts\python -m musepolar --port 8775 --data-dir corva_recordings %*
goto end
:nopython
echo Python 3.11 atau lebih baru tidak ditemukan. Pasang dari https://www.python.org/downloads/ lalu coba lagi.
:fail
pause
:end
