@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo 请先运行 setup.bat
  exit /b 1
)
set "PATH=%~dp0ffmpeg;%PATH%"
".venv\Scripts\python.exe" pipeline.py %*
