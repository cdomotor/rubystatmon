# File: statmon_daemon/logger_poll.py
# Full path: statmon_daemon/logger_poll.py
"""
logger_poll.py - Polls loggers directly for status/public table variables
- Loads polling tasks from config_loader.load_logger_poll_tasks()
- For each station, requests selected variables from Status/Public tables
- Persists latest values with timestamps into DB

Assumptions:
- Network access to loggers via HTTP or protocol supported by your environment
- You will replace _fetch_vars() with a real implementation (HTTP, PakBus, etc.)
- models.reading.Reading exists for persistence (or adjust to your schema)
"""

import logging
from datetime import datetime
from typing import Dict, Any, List

from statmon_daemon.config_loader import load_logger_poll_tasks
from .models import get_session

# Optional; adapt to your schema
try:
    from models.reading import Reading  # fields: station_id, name, value, timestamp
except Exception:
    Reading = None

logger = logging.getLogger("statmon_daemon")


class LoggerPoll:
    def __init__(self, _config_ignored: dict = None):
        pass

    def run(self):
        """Poll all configured stations for selected variables."""
        plan = load_logger_poll_tasks()
        tasks: List[Dict[str, Any]] = plan.get("tasks", [])

        if not tasks:
            logger.info("No logger poll tasks configured.")
            return

        logger.info(f"Logger poll starting ({len(tasks)} task(s)).")
        session = None
        try:
            session = get_session()

            for t in tasks:
                station_id = t["station_id"]
                station_name = t.get("station_name", f"Station {station_id}")
                ip = t["ip_address"]
                variables: List[str] = t.get("variables", [])  # e.g. ["Battery", "SignalStrength"]

                if not ip or not variables:
                    logger.warning(f"[{station_name}] Missing IP or variables; skipping.")
                    continue

                # Replace with real device read
                now = datetime.utcnow()
                values = self._fetch_vars(ip, variables)

                for var_name, val in values.items():
                    if val is None:
                        continue

                    if Reading is None:
                        logger.debug(f"[{station_name}] {var_name} = {val}")
                    else:
                        session.add(Reading(
                            station_id=station_id,
                            name=var_name,
                            value=float(val),
                            timestamp=now,
                        ))

                logger.info(f"[{station_name}] Polled {len(values)} variable(s).")

            if session:
                session.commit()
            logger.info("Logger poll complete.")

        except Exception:
            if session:
                session.rollback()
            logger.exception("Logger poll failed; rolled back DB transaction.")
        finally:
            if session:
                session.close()

    # --------------------- Replace with your real implementation ---------------------

    def _fetch_vars(self, ip: str, variables: List[str]) -> Dict[str, Any]:
        """
        Placeholder that returns dummy values.
        Implement HTTP/PakBus/CRBasic polling here and return a dict:
            { "Battery": 12.7, "SignalStrength": -72, ... }
        """
        # Example placeholder values
        fake_map = {}
        for v in variables:
            if v.lower().startswith("batt"):
                fake_map[v] = 12.5
            elif "signal" in v.lower():
                fake_map[v] = -70
            else:
                fake_map[v] = 0.0
        return fake_map
