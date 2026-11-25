@echo off
rem Bilgisayarda GERCEKTEN calisan Python'u bulur ve PY degiskenine yazar.
rem Her adayda Python'a 12345 yazdirilir; sadece cevap gelirse o secilir.
set "PY="
for /f "delims=" %%v in ('py -3.13 -c "print(12345)" 2^>nul') do if "%%v"=="12345" set "PY=py -3.13"
if not defined PY for /f "delims=" %%v in ('py -3.12 -c "print(12345)" 2^>nul') do if "%%v"=="12345" set "PY=py -3.12"
if not defined PY for /f "delims=" %%v in ('py -c "print(12345)" 2^>nul') do if "%%v"=="12345" set "PY=py"
if not defined PY for /f "delims=" %%v in ('python -c "print(12345)" 2^>nul') do if "%%v"=="12345" set "PY=python"
