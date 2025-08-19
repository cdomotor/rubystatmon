# File: statmon_daemon/alerting.py
# Path: /statmon_daemon/alerting.py
"""
alerting.py - Evaluates health conditions and sends notifications

Responsibilities:
  - Check recent PingResult rows for consecutive failures per station
  - Check Reading rows for data gaps (no new data within N hours)
  - Check Reading values against min/max thresholds per parameter
  - Send notifications (Teams/email) when alerts trigger

Design notes:
  - Tolerant to schema differences. Uses defensive checks for columns.
  - Pulls live settings from DB via config_loader on each run.
  - Notifications are stubbed but functional: Teams via webhook, Email via SMTP.

Assumed schema (tolerant; columns checked before use):

  Table: stations
    id INTEGER PRIMARY KEY
    name TEXT
    enabled INTEGER (0/1)
    alert_ping_failures INTEGER          # default 3 (consecutive fails)
    alert_gap_hours INTEGER              # default 6 hours
    alert_thresholds TEXT/JSON           # {"Battery":[11.5,14.5], "SignalStrength":[-120,-50]}

  Table: ping_results
    id INTEGER PRIMARY KEY
    station_id INTEGER
    success INTEGER (0/1)
    latency_ms REAL
    created_at TEXT (ISO)                # preferred
    updated_at TEXT (ISO)
    -- or a 'timestamp' column (fallback)

  Table: readings
    id INTEGER PRIMARY KEY
    station_id INTEGER
    name TEXT
    value REAL
    timestamp TEXT (ISO)                 # preferred
    created_at TEXT (ISO)                # fallback
"""

from __future__ import annotations

import json
import logging
import smtplib
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple
from urllib.error import URLError
from urllib.request import Request, urlopen

# Use package-relative import so `python -m statmon_daemon` works
from .config_loader import session_scope

logger = logging.getLogger("statmon_daemon")


# --------------------------------------------------------------------------- #
# Utility: minimal SQL helpers (kept local so this file is self-contained)
# --------------------------------------------------------------------------- #

def _exec_fetchall(conn, sql: str, params: Sequence[Any] | Dict[str, Any] = ()) -> List[Dict[str, Any]]:
    cur = conn.execute(sql, params if not isinstance(params, dict) else tuple(params.values()))
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, row)) for row in cur.fetchall()]

def _exec_fetchone(conn, sql: str, params: Sequence[Any] | Dict[str, Any] = ()) -> Optional[Dict[str, Any]]:
    cur = conn.execute(sql, params if not isinstance(params, dict) else tuple(params.values()))
    row = cur.fetchone()
    if not row:
        return None
    cols = [d[0] for d in cur.description]
    return dict(zip(cols, row))

def _table_exists(conn, table: str) -> bool:
    try:
        row = _exec_fetchone(conn, "SELECT name FROM sqlite_master WHERE type='table' AND name=?;", (table,))
        return bool(row)
    except Exception:
        return False

def _columns(conn, table: str) -> List[str]:
    try:
        cur = conn.execute(f"PRAGMA table_info({table});")
        return [r[1] for r in cur.fetchall()]
    except Exception:
        return []

def _has_col(conn, table: str, col: str) -> bool:
    return col in _columns(conn, table)

def _parse_iso(ts: Optional[str]) -> Optional[datetime]:
    if not ts:
        return None
    try:
        # Accept both 'Z' and naive strings
        if ts.endswith("Z"):
            return datetime.fromisoformat(ts.replace("Z", "+00:00"))
        return datetime.fromisoformat(ts)
    except Exception:
        return None


# --------------------------------------------------------------------------- #
# Alert Manager
# --------------------------------------------------------------------------- #

