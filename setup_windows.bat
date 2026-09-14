@echo off
setlocal EnableExtensions EnableDelayedExpansion
chcp 65001 >nul
set "PYTHONUTF8=1"
cd /d "%~dp0"
set "LOG=%~dp0setup_log.txt"

if /I "%~1"=="__inner" goto :inner

echo Running SFX 532 setup...
echo Full output will be saved to: "%LOG%"
echo.

call "%~f0" __inner > "%LOG%" 2>&1
set "RC=%ERRORLEVEL%"

echo.
echo ================= SETUP OUTPUT =================
type "%LOG%"
echo ================= END OUTPUT ===================
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

:inner
cd /d "%~dp0"

echo ==================================================
echo SFX 532 Research - Windows setup
echo ==================================================
echo Working directory: %CD%
echo.

echo [1/6] Selecting Python 3.11...
set "PYEXE="

where py >nul 2>nul
if !errorlevel! equ 0 (
  for /f "usebackq delims=" %%P in (`py -3.11 -c "import sys; print(sys.executable)" 2^>nul`) do (
    if not defined PYEXE set "PYEXE=%%P"
  )
)

if not defined PYEXE (
  for /f "delims=" %%P in ('where python 2^>nul') do (
    if not defined PYEXE (
      "%%P" -c "import sys; raise SystemExit(0 if sys.version_info[:2] == (3,11) else 1)" >nul 2>&1
      if !errorlevel! equ 0 set "PYEXE=%%P"
    )
  )
)

if not defined PYEXE (
  echo ERROR: Python 3.11 was not found.
  echo Install Python 3.11 x64 and run setup again.
  exit /b 1
)

echo Selected Python: !PYEXE!
"!PYEXE!" --version
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
if errorlevel 1 (
  echo ERROR: FFmpeg command was found but did not run correctly.
  exit /b 2
)

echo.
echo [3/6] Checking FFprobe...
where ffprobe
if errorlevel 1 (
  echo ERROR: FFprobe is not available in PATH.
  exit /b 3
)
ffprobe -version | findstr /B /C:"ffprobe version"
if errorlevel 1 (
  echo ERROR: FFprobe command was found but did not run correctly.
  exit /b 3
)

echo.
echo [4/6] Creating Python 3.11 virtual environment...
if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" -c "import sys; raise SystemExit(0 if sys.version_info[:2] == (3,11) else 1)" >nul 2>&1
  if !errorlevel! neq 0 (
    echo Existing .venv is not Python 3.11 - rebuilding it.
    rmdir /s /q ".venv"
    if exist ".venv" (
      echo ERROR: Could not remove old .venv.
      exit /b 4
    )
  )
)

if not exist ".venv\Scripts\python.exe" (
  "!PYEXE!" -m venv .venv
  if errorlevel 1 (
    echo ERROR: Could not create .venv with Python 3.11.
    exit /b 4
  )
) else (
  echo Existing Python 3.11 .venv found - reusing it.
)

call ".venv\Scripts\activate.bat"
if errorlevel 1 (
  echo ERROR: Could not activate .venv
  exit /b 5
)
python --version

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
