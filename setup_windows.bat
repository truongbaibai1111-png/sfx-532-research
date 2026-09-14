@echo off
setlocal EnableExtensions

rem Run the real setup in a child invocation so every line is captured to a log.
if /I not "%~1"=="__inner" (
  cd /d "%~dp0"
  set "LOG=%~dp0setup_log.txt"
  echo Running SFX 532 setup...
  echo Full output will be saved to: "%LOG%"
  echo.

  call "%~f0" __inner > "%LOG%" 2>&1
  set "RC=%ERRORLEVEL%"

  type "%LOG%"
  echo.
  echo ==================================================
  if "%RC%"=="0" (
    echo SETUP FINISHED SUCCESSFULLY.
  ) else (
    echo SETUP FAILED. Error code: %RC%
    echo Please send setup_log.txt or a screenshot of this window.
  )
  echo Log file: "%LOG%"
  echo ==================================================
  echo.
  pause
  exit /b %RC%
)

cd /d "%~dp0"

echo ==================================================
echo SFX 532 Research - Windows setup
echo ==================================================
echo Working directory: %CD%
echo.

echo [1/6] Checking Python...
where python
if errorlevel 1 (
  echo ERROR: Python is not available in PATH.
  exit /b 1
)
python --version
if errorlevel 1 exit /b 1

echo.
echo [2/6] Checking FFmpeg...
where ffmpeg
if errorlevel 1 (
  echo ERROR: FFmpeg is not available in PATH.
  echo Install FFmpeg first, then run this file again.
  exit /b 2
)
ffmpeg -version | findstr /B /C:"ffmpeg version"

echo.
echo [3/6] Checking FFprobe...
where ffprobe
if errorlevel 1 (
  echo ERROR: FFprobe is not available in PATH.
  exit /b 3
)
ffprobe -version | findstr /B /C:"ffprobe version"

echo.
echo [4/6] Creating Python virtual environment...
if not exist .venv\Scripts\python.exe (
  python -m venv .venv
  if errorlevel 1 (
    echo ERROR: Could not create .venv
    exit /b 4
  )
) else (
  echo Existing .venv found - reusing it.
)

call .venv\Scripts\activate.bat
if errorlevel 1 (
  echo ERROR: Could not activate .venv
  exit /b 5
)

echo.
echo [5/6] Installing Python dependencies...
python -m pip install --upgrade pip
if errorlevel 1 exit /b 6
python -m pip install -r requirements.txt
if errorlevel 1 exit /b 7

echo.
echo [6/6] Running core self-test...
python scripts\self_test.py
if errorlevel 1 (
  echo ERROR: Core self-test failed.
  exit /b 8
)

echo.
echo ==================================================
echo ALL CORE CHECKS PASSED
echo ==================================================
echo SETUP COMPLETE.
echo Next: copy ONE test video into data\raw_videos\
echo Then run: python scripts\scan_videos.py
exit /b 0
