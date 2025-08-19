# File: statmon_daemon/pinger.py
# Full path: statmon_daemon/pinger.py
"""
Pings stations using icmplib and persists results to the shared DB.
Stations and ping settings are loaded dynamically from config_loader
each run so UI changes take effect without restarting the daemon.
"""

import logging
from datetime import datetime
from typing import Tuple, Optional

from icmplib import ping as icmp_ping, ICMPLibError

from .models import get_session
from models.ping import PingResult
from statmon_daemon.config_loader import load_config  # <-- wired here

logger = logging.getLogger("statmon_daemon")


class Pinger:
    def __init__(self, _config_ignored: dict = None):
        """
        _config_ignored is kept for API compatibility with previous code,
        but we always reload from config_loader on each run().
        """
        pass

    def run(self):
        """Execute one auto‑ping cycle with the latest config."""
        config = load_config()
        stations = config.get("stations", [])
        ping_cfg = config.get("ping", {}) or {}

        count = int(ping_cfg.get("count", 1))
        interval = float(ping_cfg.get("interval", 0.8))
        timeout = float(ping_cfg.get("timeout", 2.0))
        privileged = bool(ping_cfg.get("privileged", False))

        if not stations:
            logger.warning("No stations configured for auto-ping.")
            return

        logger.info(f"Auto-ping cycle started for {len(stations)} station(s).")

        session = None
        try:
            session = get_session()

            for st in stations:
                station_id = st.get("id")
                name = st.get("name", f"Station {station_id or ''}".strip())
                ip = st.get("ip_address")

                if not station_id or not ip:
                    logger.warning(f"[{name}] Skipping: missing id or ip_address.")
                    continue

                latency_ms, success = self.ping_station(
                    ip=ip,
                    count=count,
                    interval=interval,
                    timeout=timeout,
                    privileged=privileged,
                )

                if success:
                    logger.info(f"[{name}] {ip} - Ping OK ({latency_ms:.1f} ms)")
                else:
                    logger.warning(f"[{name}] {ip} - Ping FAILED")

                self._save_ping_result(session, station_id, success, latency_ms)

            session.commit()
            logger.info("Auto-ping cycle complete.")

        except Exception:
            if session:
                session.rollback()
            logger.exception("Auto-ping cycle failed; rolled back DB transaction.")
        finally:
            if session:
                session.close()

    def ping_station(
        self,
        ip: str,
        count: int = 1,
        interval: float = 0.8,
        timeout: float = 2.0,
        privileged: bool = False,
    ) -> Tuple[Optional[float], bool]:
        """
        Ping a single host using icmplib.

        Returns:
            (latency_ms, success)
        """
        try:
            host = icmp_ping(
                address=ip,
                count=count,
                interval=interval,
                timeout=timeout,
                privileged=privileged,
            )
            success = host.is_alive
            latency = float(host.avg_rtt) if success else None
            return latency, success

        except ICMPLibError as e:
            logger.debug(f"icmplib error for {ip}: {e}")
            return None, False
        except Exception as e:
            logger.exception(f"Unexpected ping error for {ip}: {e}")
            return None, False

    def _save_ping_result(self, session, station_id: int, success: bool, latency_ms: Optional[float]):
        """Persist a ping result row in UTC."""
        session.add(PingResult(
            station_id=station_id,
            success=bool(success),
            latency_ms=float(latency_ms) if latency_ms is not None else None,
            timestamp=datetime.utcnow(),
        ))
