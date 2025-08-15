# File: statmon_daemon/config_loader.py
# Full path: statmon_daemon/config_loader.py
"""
Loads runtime configuration for the StatMon daemon.

- Pulls stations (id, name, ip_address) from the DB for pinging.
- Optionally reads ping settings from a Config table (if present).
- Falls back to safe defaults if no config rows exist.

Assumptions:
- models.get_session() returns a SQLAlchemy session.
- models.station.Station has: id, name, ip_address, enabled (bool), ping_enabled (bool, optional).
- models.config.Config (optional) has key/value (strings). Keys used here:
    PING_COUNT, PING_INTERVAL_SEC, PING_TIMEOUT_SEC, PING_PRIVILEGED
"""

from typing import Dict, Any, List
from contextlib import contextmanager

from models import get_session
from models.station import Station

# Optional: if you have a Config model; otherwise the try/except path will handle it.
try:
    from models.config import Config  # key (str), value (str)
except Exception:
    Config = None  # gracefully handle absence


DEFAULT_PING = {
    "count": 1,
    "interval": 0.8,     # seconds between echo requests
    "timeout": 2.0,      # per-host timeout
    "privileged": False, # run unprivileged by default
}


@contextmanager
def session_scope():
    """Provide a transactional scope around a series of operations."""
    session = get_session()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def _load_ping_settings(session) -> Dict[str, Any]:
    """Load ping settings from Config table if available; else defaults."""
    cfg = dict(DEFAULT_PING)
    if not Config:
        return cfg

    try:
        rows = session.query(Config).all()
    except Exception:
        # Table may not exist yet; keep defaults
        return cfg

    kv = {r.key: r.value for r in rows}

    # Parse with fallbacks
    if "PING_COUNT" in kv:
        try:
            cfg["count"] = int(kv["PING_COUNT"])
        except ValueError:
            pass

    if "PING_INTERVAL_SEC" in kv:
        try:
            cfg["interval"] = float(kv["PING_INTERVAL_SEC"])
        except ValueError:
            pass

    if "PING_TIMEOUT_SEC" in kv:
        try:
            cfg["timeout"] = float(kv["PING_TIMEOUT_SEC"])
        except ValueError:
            pass

    if "PING_PRIVILEGED" in kv:
        cfg["privileged"] = str(kv["PING_PRIVILEGED"]).strip().lower() in {"1", "true", "yes"}

    return cfg


def _load_stations_for_ping(session) -> List[Dict[str, Any]]:
    """
    Returns a list of stations to ping:
      [{ "id": int, "name": str, "ip_address": str }, ...]
    Filters: enabled == True, and (ping_enabled == True if column exists).
    """
    q = session.query(Station)

    # Filter enabled if present
    if hasattr(Station, "enabled"):
        q = q.filter(Station.enabled == True)  # noqa: E712

    # Filter ping_enabled if present
    if hasattr(Station, "ping_enabled"):
        q = q.filter(Station.ping_enabled == True)  # noqa: E712

    stations = []
    for s in q.all():
        ip = getattr(s, "ip_address", None)
        if not ip:
            continue
        stations.append({
            "id": s.id,
            "name": getattr(s, "name", f"Station {s.id}"),
            "ip_address": ip,
        })
    return stations


def load_config() -> Dict[str, Any]:
    """
    Returns:
        {
          "stations": [ {id, name, ip_address}, ... ],
          "ping": { count, interval, timeout, privileged }
        }
    """
    with session_scope() as session:
        return {
            "stations": _load_stations_for_ping(session),
            "ping": _load_ping_settings(session),
        }

# --- Add to: statmon_daemon/config_loader.py ---

def load_filestore_tasks() -> Dict[str, Any]:
    """
    Returns:
      {
        "tasks": [
          {
            "station_id": int,
            "station_name": str,
            "source_path": str,
            "parameters": {
                "<param_name>": {"trend_days": int},
                ...
            }
          },
          ...
        ]
      }
    Schema assumptions (tolerant):
    - Station has: id, name, filestore_path (str, path to folder)
    - Station has: ingest_enabled (bool) OR enabled (bool)
    - Station has: ingest_parameters (JSON/text) where we expect:
        { "flow_rate": {"trend_days": 3}, "turbidity": {"trend_days": 7} }
    """
    from models.station import Station

    tasks: List[Dict[str, Any]] = []
    with session_scope() as session:
        q = session.query(Station)

        if hasattr(Station, "enabled"):
            q = q.filter(Station.enabled == True)  # noqa: E712
        if hasattr(Station, "ingest_enabled"):
            q = q.filter(Station.ingest_enabled == True)  # noqa: E712

        for s in q.all():
            path = getattr(s, "filestore_path", None)
            if not path:
                continue

            params = {}
            if hasattr(s, "ingest_parameters") and s.ingest_parameters:
                try:
                    import json
                    params = json.loads(s.ingest_parameters)
                except Exception:
                    params = {}

            tasks.append({
                "station_id": s.id,
                "station_name": getattr(s, "name", f"Station {s.id}"),
                "source_path": path,
                "parameters": params or {},
            })

    return {"tasks": tasks}


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
    Schema assumptions (tolerant):
    - Station has: id, name, ip_address
    - Station has: poll_enabled (bool) OR enabled (bool)
    - Station has: poll_variables (JSON/text) like ["Battery", "SignalStrength"]
    """
    from models.station import Station

    tasks: List[Dict[str, Any]] = []
    with session_scope() as session:
        q = session.query(Station)
        if hasattr(Station, "enabled"):
            q = q.filter(Station.enabled == True)  # noqa: E712
        if hasattr(Station, "poll_enabled"):
            q = q.filter(Station.poll_enabled == True)  # noqa: E712

        for s in q.all():
            ip = getattr(s, "ip_address", None)
            if not ip:
                continue

            variables: List[str] = []
            if hasattr(s, "poll_variables") and s.poll_variables:
                try:
                    import json
                    variables = json.loads(s.poll_variables)
                except Exception:
                    variables = []

            tasks.append({
                "station_id": s.id,
                "station_name": getattr(s, "name", f"Station {s.id}"),
                "ip_address": ip,
                "variables": variables or [],
            })

    return {"tasks": tasks}
