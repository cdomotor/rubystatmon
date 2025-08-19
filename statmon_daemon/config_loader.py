# File: statmon_daemon/config_loader.py
# Full path: /statmon_daemon/config_loader.py
"""
Loads runtime configuration for the StatMon daemon.

What this module does (resiliently):
- Pulls stations (id, name, ip_address) from the DB for pinging.
- Optionally reads ping settings from a key/value config table (if present).
- Builds filestore ingest tasks from station fields.
- Builds direct-logger poll tasks from station fields.
- Falls back to safe defaults if tables/columns are missing.

DB backends:
- Defaults to SQLite using the Rails DB at 'db/development.sqlite3'.
- You may override with env STATMON_DB.
- If you later provide .models.get_session (SQLAlchemy), this file will
  use it automatically; otherwise it opens a sqlite3 connection directly.

Assumed schema (tolerant: columns checked before use):
- Table: stations
  Required: id (int), ip_address (text)
  Optional: name (text), enabled (bool/int), ping_enabled (bool/int),
            filestore_path (text), ingest_enabled (bool/int),
            ingest_parameters (json/text),
            poll_enabled (bool/int), poll_variables (json/text)

- Key/Value config table (optional):
  First existing of: configs, config, settings, app_configs
  Columns: key (text), value (text)
  Keys honored: PING_COUNT, PING_INTERVAL_SEC, PING_TIMEOUT_SEC, PING_PRIVILEGED
"""

from __future__ import annotations

import json
import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple

# Optional: if you have a models.get_session, we try to use it
try:
    from .models import get_session as _maybe_get_session  # type: ignore
except Exception:
    _maybe_get_session = None  # graceful fallback to sqlite3

DEFAULT_DB_PATH = os.getenv("STATMON_DB", "db/development.sqlite3")

DEFAULT_PING: Dict[str, Any] = {
    "count": 1,
    "interval": 0.8,      # seconds between echo requests
    "timeout": 2.0,       # per-host timeout
    "privileged": False,  # run unprivileged by default
}

# ---------------------------- low-level helpers ----------------------------- #

def _open_sqlite(db_path: str) -> sqlite3.Connection:
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn

def _open_session() -> Any:
    """Prefer .models.get_session if available; else open sqlite3 connection."""
    if _maybe_get_session is not None:
        try:
            return _maybe_get_session({})
        except TypeError:
            # get_session() without args
            return _maybe_get_session()  # type: ignore[misc]
    return _open_sqlite(DEFAULT_DB_PATH)

@contextmanager
def session_scope():
    """
    Provide a transactional scope.
    Works for sqlite3.Connection or SQLAlchemy Session (if get_session returns one).
    """
    sess = _open_session()
    try:
        yield sess
        # Best-effort commit
        try:
            sess.commit()
        except Exception:
            pass
    except Exception:
        # Best-effort rollback
        try:
            sess.rollback()
        except Exception:
            pass
        raise
    finally:
        # Best-effort close
        try:
            sess.close()
        except Exception:
            try:
                # SQLAlchemy: session.bind.dispose() is overkill; this is fine
                sess.connection().close()  # type: ignore[attr-defined]
            except Exception:
                pass

def _is_sqlite(sess: Any) -> bool:
    return isinstance(sess, sqlite3.Connection)

def _exec_fetchall(sess: Any, sql: str, params: Iterable[Any] | Dict[str, Any] = ()) -> List[Dict[str, Any]]:
    """
    Execute a SELECT and return list of dict rows.
    Supports sqlite3.Connection and SQLAlchemy Session (without importing SA types).
    """
    if _is_sqlite(sess):
        cur = sess.execute(sql, params if not isinstance(params, dict) else tuple(params.values()))
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]

    # SQLAlchemy Session-like
    try:
        from sqlalchemy import text  # type: ignore
        res = sess.execute(text(sql), params if isinstance(params, dict) else tuple(params))  # type: ignore[arg-type]
        # SQLAlchemy 2.0 returns Row objects with ._mapping
        return [dict(r._mapping) for r in res]
    except Exception:
        # Last resort: try very simple path
        try:
            res = sess.execute(sql)  # type: ignore
            return [dict(r) for r in res]
        except Exception:
            return []

