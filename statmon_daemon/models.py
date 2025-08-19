# File: statmon_daemon/models.py
# Path: /statmon_daemon/models.py
"""
Tiny DB helper for the daemon.

Provides get_session(config) returning a sqlite3.Connection.
Swap out with SQLAlchemy later if needed.
"""

from pathlib import Path
import sqlite3
from typing import Any, Dict

def get_session(config: Dict[str, Any]):
    # Expect daemon.toml to have:
    # [database]
    # path = "db/development.sqlite3"
    db_path = (
        config.get("database", {}).get("path")
        or "db/development.sqlite3"
    )
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path, check_same_thread=False)
    return conn
