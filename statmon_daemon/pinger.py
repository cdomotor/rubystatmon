# File: statmon_daemon/pinger.py
# Path: /statmon_daemon/pinger.py
"""
StatMon Daemon - Pinger

Pings configured stations and writes results into the Rails DB table
`ping_results` with columns commonly used by the Rails app:

  ping_results(
      id INTEGER PRIMARY KEY,
      station_id INTEGER NOT NULL,
      success BOOLEAN NOT NULL,
      latency_ms REAL,               -- nullable when failed
      created_at TEXT NOT NULL,      -- ISO8601
      updated_at TEXT NOT NULL       -- ISO8601
  )

Notes:
- Uses icmplib when available; falls back to system 'ping' on Windows.
- Works without admin privileges by preferring unprivileged ping modes.
- Does not depend on Ruby models. Writes rows with raw SQL using sqlite3.
"""

from __future__ import annotations

import datetime as _dt
import os
import re
import subprocess
import sys
import time
from typing import Any, Dict, Iterable, Optional, Tuple

from .models import get_session  # our sqlite connection helper


class Pinger:
    def __init__(self, config: Dict[str, Any]) -> None:
        self.config = config or {}
        self.ping_cfg: Dict[str, Any] = (self.config.get("ping") or {})
        # defaults (can be overridden by config_loader)
        self.count: int = int(self.ping_cfg.get("count", 1))
        self.interval: float = float(self.ping_cfg.get("interval", 0.8))
        self.timeout: float = float(self.ping_cfg.get("timeout", 2.0))
        self.privileged: bool = bool(self.ping_cfg.get("privileged", False))

        self._stations = list(self.config.get("stations") or [])

    # --------------------------------------------------------------------- #
    # Public API
    # --------------------------------------------------------------------- #
    def run(self) -> None:
        """Ping all configured stations once."""
        if not self._stations:
            print("[pinger] no stations configured")
            return

        # open one DB connection for the whole run
        conn = get_session({})
        try:
            self._ensure_ping_table(conn)
            for s in self._stations:
                sid = s.get("id")
                name = s.get("name") or f"Station {sid}"
                host = s.get("ip_address")
                if not host:
                    continue

                success, latency_ms = self._ping_host(host)
                self._save_ping_result(conn, sid, success, latency_ms)
                print(f"[pinger] {name} ({host}) -> {'OK' if success else 'FAIL'}"
                      + (f" {latency_ms:.1f} ms" if success and latency_ms is not None else ""))
        finally:
            try:
                conn.close()
            except Exception:
                pass

    # --------------------------------------------------------------------- #
    # DB helpers
    # --------------------------------------------------------------------- #
    def _ensure_ping_table(self, conn) -> None:
        """Create a very tolerant ping_results table if it doesn't exist.

        NOTE: Rails migrations normally create this. This is just a guard so
        the daemon doesn't crash if you run it first.
        """
        try:
            cur = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='ping_results';"
            )
            if cur.fetchone():
                return
        except Exception:
            # if PRAGMA fails or similar, best effort create anyway
            pass

        try:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS ping_results (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    station_id INTEGER NOT NULL,
                    success INTEGER NOT NULL,
                    latency_ms REAL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                """
            )
            conn.commit()
        except Exception:
            # If we fail to create, we still proceed; inserts may fail and will surface.
            pass

    def _save_ping_result(self, conn, station_id: int, success: bool, latency_ms: Optional[float]) -> None:
        now = _dt.datetime.utcnow().replace(microsecond=0).isoformat() + "Z"
        try:
            conn.execute(
                "INSERT INTO ping_results (station_id, success, latency_ms, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?);",
                (station_id, 1 if success else 0, latency_ms, now, now),
            )
            conn.commit()
        except Exception as e:
            # Don't kill the daemon over a single insert.
            print(f"[pinger] DB insert failed for station_id={station_id}: {e}", file=sys.stderr)

    # --------------------------------------------------------------------- #
    # Ping implementations
    # --------------------------------------------------------------------- #
    def _ping_host(self, host: str) -> Tuple[bool, Optional[float]]:
        """
        Returns (success, latency_ms). If success is False, latency_ms is None.
        Tries icmplib; on failure or ImportError, falls back to system 'ping'.
        """
        # 1) try icmplib for accurate timing (works cross-platform, unprivileged mode when possible)
        try:
            from icmplib import ping as _icmp_ping  # type: ignore

            r = _icmp_ping(
                host,
                count=max(1, self.count),
                interval=max(0.2, self.interval),
                timeout=max(0.5, self.timeout),
                privileged=bool(self.privileged),
            )
            if r.is_alive:
                # icmplib gives avg_rtt in ms already
                return True, float(r.avg_rtt)
            return False, None
        except Exception:
            # Fall back to system ping
            pass

        # 2) Windows/Linux/OSX fallback using system ping
        return self._ping_via_system(host)

    def _ping_via_system(self, host: str) -> Tuple[bool, Optional[float]]:
        """
        Cross-platform system 'ping' wrapper. Returns (success, latency_ms).
        - Windows: ping -n COUNT -w TIMEOUT_MS HOST
        - POSIX  : ping -c COUNT -W TIMEOUT_S HOST
        Parses time=XXms or averages when present.
        """
        is_windows = os.name == "nt"
        count = str(max(1, self.count))

        if is_windows:
            timeout_ms = str(int(max(1.0, self.timeout) * 1000))
            cmd = ["ping", "-n", count, "-w", timeout_ms, host]
        else:
            timeout_s = str(int(max(1.0, self.timeout)))
            # -i needs sudo on many systems; we skip it and just rely on defaults
            cmd = ["ping", "-c", count, "-W", timeout_s, host]

        try:
            start = time.time()
            out = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="ignore",
                timeout=max(2.0, self.timeout * (self.count + 1)),
            )
            duration_ms = (time.time() - start) * 1000.0
            stdout = out.stdout or ""

            # Detect failure by exit code or well-known phrases
            if out.returncode != 0 and "TTL=" not in stdout.upper() and "time=" not in stdout:
                return False, None

            # Try to parse 'time=XXms' occurrences and take the min or avg
            times = _extract_times_ms(stdout)
            if times:
                return True, sum(times) / len(times)

            # As a last resort, if ping succeeded but we couldn't parse time,
            # provide coarse duration per count.
            return True, duration_ms / max(1, self.count)

        except subprocess.TimeoutExpired:
            return False, None
        except Exception:
            return False, None


# --------------------------- parsing helpers -------------------------------- #

_TIME_RE = re.compile(r"time[=<]\s*(\d+(?:\.\d+)?)\s*ms", re.IGNORECASE)
_AVG_RES = [
    # Windows summary: "Minimum = 1ms, Maximum = 1ms, Average = 1ms"
    re.compile(r"Average\s*=\s*(\d+(?:\.\d+)?)\s*ms", re.IGNORECASE),
    # Linux/macOS summary: "rtt min/avg/max/mdev = 1.234/2.345/..."
    re.compile(r"=\s*\d+(?:\.\d+)?/(\d+(?:\.\d+)?)/", re.IGNORECASE),
]

def _extract_times_ms(text: str) -> Optional[Iterable[float]]:
    """Return a list of RTTs in milliseconds found in ping output, if any."""
    hits = [float(m.group(1)) for m in _TIME_RE.finditer(text)]
    if hits:
        return hits
    for rx in _AVG_RES:
        m = rx.search(text)
        if m:
            try:
                return [float(m.group(1))]
            except Exception:
                pass
    return None
