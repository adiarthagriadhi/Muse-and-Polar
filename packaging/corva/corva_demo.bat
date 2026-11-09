@echo off
rem CorVa Space versi demo (tanpa Muse/Polar).
cd /d "%~dp0"
call corva_windows.bat --demo --data-dir corva_demo %*
