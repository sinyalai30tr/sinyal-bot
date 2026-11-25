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
echo ==============================================
echo   AI Trend Studyosu - KURULUM (bir kez yapilir)
echo ==============================================
echo.
echo [1/2] Python araniyor...
call "%~dp0_python.bat"
if not defined PY (
    echo Python bulunamadi, kuruluyor...
    py install 3.13
    call "%~dp0_python.bat"
)
if not defined PY (
    echo.
    echo HATA: Python kurulamadi. python.org adresinden Python'u kurup tekrar dene.
    pause
    exit /b 1
)
%PY% --version
echo.
echo [2/2] Gerekli paketler kuruluyor. Birkac dakika surebilir, pencereyi kapatma...
%PY% -m pip install --upgrade pip >nul 2>&1
%PY% -m pip install -r requirements.txt
if errorlevel 1 (
    echo.
    echo HATA: Paketler kurulamadi. Bu pencerenin ekran goruntusunu gonder.
    pause
    exit /b 1
)
if not exist .env copy .env.example .env >nul
echo.
echo ==============================================
echo   KURULUM TAMAM!
echo   Simdi "2-ONAY-MASASI.bat" dosyasina cift tikla.
echo ==============================================
pause
