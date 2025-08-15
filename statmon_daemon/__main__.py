# File: statmon_daemon/__main__.py
"""
StatMon Daemon Entrypoint

This is the main starting point for the StatMon background service (daemon).
It runs continuously to:
  - Auto-ping stations at configured intervals
  - Ingest logger data from file storage
  - Poll loggers directly for status/public table variables
  - Trigger alerts when conditions are met

Configuration is pulled from the shared StatMon database or .ini file.
"""

import time
import logging
from scheduler import Scheduler
from config_loader import load_config
from pinger import Pinger
from filestore_ingest import FileStoreIngest
from logger_poll import LoggerPoll
from alerting import AlertManager

# -----------------------------------------------------------------------------
# Configure logging
# -----------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler("statmon_daemon.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("statmon_daemon")

# -----------------------------------------------------------------------------
# Main entrypoint
# -----------------------------------------------------------------------------
def main():
    logger.info("Starting StatMon Daemon...")

    # Load configuration (from DB or ini)
    config = load_config()

    # Initialize core components
    pinger = Pinger(config)
    filestore_ingest = FileStoreIngest(config)
    logger_poll = LoggerPoll(config)
    alert_manager = AlertManager(config)

    # Setup scheduler
    scheduler = Scheduler()

    # Register tasks with their intervals (minutes)
    scheduler.every(5).minutes.do(pinger.run)
    scheduler.every(15).minutes.do(filestore_ingest.run)
    scheduler.every(10).minutes.do(logger_poll.run)
    scheduler.every(5).minutes.do(alert_manager.run)

    # Main loop
    try:
        while True:
            scheduler.run_pending()
            time.sleep(1)
    except KeyboardInterrupt:
        logger.info("Shutting down daemon...")

# -----------------------------------------------------------------------------
# Run if executed directly
# -----------------------------------------------------------------------------
if __name__ == "__main__":
    main()
