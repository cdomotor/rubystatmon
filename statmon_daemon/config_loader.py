# File: statmon_daemon/config_loader.py
# Path: /statmon_daemon/config_loader.py
"""
Resilient config loader for StatMon daemon.

- Accepts optional path to a TOML config (daemon.toml).
- If provided and present, reads:
    [database]
    path = "db/development.sqlite3"

    [ping]
    count = 1
    interval = 0.8
    timeout = 2.0
    privileged = false

    [intervals]
    pinger = 5
    filestore_ingest = 15
    logger_poll = 10
    alerts = 5

- Merges DB-derived ping settings with file ping (file wins).
- Exposes: load_config(config_path=None) -> dict with keys:
    - stations: [{id, name, ip_address}, ...]
    - ping: {count, interval, timeout, privileged}
    - intervals: {pinger, filestore_ingest, logger_poll, alerts}
"""

from __future__ import annotations

import json
import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence

# Optional TOML (py311+ has tomllib)
try:
    import tomllib as _toml
except Exception:
    try:
        import tomli as _toml  # type: ignore
    except Exception:
        _toml = None  # TOML parsing disabled if neither available

# If you later provide .models.get_session (SQLAlchemy), we’ll use it.
try:
    from .models import get_session as _maybe_get_session  # type: ignore
except Exception:
    _maybe_get_session = None

# -------------------------- Defaults & Overrides ---------------------------- #

_DEFAULT_DB_PATH = os.getenv("STATMON_DB", "db/development.sqlite3")
_DB_OVERRIDE: Optional[str] = None  # set by load_config() if file specifies one

DEFAULT_PING: Dict[str, Any] = {
    "count": 1,
    "interval": 0.8,
    "timeout": 2.0,
    "privileged": False,
}
DEFAULT_INTERVALS: Dict[str, int] = {
    "pinger": 5,
    "filestore_ingest": 15,
    "logger_poll": 10,
    "alerts": 5,
}

# ---------------------------- Low-level helpers ----------------------------- #

def _open_sqlite(db_path: str) -> sqlite3.Connection:
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn

def _open_session() -> Any:
    """
    Prefer .models.get_session if present; else open sqlite3 using the override
    from load_config() or the default Rails DB path.
    """
    if _maybe_get_session is not None:
        try:
            return _maybe_get_session({})
        except TypeError:
            return _maybe_get_session()  # type: ignore[misc]
    db_path = _DB_OVERRIDE or _DEFAULT_DB_PATH
    return _open_sqlite(db_path)

@contextmanager
def session_scope():
    sess = _open_session()
    try:
        yield sess
        try:
            sess.commit()
        except Exception:
            pass
    except Exception:
        try:
            sess.rollback()
        except Exception:
            pass
        raise
    finally:
        try:
            sess.close()
        except Exception:
            pass

def _is_sqlite(sess: Any) -> bool:
    return isinstance(sess, sqlite3.Connection)

def _exec_fetchall(sess: Any, sql: str, params: Sequence[Any] | Dict[str, Any] = ()) -> List[Dict[str, Any]]:
    if _is_sqlite(sess):
        cur = sess.execute(sql, params if not isinstance(params, dict) else tuple(params.values()))
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]
    # SQLAlchemy path (avoid hard dep)
    try:
        from sqlalchemy import text  # type: ignore
        res = sess.execute(text(sql), params if isinstance(params, dict) else tuple(params))  # type: ignore[arg-type]
        return [dict(r._mapping) for r in res]
    except Exception:
        try:
            res = sess.execute(sql)  # type: ignore
            return [dict(r) for r in res]
        except Exception:
            return []

def _table_exists(sess: Any, table: str) -> bool:
    if _is_sqlite(sess):
        return bool(_exec_fetchall(sess, "SELECT name FROM sqlite_master WHERE type='table' AND name=?;", (table,)))
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
    try:
        _exec_fetchall(sess, f"SELECT {column} FROM {table} LIMIT 0;")
        return True
    except Exception:
        return False

# ----------------------------- Ping settings -------------------------------- #

