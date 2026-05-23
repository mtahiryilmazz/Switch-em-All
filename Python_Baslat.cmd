@echo off
chcp 65001 >nul
cd /d "%~dp0"
set "TCL_LIBRARY=C:\Users\YILMAZ\AppData\Local\Programs\Python\Python311\tcl\tcl8.6"
set "TK_LIBRARY=C:\Users\YILMAZ\AppData\Local\Programs\Python\Python311\tcl\tk8.6"
"C:\Users\YILMAZ\AppData\Local\Programs\Python\Python311\python.exe" -c "import requests" >nul 2>nul
if errorlevel 1 (
    echo Gerekli Python modulleri kuruluyor...
    "C:\Users\YILMAZ\AppData\Local\Programs\Python\Python311\python.exe" -m pip install --no-warn-script-location -r "%~dp0requirements.txt"
    if errorlevel 1 (
        pause
        exit /b 1
    )
)
"C:\Users\YILMAZ\AppData\Local\Programs\Python\Python311\python.exe" "%~dp0Switch-em All.py"
if errorlevel 1 pause