def _table_exists(sess: Any, table: str) -> bool:
    if _is_sqlite(sess):
        row = _exec_fetchall(sess, "SELECT name FROM sqlite_master WHERE type='table' AND name=?;", (table,))
        return bool(row)
    # SQLAlchemy-ish: try a trivial select
    try:
        _exec_fetchall(sess, f"SELECT * FROM {table} LIMIT 0;")
        return True
    except Exception:
        return False

def _columns_sqlite(sess: sqlite3.Connection, table: str) -> List[str]:
    cur = sess.execute(f"PRAGMA table_info({table});")
    return [r[1] for r in cur.fetchall()]

def _has_column(sess: Any, table: str, column: str) -> bool:
    if _is_sqlite(sess):
        try:
            return column in _columns_sqlite(sess, table)
        except Exception:
            return False
    # SQLAlchemy-ish: try selecting that column
    try:
        _exec_fetchall(sess, f"SELECT {column} FROM {table} LIMIT 0;")
        return True
    except Exception:
        return False

# ----------------------------- ping settings -------------------------------- #

def _load_ping_settings(sess: Any) -> Dict[str, Any]:
    """
    Load ping settings from the first existing config table among:
    configs, config, settings, app_configs. Falls back to DEFAULT_PING.
    """
    cfg = dict(DEFAULT_PING)
    for table in ("configs", "config", "settings", "app_configs"):
        if not _table_exists(sess, table):
            continue
        try:
            rows = _exec_fetchall(sess, f"SELECT key, value FROM {table};")
        except Exception:
            rows = []
        if not rows:
            continue

        kv = {str(r.get("key")): str(r.get("value")) for r in rows if r.get("key") is not None}
        # Parse with fallbacks
        try:
            if "PING_COUNT" in kv:
                cfg["count"] = int(kv["PING_COUNT"])
            if "PING_INTERVAL_SEC" in kv:
                cfg["interval"] = float(kv["PING_INTERVAL_SEC"])
            if "PING_TIMEOUT_SEC" in kv:
                cfg["timeout"] = float(kv["PING_TIMEOUT_SEC"])
            if "PING_PRIVILEGED" in kv:
                cfg["privileged"] = kv["PING_PRIVILEGED"].strip().lower() in {"1", "true", "yes"}
        except Exception:
            # Ignore bad values; keep defaults where parsing fails
            pass
        break  # use first found table
    return cfg

# ----------------------------- stations list -------------------------------- #

def _load_stations_for_ping(sess: Any) -> List[Dict[str, Any]]:
    """
    Returns a list of stations to ping:
      [{ "id": int, "name": str, "ip_address": str }, ...]
    Filters: enabled == true, and ping_enabled == true if those columns exist.
    """
    if not _table_exists(sess, "stations"):
        return []

    filters: List[str] = []
    if _has_column(sess, "stations", "enabled"):
        filters.append("enabled = 1")
    if _has_column(sess, "stations", "ping_enabled"):
        filters.append("ping_enabled = 1")

    where = f"WHERE {' AND '.join(filters)}" if filters else ""
    # Prefer name if present, else fallback to generated name
    select_name = "name" if _has_column(sess, "stations", "name") else "NULL as name"

    rows = _exec_fetchall(
        sess,
        f"SELECT id, {select_name}, ip_address FROM stations {where};"
    )

    out: List[Dict[str, Any]] = []
    for r in rows:
        ip = r.get("ip_address")
        if not ip:
            continue
        name = r.get("name") or f"Station {r.get('id')}"
        out.append({"id": r.get("id"), "name": name, "ip_address": ip})
    return out

# ------------------------------- public API --------------------------------- #

def load_config() -> Dict[str, Any]:
    """
    Returns:
        {
          "stations": [ {id, name, ip_address}, ... ],
          "ping": { count, interval, timeout, privileged }
        }
    """
    with session_scope() as sess:
        return {
            "stations": _load_stations_for_ping(sess),
            "ping": _load_ping_settings(sess),
        }

