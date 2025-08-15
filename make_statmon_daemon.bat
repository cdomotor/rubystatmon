@echo off
REM Make statmon_daemon directory and files
set DIR=statmon_daemon

REM Create the main directory
mkdir %DIR%

REM Create subfolders if needed
REM (Not strictly necessary for this layout, but here for extension)
REM mkdir %DIR%\tests

REM Create empty Python files
(
echo # __main__.py - Entrypoint for StatMon daemon
) > %DIR%\__main__.py

(
echo # scheduler.py - Task orchestration for StatMon daemon
) > %DIR%\scheduler.py

(
echo # config_loader.py - Loads config from DB or ini
) > %DIR%\config_loader.py

(
echo # pinger.py - Handles auto-ping logic
) > %DIR%\pinger.py

(
echo # filestore_ingest.py - Ingests data from on-prem logger file storage
) > %DIR%\filestore_ingest.py

(
echo # logger_poll.py - Polls loggers directly for status/public table vars
) > %DIR%\logger_poll.py

(
echo # alerting.py - Checks for failures and sends alerts
) > %DIR%\alerting.py

(
echo # utils.py - Shared helper functions (logging, retry, etc.)
) > %DIR%\utils.py

(
echo # constants.py - Paths, intervals, table names, status enums
) > %DIR%\constants.py

echo Folder and files created in %DIR%
pause
