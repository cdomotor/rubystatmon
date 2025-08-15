# File: statmon_daemon/alerting.py
# Full path: statmon_daemon/alerting.py
"""
alerting.py - Evaluates health conditions and sends notifications

Responsibilities:
  - Check recent PingResult rows for consecutive failures per station
  - Check Reading rows for data gaps (no new data within N hours)
  - Check Reading values against min/max thresholds per parameter
  - Send notifications (Teams/email) when alerts trigger

Design notes:
  - Tolerant to schema differences. Uses hasattr() where fields may not exist yet.
  - Pulls live settings from DB via config_loader on each run.
  - Notifications are stubbed (_notify_teams/_notify_email); wire in real creds later.

Assumed schema (adjust as needed):
  models.station.Station:
    - id:int, name:str
    - (optional) alert_ping_failures:int  -> consecutive ping failures before alert (default 3)
    - (optional) alert_gap_hours:int      -> hours without data before alert (default 6)
    - (optional) alert_thresholds:text/JSON (e.g. {"Battery":[11.5,14.5], "SignalStrength":[-120,-50]})

  models.ping.PingResult:
    - id, station_id, success:bool, latency_ms:float|None, timestamp:datetime (UTC)

  models.reading.Reading:
    - id, station_id, name:str, value:float, timestamp:datetime (UTC)
"""

from __future__ import annotations

import json
import logging
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

from statmon_daemon.config_loader import session_scope  # reuse context manager
from statmon_daemon.config_loader import load_config    # for global defaults (if any)

logger = logging.getLogger("statmon_daemon")

# --- Optional imports; keep module importable even if models not ready yet ---
try:
    from models.station import Station
except Exception:
    Station = None  # type: ignore

try:
    from models.ping import PingResult
except Exception:
    PingResult = None  # type: ignore

try:
    from models.reading import Reading
except Exception:
    Reading = None  # type: ignore


