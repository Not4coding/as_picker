@echo off
cd /d "%~dp0"
where python >nul 2>nul
if errorlevel 1 (
  echo 需要先安装 Python 3.10+ 并勾选 Add to PATH
  echo https://www.python.org/downloads/
  exit /b 1
)
python setup.py
if errorlevel 1 exit /b 1
echo.
echo 可选：把微软雅黑 msyh.ttc / msyhbd.ttc 拷到 fonts\
echo 可选：口播 mp3 放到 data\source\Sample\Music\
pause
