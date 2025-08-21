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
from datetime import datetime, timezone
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
    def __init__(self, config: dict | None = None):
        # Keep config so DB/session helpers know where the DB is
        self.config: Dict[str, Any] = config or {}

    def run(self) -> None:
        """Poll all configured stations for selected variables."""
        plan = load_logger_poll_tasks()
        tasks: List[Dict[str, Any]] = list(plan.get("tasks", []))

        if not tasks:
            logger.info("No logger poll tasks configured.")
            return

        # Skip inactive/disabled tasks by default (mirrors pinger/alerting behavior)
        def _truthy(v: Any) -> bool:
            if isinstance(v, bool):
                return v
            if isinstance(v, (int, float)):
                return v != 0
            if isinstance(v, str):
                return v.strip().lower() in {"1", "true", "t", "yes", "y", "on"}
            return False

        tasks = [
            t for t in tasks
            if (("active" not in t) or _truthy(t.get("active")))
            and (("enabled" not in t) or _truthy(t.get("enabled")))
        ]

        if not tasks:
            logger.info("Logger poll: no active/enabled tasks after filtering.")
            return

        logger.info(f"Logger poll starting ({len(tasks)} task(s)).")
        session = None
        try:
            # ✅ FIX: pass full config so get_session can locate the DB/DSN
            session = get_session(self.config)

            # Some environments return a raw sqlite3 connection (execute/commit),
            # others an ORM session (add/commit). Detect minimal capabilities.
            has_add = hasattr(session, "add")

            for t in tasks:
                station_id = t["station_id"]
                station_name = t.get("station_name", f"Station {station_id}")
                ip = t.get("ip_address")
                variables: List[str] = list(t.get("variables", []))  # e.g. ["Battery", "SignalStrength"]

                if not ip or not variables:
                    logger.warning(f"[{station_name}] Missing IP or variables; skipping.")
                    continue

                # Replace with real device read
                now = datetime.now(timezone.utc)
                values = self._fetch_vars(ip, variables)

                if Reading is None or not has_add:
                    # Fallback: just log the values (no ORM available here)
                    for var_name, val in values.items():
                        if val is None:
                            continue
                        logger.debug(f"[{station_name}] {var_name} = {val}")
                else:
                    # ORM path
                    for var_name, val in values.items():
                        if val is None:
                            continue
                        try:
                            session.add(Reading(
                                station_id=station_id,
                                name=var_name,
                                value=float(val),
                                timestamp=now,
                            ))
                        except Exception:
                            logger.exception(f"[{station_name}] Failed to stage Reading for {var_name}")

                logger.info(f"[{station_name}] Polled {len(values)} variable(s).")

            # Commit if the session supports it
            try:
                session.commit()
            except Exception:
                # Raw sqlite3 connections also have commit(); keep same flow
                try:
                    session.commit()
                except Exception:
                    pass

            logger.info("Logger poll complete.")

        except Exception:
            if session:
                try:
                    session.rollback()
                except Exception:
                    pass
            logger.exception("Logger poll failed; rolled back DB transaction.")
        finally:
            if session:
                try:
                    session.close()
                except Exception:
                    pass

    # --------------------- Replace with your real implementation ---------------------

    def _fetch_vars(self, ip: str, variables: List[str]) -> Dict[str, Any]:
        """
        Placeholder that returns dummy values.
        Implement HTTP/PakBus/CRBasic polling here and return a dict:
            { "Battery": 12.7, "SignalStrength": -72, ... }
        """
        # Example placeholder values
        fake_map: Dict[str, Any] = {}
        for v in variables:
            vl = v.lower()
            if vl.startswith("batt"):
                fake_map[v] = 12.5
            elif "signal" in vl:
                fake_map[v] = -70
            else:
                fake_map[v] = 0.0
        return fake_map