class AlertManager:
    def __init__(self, _config_ignored: dict = None):
        # In-memory guard to reduce duplicate alerts within a single daemon run.
        # For persistence across restarts, store in DB.
        self._last_alert_key_sent: set[str] = set()

    # --------------------------- Public entrypoint ---------------------------

    def run(self):
        """Evaluate all alert conditions and notify as needed."""
        if not (Station and PingResult and Reading):
            logger.warning("AlertManager: models not fully available; skipping.")
            return

        now = datetime.utcnow()
        cfg = load_config() or {}
        notify_cfg = self._load_notify_settings()  # from env/ini later if desired

        with session_scope() as session:
            stations = session.query(Station).all()

            # Build a quick map of latest readings per station/param
            latest_reading_map = self._latest_readings_map(session)

            for s in stations:
                sid = s.id
                sname = getattr(s, "name", f"Station {sid}")

                # Per-station settings with sensible defaults
                ping_fail_limit = self._get_int(s, "alert_ping_failures", 3)
                gap_hours = self._get_int(s, "alert_gap_hours", 6)
                thresholds = self._get_thresholds(s)

                # 1) Consecutive ping failures
                cons_fails = self._consecutive_ping_failures(session, sid, limit=ping_fail_limit)
                if cons_fails >= ping_fail_limit > 0:
                    key = f"pingfail:{sid}:{cons_fails}"
                    if key not in self._last_alert_key_sent:
                        self._send_alert(
                            notify_cfg,
                            title=f"[StatMon] Ping failure: {sname}",
                            body=f"{sname} has {cons_fails} consecutive failed pings (threshold {ping_fail_limit}).",
                            severity="high",
                        )
                        self._last_alert_key_sent.add(key)

                # 2) Data gaps (no readings within N hours) — checks any data; optionally restrict to tracked params
                gap_td = timedelta(hours=gap_hours)
                latest_ts = self._latest_station_timestamp(latest_reading_map, sid)
                if latest_ts is None or now - latest_ts > gap_td:
                    key = f"gap:{sid}:{gap_hours}"
                    if key not in self._last_alert_key_sent:
                        gap_str = "no data found" if latest_ts is None else f"last at {latest_ts.isoformat()}Z"
                        self._send_alert(
                            notify_cfg,
                            title=f"[StatMon] Data gap: {sname}",
                            body=f"{sname} has a data gap > {gap_hours}h ({gap_str}).",
                            severity="medium",
                        )
                        self._last_alert_key_sent.add(key)

                # 3) Threshold breaches for selected parameters
                # thresholds example: {"Battery":[11.5,14.5], "SignalStrength":[-120,-50]}
                if thresholds:
                    station_params = latest_reading_map.get(sid, {})
                    for pname, (vmin, vmax) in thresholds.items():
                        if pname not in station_params:
                            continue
                        val, ts = station_params[pname]
                        breach = ((vmin is not None and val < vmin) or
                                  (vmax is not None and val > vmax))
                        if breach:
                            key = f"thresh:{sid}:{pname}:{ts.isoformat()}"
                            if key not in self._last_alert_key_sent:
                                rng = f"[{vmin if vmin is not None else '-inf'}, {vmax if vmax is not None else '+inf'}]"
                                self._send_alert(
                                    notify_cfg,
                                    title=f"[StatMon] Threshold: {sname}.{pname}",
                                    body=f"{pname}={val} at {ts.isoformat()}Z outside {rng}.",
                                    severity="medium",
                                )
                                self._last_alert_key_sent.add(key)

        logger.info("Alert evaluation complete.")

    # ------------------------------ Calculations ------------------------------

    def _consecutive_ping_failures(self, session, station_id: int, limit: int) -> int:
        """Return number of most recent consecutive failed pings, up to a search window."""
        if limit <= 0:
            return 0
        # Search a small window (e.g., last 20) to avoid scanning the whole table
        q = (session.query(PingResult)
             .filter(PingResult.station_id == station_id)
             .order_by(PingResult.timestamp.desc())
             .limit(max(20, limit)))
        count = 0
        for pr in q:
            if getattr(pr, "success", False):
                break
            count += 1
        return count

    def _latest_readings_map(self, session) -> Dict[int, Dict[str, Tuple[float, datetime]]]:
        """
        Build {station_id: {param_name: (value, timestamp)}} for the latest reading per parameter.
        Note: Uses a simple approach; for large datasets, replace with GROUP BY subquery.
        """
        result: Dict[int, Dict[str, Tuple[float, datetime]]] = defaultdict(dict)
        # Fetch recent readings window (e.g., last 7 days) to keep memory modest
        window_start = datetime.utcnow() - timedelta(days=7)
        q = session.query(Reading).filter(Reading.timestamp >= window_start)
        for r in q:
            sid = r.station_id
            pname = getattr(r, "name", None)
            if not pname:
                continue
            prev = result[sid].get(pname)
            if prev is None or r.timestamp > prev[1]:
                try:
                    val = float(r.value)
                except Exception:
                    continue
                result[sid][pname] = (val, r.timestamp)
        return result

    def _latest_station_timestamp(self, latest_map: Dict[int, Dict[str, Tuple[float, datetime]]], station_id: int) -> Optional[datetime]:
        """Return latest timestamp across all parameters for the station."""
        params = latest_map.get(station_id, {})
        if not params:
            return None
        return max(ts for _, ts in params.values())

    # ------------------------------ Config helpers ----------------------------

    def _get_int(self, obj: Any, attr: str, default: int) -> int:
        try:
            if hasattr(obj, attr):
                v = getattr(obj, attr)
                if v is None:
                    return default
                return int(v)
        except Exception:
            pass
        return default

    def _get_thresholds(self, station: Any) -> Dict[str, Tuple[Optional[float], Optional[float]]]:
        """
        Parse JSON/text thresholds from station.alert_thresholds if present.
        Format expected: { "Param": [min, max], "Param2": [null, 10.0], ... }
        Returns: { "Param": (min|None, max|None), ... }
        """
        if not hasattr(station, "alert_thresholds"):
            return {}
        raw = getattr(station, "alert_thresholds", None)
        if not raw:
            return {}
        try:
            j = raw if isinstance(raw, dict) else json.loads(raw)
            out: Dict[str, Tuple[Optional[float], Optional[float]]] = {}
            for k, arr in (j or {}).items():
                if not isinstance(arr, (list, tuple)) or len(arr) != 2:
                    continue
                vmin = None if arr[0] is None else _to_float_or_none(arr[0])
                vmax = None if arr[1] is None else _to_float_or_none(arr[1])
                out[str(k)] = (vmin, vmax)
            return out
        except Exception:
            logger.exception("Failed to parse alert_thresholds JSON; ignoring for this station.")
            return {}

    # ---------------------------- Notification layer --------------------------

    def _send_alert(self, notify_cfg: Dict[str, Any], title: str, body: str, severity: str = "medium"):
        """
        Dispatch alert to configured channels.
        notify_cfg example:
          {
            "teams_webhook": "https://outlook.office.com/webhook/...",
            "email": {
              "smtp_host": "...", "smtp_port": 587,
              "username": "...", "password": "...",
              "from": "statmon@acme.com", "to": ["ops@acme.com"]
            }
          }
        """
        logger.warning(f"ALERT ({severity.upper()}): {title} :: {body}")
        try:
            if notify_cfg.get("teams_webhook"):
                self._notify_teams(notify_cfg["teams_webhook"], title, body, severity)
        except Exception:
            logger.exception("Failed sending Teams alert.")

        try:
            email_cfg = notify_cfg.get("email")
            if email_cfg:
                self._notify_email(email_cfg, title, body)
        except Exception:
            logger.exception("Failed sending Email alert.")

    def _notify_teams(self, webhook_url: str, title: str, body: str, severity: str):
        """
        Minimal Teams webhook JSON card. Replace with your preferred c
