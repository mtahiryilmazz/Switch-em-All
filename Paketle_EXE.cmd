@echo off
chcp 65001 >nul
cd /d "%~dp0"

set "PYTHON_EXE=C:\Users\YILMAZ\AppData\Local\Programs\Python\Python311\python.exe"
set "TCL_LIBRARY=C:\Users\YILMAZ\AppData\Local\Programs\Python\Python311\tcl\tcl8.6"
set "TK_LIBRARY=C:\Users\YILMAZ\AppData\Local\Programs\Python\Python311\tcl\tk8.6"

echo Python modulleri kontrol ediliyor...
"%PYTHON_EXE%" -m pip install --no-warn-script-location -r "%~dp0requirements.txt"
if errorlevel 1 goto fail

"%PYTHON_EXE%" -c "import PyInstaller" >nul 2>nul
if errorlevel 1 (
    echo PyInstaller kuruluyor...
    "%PYTHON_EXE%" -m pip install --no-warn-script-location pyinstaller
    if errorlevel 1 goto fail
)

echo EXE paketleniyor...
"%PYTHON_EXE%" -m PyInstaller --noconfirm --clean --onefile --windowed --name "Switch-em All" "%~dp0Switch-em All.py"
if errorlevel 1 goto fail

if not exist "%~dp0dist\config" mkdir "%~dp0dist\config"
xcopy "%~dp0config" "%~dp0dist\config" /E /I /Y >nul
if not exist "%~dp0dist\downloads" mkdir "%~dp0dist\downloads"
if not exist "%~dp0dist\logs" mkdir "%~dp0dist\logs"

echo.
echo Paket hazir:
echo %~dp0dist\Switch-em All.exe
echo.
pause
exit /b 0

:fail
echo.
echo Paketleme basarisiz oldu.
pause
exit /b 1