def _load_ping_settings(sess: Any) -> Dict[str, Any]:
    """
    Load ping settings from the first existing config table among
    ('configs','config','settings','app_configs'). Falls back to DEFAULT_PING.
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
            pass
        break
    return cfg

# ----------------------------- Stations list -------------------------------- #

def _load_stations_for_ping(sess: Any) -> List[Dict[str, Any]]:
    """
    Returns a list of stations to ping:
      [{ "id": int, "name": str, "ip_address": str }, ...]
    Filters: enabled == 1 and ping_enabled == 1 when columns exist.
    """
    if not _table_exists(sess, "stations"):
        return []

    filters: List[str] = []
    if _has_column(sess, "stations", "enabled"):
        filters.append("enabled = 1")
    if _has_column(sess, "stations", "ping_enabled"):
        filters.append("ping_enabled = 1")
    where = f"WHERE {' AND '.join(filters)}" if filters else ""

    sel_name = "name" if _has_column(sess, "stations", "name") else "NULL as name"
    rows = _exec_fetchall(sess, f"SELECT id, {sel_name}, ip_address FROM stations {where};")

    out: List[Dict[str, Any]] = []
    for r in rows:
        ip = r.get("ip_address")
        if not ip:
            continue
        out.append({"id": r.get("id"), "name": r.get("name") or f"Station {r.get('id')}", "ip_address": ip})
    return out

# ------------------------------ Public API ---------------------------------- #

def load_config(config_path: Optional[str] = None) -> Dict[str, Any]:
    """
    Load config from (optional) TOML file and the DB.

    Args:
        config_path: path to daemon.toml (optional)

    Returns:
        {
          "stations":  [ {id, name, ip_address}, ... ],
          "ping":      { count, interval, timeout, privileged },
          "intervals": { pinger, filestore_ingest, logger_poll, alerts }
        }
    """
    # 1) Read file (optional)
    file_ping: Dict[str, Any] = {}
    file_intervals: Dict[str, Any] = {}
    global _DB_OVERRIDE

    if config_path:
        try:
            p = Path(config_path)
            if p.exists() and _toml is not None:
                with p.open("rb") as f:
                    t = _toml.load(f)  # dict
                # optional DB override
                db_path = (t.get("database") or {}).get("path")
                if isinstance(db_path, str) and db_path.strip():
                    _DB_OVERRIDE = db_path.strip()
                # optional ping + intervals
                if isinstance(t.get("ping"), dict):
                    file_ping = dict(t["ping"])
                if isinstance(t.get("intervals"), dict):
                    file_intervals = dict(t["intervals"])
        except Exception:
            # Do not fail if file is malformed; we’ll continue with defaults/DB
            pass

    # 2) Read DB-backed pieces
    with session_scope() as sess:
        stations = _load_stations_for_ping(sess)
        db_ping  = _load_ping_settings(sess)

    # 3) Merge ping (file wins over DB; DB wins over defaults already applied)
    ping_cfg = dict(db_ping)
    for k, v in (file_ping or {}).items():
        if k in DEFAULT_PING:
            ping_cfg[k] = v

    # 4) Intervals (file or defaults)
    intervals_cfg = dict(DEFAULT_INTERVALS)
    for k, v in (file_intervals or {}).items():
        if k in intervals_cfg:
            try:
                intervals_cfg[k] = int(v)
            except Exception:
                pass

    return {
        "stations": stations,
        "ping": ping_cfg,
        "intervals": intervals_cfg,
    }

# --------------------------- Filestore ingest tasks ------------------------- #

def load_filestore_tasks() -> Dict[str, Any]:
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

        sel_name = "name" if _has_column(sess, "stations", "name") else "NULL as name"
        sel_params = "ingest_parameters" if _has_column(sess, "stations", "ingest_parameters") else "NULL as ingest_parameters"

        rows = _exec_fetchall(
            sess,
            f"SELECT id, {sel_name}, filestore_path, {sel_params} FROM stations {where};"
        )

        for r in rows:
            path = r.get("filestore_path")
            if not path:
                continue
            params = {}
            raw = r.get("ingest_parameters")
            if raw:
                try:
                    params = json.loads(raw) if isinstance(raw, str) else dict(raw)
                except Exception:
                    params = {}
            tasks.append({
                "station_id": r.get("id"),
                "station_name": r.get("name") or f"Station {r.get('id')}",
                "source_path": path,
                "parameters": params or {},
            })
    return {"tasks": tasks}

# ----------------------------- Logger poll tasks ---------------------------- #

def load_logger_poll_tasks() -> Dict[str, Any]:
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

        sel_name = "name" if _has_column(sess, "stations", "name") else "NULL as name"
        sel_vars = "poll_variables" if _has_column(sess, "stations", "poll_variables") else "NULL as poll_variables"

        rows = _exec_fetchall(
            sess,
            f"SELECT id, {sel_name}, ip_address, {sel_vars} FROM stations {where};"
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
