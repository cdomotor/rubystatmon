:: reset_assets.bat
:: Batch script to reset and recompile Rails assets for the StatMon application.
:: Usage: Double-click or run from command line in the rubystatmon directory.
:: This script will delete old compiled assets and generate fresh ones.
:: Only run this if you need to reset the assets (e.g., after changes to JS/CSS).

@echo off
setlocal

:: Move to script directory (repo root)
cd /d %~dp0

echo.
echo [StatMon] Resetting Rails assets...
echo.

:: Run clobber (delete old compiled assets)
bundle exec rails assets:clobber

:: Run precompile (fresh build)
bundle exec rails assets:precompile

echo.
echo [StatMon] Asset reset complete.
pause
endlocal