class AlertManager:
    def __init__(self, _config_ignored: dict | None = None):
        # In-memory guard to reduce duplicate alerts within a single daemon uptime
        self._sent_keys: set[str] = set()

    # --------------------------- Public entrypoint --------------------------- #

    def run(self) -> None:
        """Evaluate all alert conditions and notify as needed."""
        with session_scope() as conn:
            if not _table_exists(conn, "stations"):
                logger.warning("AlertManager: no 'stations' table; skipping.")
                return

            stations = self._load_stations(conn)
            if not stations:
                logger.info("AlertManager: no stations to evaluate.")
                return

            # Build a quick map of latest readings (value, timestamp) per station/param
            latest_map = self._latest_readings_map(conn)

            for s in stations:
                sid = s["id"]
                name = s["name"]
                ping_fail_limit = int(s.get("alert_ping_failures", 3) or 3)
                gap_hours      = int(s.get("alert_gap_hours", 6) or 6)
                thresholds     = self._parse_thresholds(s.get("alert_thresholds"))

                # 1) Consecutive ping failures
                cons = self._consecutive_ping_failures(conn, sid, search_window=max(20, ping_fail_limit))
                if ping_fail_limit > 0 and cons >= ping_fail_limit:
                    key = f"pingfail:{sid}:{cons}"
                    if key not in self._sent_keys:
                        self._send_alert(
                            title=f"[StatMon] Ping failure: {name}",
                            body=f"{name} has {cons} consecutive failed pings (threshold {ping_fail_limit}).",
                            severity="high",
                        )
                        self._sent_keys.add(key)

                # 2) Data gap across all readings
                latest_ts = self._latest_station_timestamp(latest_map, sid)
                gap_td = timedelta(hours=gap_hours)
                now = datetime.now(timezone.utc)
                if latest_ts is None or (now - latest_ts) > gap_td:
                    key = f"gap:{sid}:{gap_hours}"
                    if key not in self._sent_keys:
                        gap_str = "no data found" if latest_ts is None else f"last at {latest_ts.isoformat()}"
                        self._send_alert(
                            title=f"[StatMon] Data gap: {name}",
                            body=f"{name} has a data gap > {gap_hours}h ({gap_str}).",
                            severity="medium",
                        )
                        self._sent_keys.add(key)

                # 3) Threshold breaches for selected parameters
                if thresholds:
                    params = latest_map.get(sid, {})
                    for pname, (vmin, vmax) in thresholds.items():
                        if pname not in params:
                            continue
                        val, ts = params[pname]
                        breach = ((vmin is not None and val < vmin) or
                                  (vmax is not None and val > vmax))
                        if breach:
                            key = f"thresh:{sid}:{pname}:{ts.isoformat()}"
                            if key not in self._sent_keys:
                                rng = f"[{vmin if vmin is not None else '-inf'}, {vmax if vmax is not None else '+inf'}]"
                                self._send_alert(
                                    title=f"[StatMon] Threshold: {name}.{pname}",
                                    body=f"{pname}={val} at {ts.isoformat()} outside {rng}.",
                                    severity="medium",
                                )
                                self._sent_keys.add(key)

        logger.info("Alert evaluation complete.")

    # ------------------------------ Loaders --------------------------------- #

    def _load_stations(self, conn) -> List[Dict[str, Any]]:
        cols = _columns(conn, "stations")
        if "id" not in cols:
            return []

        select: List[str] = ["id"]
        select += ["name"] if "name" in cols else ["NULL as name"]
        for c in ("alert_ping_failures", "alert_gap_hours", "alert_thresholds", "enabled"):
            select.append(c) if c in cols else None

        rows = _exec_fetchall(conn, f"SELECT {', '.join(select)} FROM stations")
        out: List[Dict[str, Any]] = []
        for r in rows:
            if "enabled" in r and r["enabled"] in (0, "0", False):
                continue
            out.append({
                "id": r["id"],
                "name": r.get("name") or f"Station {r['id']}",
                "alert_ping_failures": r.get("alert_ping_failures"),
                "alert_gap_hours": r.get("alert_gap_hours"),
                "alert_thresholds": r.get("alert_thresholds"),
            })
        return out

    def _latest_readings_map(self, conn) -> Dict[int, Dict[str, Tuple[float, datetime]]]:
        """
        Build {station_id: {param_name: (value, timestamp)}} using the freshest
        row per parameter within a 7-day window.
        """
        if not _table_exists(conn, "readings"):
            return {}

        cols = _columns(conn, "readings")
        if "station_id" not in cols or "name" not in cols:
            return {}

        ts_col = "timestamp" if "timestamp" in cols else ("created_at" if "created_at" in cols else None)
        val_col = "value" if "value" in cols else None
        if not ts_col or not val_col:
            return {}

        since = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
        rows = _exec_fetchall(
            conn,
            f"SELECT station_id, name, {val_col} as value, {ts_col} as ts FROM readings WHERE {ts_col} >= ?;",
            (since,),
        )

        latest: Dict[int, Dict[str, Tuple[float, datetime]]] = defaultdict(dict)
        for r in rows:
            sid = r["station_id"]
            pname = r["name"]
            ts = _parse_iso(r.get("ts"))
            if ts is None:
                continue
            try:
                val = float(r.get("value"))
            except Exception:
                continue
            prev = latest[sid].get(pname)
            if prev is None or ts > prev[1]:
                latest[sid][pname] = (val, ts)
        return latest

    # ------------------------------ Calculations ----------------------------- #

    def _consecutive_ping_failures(self, conn, station_id: int, search_window: int = 20) -> int:
        """Return number of most recent consecutive failed pings for a station."""
        if not _table_exists(conn, "ping_results"):
            return 0

        cols = _columns(conn, "ping_results")
        order_col = "created_at" if "created_at" in cols else ("timestamp" if "timestamp" in cols else "id")
        rows = _exec_fetchall(
            conn,
            f"SELECT success FROM ping_results WHERE station_id = ? ORDER BY {order_col} DESC LIMIT ?;",
            (station_id, search_window),
        )

        count = 0
        for r in rows:
            ok = r.get("success")
            ok_bool = (ok in (1, True, "1"))
            if ok_bool:
                break
            count += 1
        return count

    def _latest_station_timestamp(self, latest_map: Dict[int, Dict[str, Tuple[float, datetime]]], station_id: int) -> Optional[datetime]:
        params = latest_map.get(station_id, {})
        if not params:
            return None
        return max(ts for _, ts in params.values())

    # ------------------------------ Parsers ---------------------------------- #

    def _parse_thresholds(self, raw: Any) -> Dict[str, Tuple[Optional[float], Optional[float]]]:
        """
        Accepts dict or JSON string of: {"Param":[min,max], ...}
        Returns: { "Param": (min|None, max|None) }
        """
        if not raw:
            return {}
        try:
            data = raw if isinstance(raw, dict) else json.loads(raw)
            out: Dict[str, Tuple[Optional[float], Optional[float]]] = {}
            for k, arr in (data or {}).items():
                if not isinstance(arr, (list, tuple)) or len(arr) != 2:
                    continue
                vmin = None if arr[0] is None else _to_float(arr[0])
                vmax = None if arr[1] is None else _to_float(arr[1])
                out[str(k)] = (vmin, vmax)
            return out
        except Exception:
            logger.exception("AlertManager: failed to parse alert_thresholds JSON.")
            return {}

    # ---------------------------- Notification layer -------------------------- #

    def _send_alert(self, title: str, body: str, severity: str = "medium") -> None:
        """
        Dispatch alert to configured channels.

        Configuration sources (in order):
          1) Environment variables (TEAMS_WEBHOOK, SMTP_*),
          2) A future 'settings' table (not yet implemented here).

        Env vars supported:
          TEAMS_WEBHOOK
          SMTP_HOST, SMTP_PORT, SMTP_USERNAME, SMTP_PASSWORD, SMTP_FROM, SMTP_TO (comma-separated)
        """
        logger.warning(f"ALERT ({severity.upper()}): {title} :: {body}")

        # Teams
        webhook = _env("TEAMS_WEBHOOK")
        if webhook:
            try:
                self._notify_teams(webhook, title, body, severity)
            except Exception:
                logger.exception("Teams notification failed")

        # Email
        smtp_host = _env("SMTP_HOST")
        smtp_to = _env("SMTP_TO")
        if smtp_host and smtp_to:
            try:
                self._notify_email(
                    {
                        "smtp_host": smtp_host,
                        "smtp_port": int(_env("SMTP_PORT", "587")),
                        "username": _env("SMTP_USERNAME"),
                        "password": _env("SMTP_PASSWORD"),
                        "from": _env("SMTP_FROM") or "statmon@localhost",
                        "to": [x.strip() for x in smtp_to.split(",") if x.strip()],
                    },
                    title,
                    body,
                )
            except Exception:
                logger.exception("Email notification failed")

    def _notify_teams(self, webhook_url: str, title: str, body: str, severity: str) -> None:
        """
        Minimal Teams webhook JSON message using an Adaptive Card-like payload.
        Keeps dependencies minimal (urllib only).
        """
        payload = {
            "@type": "MessageCard",
            "@context": "https://schema.org/extensions",
            "summary": title,
            "themeColor": {"low": "0078D7", "medium": "FFA500", "high": "FF0000"}.get(severity, "0078D7"),
            "title": title,
            "text": body,
        }
        data = json.dumps(payload).encode("utf-8")
        req = Request(
            webhook_url,
            data=data,
            headers={"Content-Type": "application/json; charset=utf-8"},
            method="POST",
        )
        try:
            with urlopen(req, timeout=10) as resp:
                _ = resp.read()
        except URLError as e:
            raise RuntimeError(f"Teams webhook failed: {e}") from e

    def _notify_email(self, cfg: Dict[str, Any], subject: str, body: str) -> None:
        """
        Simple SMTP sender with STARTTLS.
        cfg keys:
          smtp_host (required), smtp_port (default 587),
          username/password (optional), from (required), to (list[str], required)
        """
        msg = EmailMessage()
        msg["Subject"] = subject
        msg["From"] = cfg["from"]
        msg["To"] = ", ".join(cfg["to"])
        msg.set_content(body)

        port = int(cfg.get("smtp_port", 587))
        with smtplib.SMTP(cfg["smtp_host"], port, timeout=15) as s:
            try:
                s.starttls()
            except Exception:
                pass
            if cfg.get("username") and cfg.get("password"):
                s.login(cfg["username"], cfg["password"])
            s.send_message(msg)


# --------------------------------------------------------------------------- #
# Small helpers
# --------------------------------------------------------------------------- #

def _to_float(v: Any) -> Optional[float]:
    try:
        return float(v)
    except Exception:
        return None

def _env(name: str, default: Optional[str] = None) -> Optional[str]:
    import os
    return os.environ.get(name, default)
# --------------------------------------------------------------------------- #