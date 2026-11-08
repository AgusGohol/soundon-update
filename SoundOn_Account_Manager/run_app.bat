@echo off
cd /d "%~dp0"
rem Aplikasi dibuka tanpa jendela cmd (pythonw). Pesan galat dicatat di
rem %USERPROFILE%\SoundOnAccounts\app_log.txt
where pyw >nul 2>nul
if %errorlevel%==0 (
  start "" pyw -3 soundon_dashboard.py
  exit /b
)
where pythonw >nul 2>nul
if %errorlevel%==0 (
  start "" pythonw soundon_dashboard.py
  exit /b
)
rem Cadangan bila pythonw tidak ada: jalankan seperti dulu (dengan jendela cmd).
where py >nul 2>nul
if %errorlevel%==0 (py -3 soundon_dashboard.py) else (python soundon_dashboard.py)
rem 75 = aplikasi ditutup untuk pembaruan otomatis; jendela ini ditutup.
if %errorlevel%==75 exit
pause
