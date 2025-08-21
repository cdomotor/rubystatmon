@echo off
REM ============================================================================
REM File: start_statmon_daemon.bat
REM Full path: C:\rubystatmon-fetched\rubystatmon\start_statmon_daemon.bat
REM Starts the StatMon Python daemon. Use "bg" as first arg to open a new window.
REM Extra args after the mode are passed to the daemon (e.g., --debug).
REM Env (optional): STATMON_DB, STATMON_CFG, STATMON_LOG, PYTHON_EXE
REM ============================================================================
setlocal enableextensions disabledelayedexpansion

REM --- Repo root ---
set "SCRIPT_DIR=%~dp0"
cd /d "%SCRIPT_DIR%"

REM --- Defaults ---
set "APP_DIR=%cd%"
set "CFG_PATH=%STATMON_CFG%"
if "%CFG_PATH%"=="" set "CFG_PATH=%APP_DIR%\daemon.toml"

set "LOG_PATH=%STATMON_LOG%"
if "%LOG_PATH%"=="" set "LOG_PATH=%APP_DIR%\logs\statmon_daemon.log"

REM --- Python selection (venv > explicit > PATH) ---
set "PY_EXE=%PYTHON_EXE%"
if exist "%APP_DIR%\venv\Scripts\python.exe" set "PY_EXE=%APP_DIR%\venv\Scripts\python.exe"
if "%PY_EXE%"=="" if exist "C:\Program Files\Python312\python.exe" set "PY_EXE=C:\Program Files\Python312\python.exe"
if "%PY_EXE%"=="" set "PY_EXE=python"

REM --- Ensure logs dir ---
if not exist "%APP_DIR%\logs" mkdir "%APP_DIR%\logs" >nul 2>&1

REM --- Mode parsing (fg/bg) ---
set "MODE=fg"
if /I "%~1"=="bg" (
  set "MODE=bg"
  shift
)

REM --- For display only ---
set "ARGS=%*"

REM --- Summary ---
echo(
echo [StatMon] Starting daemon
echo   App Dir   : %APP_DIR%
echo   Python    : %PY_EXE%
echo   Config    : %CFG_PATH%
echo   Log file  : %LOG_PATH%
if not "%STATMON_DB%"=="" echo   STATMON_DB : %STATMON_DB%
if not "%ARGS%"=="" echo   Extra args : %ARGS%
echo(

REM --- Unbuffered output ---
set "PYTHONUNBUFFERED=1"

REM --- Branch without parentheses to avoid parser issues ---
if /I "%MODE%"=="bg" goto :BG
goto :FG

:BG
REM New console that stays open after daemon exits.
REM Use /v:on so we can print !ERRORLEVEL! after Python finishes.
start "StatMon Daemon" "%ComSpec%" /v:on /k ^
""%PY_EXE%" -u -m statmon_daemon --log "%LOG_PATH%" --config "%CFG_PATH%" %* ^
^& echo( ^
^& echo [StatMon] Daemon exited with code !ERRORLEVEL! ^
^& echo Press any key to close this window... ^
^& pause>nul"
if errorlevel 1 (
  echo [StatMon] Failed to start daemon (background). Errorlevel %errorlevel%.
  exit /b %errorlevel%
)
echo [StatMon] Daemon started in background. Check "%LOG_PATH%".
exit /b 0

:FG
REM Foreground: run in current window and pause on exit.
"%PY_EXE%" -u -m statmon_daemon --log "%LOG_PATH%" --config "%CFG_PATH%" %*
set "EXITCODE=%ERRORLEVEL%"
echo(
echo [StatMon] Daemon exited with code %EXITCODE%.
echo(
echo Press any key to close this window...
pause >nul
exit /b %EXITCODE%
