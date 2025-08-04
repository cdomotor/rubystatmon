@echo off
setlocal

:: Set working directory to script location
cd /d %~dp0

:: Launch Tailwind CLI watcher in a new window
start "Tailwind Watcher" cmd /k "node_modules\.bin\tailwindcss-cli.cmd -i ./app/assets/stylesheets/application.tailwind.css -o ./app/assets/builds/application.css --watch"

:: Launch Rails server in a new window
start "Rails Server" cmd /k "bundle exec rails server"

endlocal
