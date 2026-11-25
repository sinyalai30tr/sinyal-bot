@echo off
cd /d "%~dp0"
if not exist "%~dp0requirements.txt" (
    echo.
    echo ==========================================================
    echo   DUR! Dosyalar henuz zip'ten cikarilmamis.
    echo   1. Bu pencereyi kapat.
    echo   2. ai-trend-studio.zip dosyasina SAG TIKLA
    echo   3. "Tumunu ayikla" sec, sonra "Ayikla" butonuna bas.
    echo   4. Acilan YENI klasorde bu dosyaya tekrar cift tikla.
    echo ==========================================================
    pause
    exit /b 1
)
call "%~dp0_python.bat"
if not defined PY (
    echo Python bulunamadi. Once "1-KURULUM.bat" dosyasina cift tikla.
    pause
    exit /b 1
)
echo Gunun haberleri taraniyor ve video hazirlaniyor. Birkac dakika surer...
echo.
%PY% run_daily.py
echo.
echo Bitti. Onaylamak icin "2-ONAY-MASASI.bat" dosyasina cift tikla.
pause
