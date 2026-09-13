@echo off
setlocal

echo ==================================================
echo SFX 532 Research - Windows setup
echo ==================================================

where python >nul 2>nul
if errorlevel 1 (
  echo ERROR: Python is not available in PATH.
  exit /b 1
)

where ffmpeg >nul 2>nul
if errorlevel 1 (
  echo ERROR: FFmpeg is not available in PATH.
  echo Install FFmpeg first, then run this file again.
  exit /b 1
)

where ffprobe >nul 2>nul
if errorlevel 1 (
  echo ERROR: FFprobe is not available in PATH.
  exit /b 1
)

if not exist .venv (
  python -m venv .venv
  if errorlevel 1 exit /b 1
)

call .venv\Scripts\activate.bat
python -m pip install --upgrade pip
pip install -r requirements.txt
if errorlevel 1 exit /b 1

python scripts\self_test.py
if errorlevel 1 exit /b 1

echo.
echo SETUP COMPLETE.
echo Next: copy ONE test video into data\raw_videos\
echo Then run: python scripts\scan_videos.py
endlocal
