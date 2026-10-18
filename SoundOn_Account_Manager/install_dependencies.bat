@echo off
cd /d "%~dp0"
py -3 -m pip install --upgrade playwright cryptography
if errorlevel 1 python -m pip install --upgrade playwright cryptography
pause
