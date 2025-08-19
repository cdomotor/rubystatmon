@echo off
REM ============================================================================
REM File: start_statmon_daemon.bat
REM Full path: C:\rubystatmon-fetched\rubystatmon\start_statmon_daemon.bat
REM ----------------------------------------------------------------------------
REM Starts the StatMon Python daemon.
REM - Place this file in your repo root: C:\rubystatmon-fetched\rubystatmon
REM - Double-click to run (foreground), or run with "bg" to spawn a new window.
REM - Any extra args after the mode are passed through to the daemon.
REM     e.g. start_statmon_daemon.bat bg --debug
REM Environment you can set (optional):
REM   STATMON_DB         : Path to SQLite DB (overrides daemon.toml)
REM   STATMON_CFG        : Path to daemon.toml (overrides default)
REM   STATMON_LOG        : Path to log file (overrides default)
REM   PYTHON_EXE         : Path to specific python.exe to use
REM ============================================================================

setlocal ENABLEDELAYEDEXPANSION

REM --- Locate repo root and move there ---
set "SCRIPT_DIR=%~dp0"
cd /d "%SCRIPT_DIR%"

REM --- Defaults ---
set "APP_DIR=%cd%"
set "CFG_PATH=%STATMON_CFG%"
if "%CFG_PATH%"=="" set "CFG_PATH=%APP_DIR%\daemon.toml"

set "LOG_PATH=%STATMON_LOG%"
if "%LOG_PATH%"=="" set "LOG_PATH=%APP_DIR%\logs\statmon_daemon.log"

REM If STATMON_DB not set, leave it empty; Python will use daemon.toml or default.

REM --- Choose Python interpreter (venv > explicit > PATH) ---
set "PY_EXE=%PYTHON_EXE%"
if exist "%APP_DIR%\venv\Scripts\python.exe" set "PY_EXE=%APP_DIR%\venv\Scripts\python.exe"
if "%PY_EXE%"=="" if exist "C:\Program Files\Python312\python.exe" set "PY_EXE=C:\Program Files\Python312\python.exe"
if "%PY_EXE%"=="" set "PY_EXE=python"

REM --- Ensure logs directory exists ---
if not exist "%APP_DIR%\logs" mkdir "%APP_DIR%\logs" >nul 2>&1

REM --- Parse mode (fg/bg). First arg "bg" = new console window ---
set "MODE=fg"
if /I "%~1"=="bg" (
  set "MODE=bg"
  shift
)

REM --- Forward the rest of the args to the daemon (e.g., --debug) ---
set "EXTRA_ARGS=%*"

REM --- Print summary ---
echo.
echo [StatMon] Starting daemon
echo   App Dir   : %APP_DIR%
echo   Python    : %PY_EXE%
echo   Config    : %CFG_PATH%
echo   Log file  : %LOG_PATH%
if not "%STATMON_DB%"=="" echo   STATMON_DB : %STATMON_DB%
if not "%EXTRA_ARGS%"=="" echo   Extra args : %EXTRA_ARGS%
echo.

REM --- Make Python flush immediately to console/logs ---
set "PYTHONUNBUFFERED=1"

REM --- Build command line ---
set "DAEMON_CMD="%PY_EXE%" -m statmon_daemon --log "%LOG_PATH%" --config "%CFG_PATH%" %EXTRA_ARGS%"

REM --- Launch ---
if /I "%MODE%"=="bg" (
  REM New console window (does not block this one)
  start "StatMon Daemon" cmd /c %DAEMON_CMD%
  if errorlevel 1 (
    echo [StatMon] Failed to start daemon (background). Errorlevel %errorlevel%.
    exit /b %errorlevel%
  )
  echo [StatMon] Daemon started in background. Check "%LOG_PATH%".
  exit /b 0
) else (
  REM Foreground (blocks current window; Ctrl+C to stop)
  %DAEMON_CMD%
  set "EXITCODE=%ERRORLEVEL%"
  echo.
  echo [StatMon] Daemon exited with code %EXITCODE%.
  exit /b %EXITCODE%
)
