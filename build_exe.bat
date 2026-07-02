@echo off
REM KieronTradeEngine masaustu EXE derleme
REM Cikti: dist\KieronTradeEngine.exe

python -m PyInstaller ^
    --onefile ^
    --windowed ^
    --name KieronTradeEngine ^
    --collect-all customtkinter ^
    gui.py

echo.
echo Derleme tamamlandi: dist\KieronTradeEngine.exe
pause
