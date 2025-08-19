# File: statmon_daemon/__main__.py
# Path: /statmon_daemon/__main__.py
"""
StatMon Daemon Entrypoint

Runs continuously to:
  - Auto-ping stations at configured intervals
  - Ingest logger data from file storage
  - Poll loggers directly for status/public table variables
  - Trigger alerts when conditions are met

Configuration is pulled from the shared StatMon database or a config file.
"""

import argparse
import logging
import logging.handlers
import signal
import sys
import time
from pathlib import Path

from .scheduler import Scheduler
from .config_loader import load_config
from .pinger import Pinger
from .filestore_ingest import FileStoreIngest
from .logger_poll import LoggerPoll
from .alerting import AlertManager


# -----------------------------------------------------------------------------
# CLI / Logging
# -----------------------------------------------------------------------------
def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="statmon-daemon", description="Run StatMon background services.")
    parser.add_argument("--config", help="Path to config file (ini/toml/json, depending on your loader).",
                        default="daemon.toml")
    parser.add_argument("--log", help="Path to log file.", default="logs/statmon_daemon.log")
    parser.add_argument("--debug", action="store_true", help="Enable debug logging.")
    return parser.parse_args()


def setup_logging(log_path: str, debug: bool) -> logging.Logger:
    # Ensure parent exists
    p = Path(log_path).expanduser()
    p.parent.mkdir(parents=True, exist_ok=True)

    level = logging.DEBUG if debug else logging.INFO
    logger = logging.getLogger("statmon_daemon")
    logger.setLevel(level)
    logger.handlers.clear()

    # Rotate at ~5 MB, keep 5 backups
    file_handler = logging.handlers.RotatingFileHandler(
        p, maxBytes=5 * 1024 * 1024, backupCount=5, encoding="utf-8"
    )
    file_handler.setLevel(level)

    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setLevel(level)

    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
    file_handler.setFormatter(fmt)
    stream_handler.setFormatter(fmt)

    logger.addHandler(file_handler)
    logger.addHandler(stream_handler)
    return logger


# -----------------------------------------------------------------------------
# Main
# -----------------------------------------------------------------------------
_shutdown = False


def _signal_handler(signum, frame):
    global _shutdown
    _shutdown = True


def main():
    args = parse_args()
    logger = setup_logging(args.log, args.debug)
    logger.info("Starting StatMon Daemon… (config=%s, log=%s, debug=%s)", args.config, args.log, args.debug)

    # Gentle shutdown on Ctrl+C / service stop
    signal.signal(signal.SIGINT, _signal_handler)
    # SIGTERM exists on Windows 10+ Python; if not, this will raise AttributeError which we ignore
    try:
        signal.signal(signal.SIGTERM, _signal_handler)
    except (AttributeError, ValueError):
        pass

    # Load configuration (from DB or file)
    try:
        config = load_config(args.config)
    except Exception as e:
        logger.exception("Failed to load configuration: %s", e)
        sys.exit(2)

    # Intervals (minutes) with sane defaults; let config override
    intervals = {
        "pinger": int(config.get("intervals", {}).get("pinger", 5)),
        "filestore_ingest": int(config.get("intervals", {}).get("filestore_ingest", 15)),
        "logger_poll": int(config.get("intervals", {}).get("logger_poll", 10)),
        "alerts": int(config.get("intervals", {}).get("alerts", 5)),
    }
    logger.info("Task intervals (min): %s", intervals)

    # Initialize core components
    try:
        pinger = Pinger(config)
        filestore_ingest = FileStoreIngest(config)
        logger_poll = LoggerPoll(config)
        alert_manager = AlertManager(config)
    except Exception as e:
        logger.exception("Failed to initialize components: %s", e)
        sys.exit(3)

    # Setup scheduler
    scheduler = Scheduler()

    # Wrap jobs with logging & error isolation so one failure doesn't kill the loop
    def _job(name, func):
        def _wrapped():
            start = time.time()
            logger.debug("Job %s: start", name)
            try:
                func()
            except Exception:
                logger.exception("Job %s: unhandled exception", name)
            finally:
                logger.debug("Job %s: done in %.2fs", name, time.time() - start)
        return _wrapped

    scheduler.every(intervals["pinger"]).minutes.do(_job("pinger", pinger.run))
    scheduler.every(intervals["filestore_ingest"]).minutes.do(_job("filestore_ingest", filestore_ingest.run))
    scheduler.every(intervals["logger_poll"]).minutes.do(_job("logger_poll", logger_poll.run))
    scheduler.every(intervals["alerts"]).minutes.do(_job("alerts", alert_manager.run))

    # Kick off once at startup (optional but nice)
    try:
        _job("pinger@startup", pinger.run)()
        _job("alerts@startup", alert_manager.run)()
    except Exception:
        logger.exception("Startup run failed (continuing).")

    # Main loop
    HEARTBEAT_SECS = 5
    last_beat = 0
    logger.info("Daemon is now running.")
    try:
        while not _shutdown:
            scheduler.run_pending()
            now = time.time()
            if now - last_beat >= HEARTBEAT_SECS:
                logger.debug("Heartbeat")
                last_beat = now
            time.sleep(1)
    except Exception:
        logger.exception("Daemon main loop crashed; exiting.")
        sys.exit(4)
    finally:
        logger.info("Shutting down daemon…")
        # If components need teardown, call here (e.g., close DB pools)


if __name__ == "__main__":
    main()
