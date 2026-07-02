@echo off
REM ATLAS masaustu EXE derleme
REM Cikti: dist\ATLAS.exe

python -m PyInstaller ^
    --onefile ^
    --windowed ^
    --name ATLAS ^
    --collect-all customtkinter ^
    gui.py

echo.
echo Derleme tamamlandi: dist\ATLAS.exe
pause