# --------------------------- filestore ingest tasks ------------------------- #

def load_filestore_tasks() -> Dict[str, Any]:
    """
    Returns:
      {
        "tasks": [
          {
            "station_id": int,
            "station_name": str,
            "source_path": str,
            "parameters": { "<param>": {"trend_days": int}, ... }
          },
          ...
        ]
      }

    Tolerant schema (all optional except id and source_path):
      - stations.filestore_path (string)
      - stations.ingest_enabled (bool/int) and/or stations.enabled (bool/int)
      - stations.name (string)
      - stations.ingest_parameters (json/text) e.g.:
          {"flow_rate":{"trend_days":3},"turbidity":{"trend_days":7}}
    """
    tasks: List[Dict[str, Any]] = []

    with session_scope() as sess:
        if not _table_exists(sess, "stations"):
            return {"tasks": tasks}

        filters: List[str] = []
        if _has_column(sess, "stations", "enabled"):
            filters.append("enabled = 1")
        if _has_column(sess, "stations", "ingest_enabled"):
            filters.append("ingest_enabled = 1")

        where = f"WHERE {' AND '.join(filters)}" if filters else ""
        select_name = "name" if _has_column(sess, "stations", "name") else "NULL as name"
        select_params = "ingest_parameters" if _has_column(sess, "stations", "ingest_parameters") else "NULL as ingest_parameters"

        rows = _exec_fetchall(
            sess,
            f"""SELECT id,
                       {select_name},
                       filestore_path,
                       {select_params}
                FROM stations
                {where};"""
        )

        for r in rows:
            path = r.get("filestore_path")
            if not path:
                continue

            params: Dict[str, Any] = {}
            raw = r.get("ingest_parameters")
            if raw:
                try:
                    params = json.loads(raw) if isinstance(raw, str) else dict(raw)  # tolerate JSON/text
                except Exception:
                    params = {}

            tasks.append({
                "station_id": r.get("id"),
                "station_name": r.get("name") or f"Station {r.get('id')}",
                "source_path": path,
                "parameters": params or {},
            })

    return {"tasks": tasks}

# ----------------------------- logger poll tasks ---------------------------- #

def load_logger_poll_tasks() -> Dict[str, Any]:
    """
    Returns:
      {
        "tasks": [
          {
            "station_id": int,
            "station_name": str,
            "ip_address": str,
            "variables": [str, ...]
          },
          ...
        ]
      }

    Tolerant schema:
      - stations.poll_enabled (bool/int) and/or stations.enabled (bool/int)
      - stations.poll_variables (json/text) e.g.: ["Battery","SignalStrength"]
      - stations.name (string)
    """
    tasks: List[Dict[str, Any]] = []

    with session_scope() as sess:
        if not _table_exists(sess, "stations"):
            return {"tasks": tasks}

        filters: List[str] = []
        if _has_column(sess, "stations", "enabled"):
            filters.append("enabled = 1")
        if _has_column(sess, "stations", "poll_enabled"):
            filters.append("poll_enabled = 1")

        where = f"WHERE {' AND '.join(filters)}" if filters else ""
        select_name = "name" if _has_column(sess, "stations", "name") else "NULL as name"
        select_vars = "poll_variables" if _has_column(sess, "stations", "poll_variables") else "NULL as poll_variables"

        rows = _exec_fetchall(
            sess,
            f"""SELECT id,
                       {select_name},
                       ip_address,
                       {select_vars}
                FROM stations
                {where};"""
        )

        for r in rows:
            ip = r.get("ip_address")
            if not ip:
                continue

            variables: List[str] = []
            raw = r.get("poll_variables")
            if raw:
                try:
                    variables = json.loads(raw) if isinstance(raw, str) else list(raw)
                except Exception:
                    variables = []

            tasks.append({
                "station_id": r.get("id"),
                "station_name": r.get("name") or f"Station {r.get('id')}",
                "ip_address": ip,
                "variables": variables or [],
            })

    return {"tasks": tasks}
