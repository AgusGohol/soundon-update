@echo off
cd /d "%~dp0"
where py >nul 2>nul
if %errorlevel%==0 (py -3 soundon_dashboard.py) else (python soundon_dashboard.py)
rem 75 = aplikasi ditutup untuk pembaruan otomatis; jendela ini ditutup.
if %errorlevel%==75 exit
pause
