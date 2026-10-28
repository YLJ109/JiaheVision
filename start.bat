@echo off
cd /d "%~dp0"
if exist ".buildenv\Scripts\python.exe" (
  ".buildenv\Scripts\python.exe" main.py
) else (
  python main.py
)
if errorlevel 1 pause
