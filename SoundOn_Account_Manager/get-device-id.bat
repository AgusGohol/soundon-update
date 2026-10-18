@echo off
cd /d "%~dp0"
py -3 get_device_id.py 2>nul || python get_device_id.py
