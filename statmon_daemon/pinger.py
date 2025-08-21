# File: statmon_daemon/pinger.py
# Path: /statmon_daemon/pinger.py
"""
StatMon Daemon - Pinger (continuous mode capable)

Pings selected stations and writes results into the Rails DB table `ping_results`.

Config sources & precedence (highest first):
  1) Optional DB overrides in a 'settings' table (section='ping', key/value pairs) — for future Rails UI.
  2) Process config passed into Pinger(config) — typically loaded from daemon.toml.
  3) Hardcoded safe defaults.

Key behaviors:
  - By default, only pings stations where stations.active == 1 (or truthy).
  - Can run once (legacy) or loop forever (continuous mode) with a sleep between cycles.
  - Supports a small per-station delay to avoid thundering herd on networks.

Units:
  - count: integer (packets)
  - interval: seconds (float) between packets within one ping call
  - timeout: seconds (float) for each packet reply
  - cycle_sleep: seconds (float) to wait between whole ping cycles (continuous mode)
  - per_station_sleep: seconds (float) to wait between stations in a cycle
  - jitter: seconds (float) max random +/- added to per_station_sleep to desynchronize starts
"""

from __future__ import annotations

import datetime as _dt
import os
import random
import re
import subprocess
import sys
import time
from typing import Any, Dict, Iterable, Optional, Tuple, List

from .models import get_session  # sqlite connection helper


class Pinger:
    def __init__(self, config: Dict[str, Any]) -> None:
        self.config = config or {}
        self._apply_config(self.config.get("ping") or {})

        # stations from config are only a fallback; DB is source of truth
        self._stations = list(self.config.get("stations") or [])

    # ------------------------------- Config --------------------------------- #
    def _apply_config(self, ping_cfg: Dict[str, Any]) -> None:
        # Packet-level
        self.count: int = int(ping_cfg.get("count", 1))                # packets
        self.interval: float = float(ping_cfg.get("interval", 0.8))    # seconds
        self.timeout: float = float(ping_cfg.get("timeout", 2.0))      # seconds
        self.privileged: bool = bool(ping_cfg.get("privileged", False))

        # Station selection
        self.include_inactive: bool = bool(ping_cfg.get("include_inactive", False))

        # Looping
        self.run_continuous: bool = bool(ping_cfg.get("run_continuous", False))
        self.cycle_sleep: float = float(ping_cfg.get("cycle_sleep", 300.0))           # seconds between cycles
        self.per_station_sleep: float = float(ping_cfg.get("per_station_sleep", 0.0)) # seconds between stations
        self.jitter: float = float(ping_cfg.get("jitter", 0.0))                       # +/- seconds

    def _maybe_reload_overrides(self, conn) -> None:
        """
        Optional: read live overrides from a generic `settings` table so the Rails UI
        can change pinger behavior without restarting the daemon.

        Expected schema (very small, easy to add via Rails migration):
            settings(section TEXT, key TEXT, value TEXT)
        We read rows where section='ping'. Keys supported mirror daemon.toml keys.

        This is a best-effort soft override; missing table/rows are ignored.
        """
        try:
            cur = conn.execute(
                "SELECT key, value FROM settings WHERE section = 'ping';"
            )
            rows = cur.fetchall() or []
        except Exception:
            return  # no table or query failed -> skip

        if not rows:
            return

        # Convert string values to proper types
        raw = {k: v for (k, v) in rows}
        def _to_bool(s: str) -> bool:
            return str(s).strip().lower() in {"1", "true", "t", "yes", "y", "on"}

        def _num(s: str, cast):
            try:
                return cast(s)
            except Exception:
                return None

        overrides: Dict[str, Any] = {}
        if "count" in raw: overrides["count"] = _num(raw["count"], int)
        if "interval" in raw: overrides["interval"] = _num(raw["interval"], float)
        if "timeout" in raw: overrides["timeout"] = _num(raw["timeout"], float)
        if "privileged" in raw: overrides["privileged"] = _to_bool(raw["privileged"])
        if "include_inactive" in raw: overrides["include_inactive"] = _to_bool(raw["include_inactive"])
        if "run_continuous" in raw: overrides["run_continuous"] = _to_bool(raw["run_continuous"])
        if "cycle_sleep" in raw: overrides["cycle_sleep"] = _num(raw["cycle_sleep"], float)
        if "per_station_sleep" in raw: overrides["per_station_sleep"] = _num(raw["per_station_sleep"], float)
        if "jitter" in raw: overrides["jitter"] = _num(raw["jitter"], float)

        # Drop None values and apply
        overrides = {k: v for k, v in overrides.items() if v is not None}
        if overrides:
            # Merge onto current ping config
            merged = {
                "count": self.count,
                "interval": self.interval,
                "timeout": self.timeout,
                "privileged": self.privileged,
                "include_inactive": self.include_inactive,
                "run_continuous": self.run_continuous,
                "cycle_sleep": self.cycle_sleep,
                "per_station_sleep": self.per_station_sleep,
                "jitter": self.jitter,
            }
            merged.update(overrides)
            self._apply_config(merged)

    # ------------------------------- Public --------------------------------- #
    def run(self) -> None:
        """
        Runs once (legacy) or forever if run_continuous=true.
        NOTE: If your higher-level scheduler already runs the pinger periodically,
        keep run_continuous=false to avoid double work.
        """
        conn = get_session(self.config)
        try:
            self._ensure_ping_table(conn)
        finally:
            try: conn.close()
            except Exception: pass

        if not self.run_continuous:
            self._run_once()
            return

        # Continuous loop
        print(f"[pinger] entering continuous mode (cycle_sleep={self.cycle_sleep}s)")
        try:
            while True:
                self._run_once()
                # Sleep between cycles
                try:
                    time.sleep(max(0.0, float(self.cycle_sleep)))
                except Exception:
                    time.sleep(1.0)
        except KeyboardInterrupt:
            print("[pinger] continuous mode interrupted; exiting.")

    def _run_once(self) -> None:
        """Ping selected stations once."""
        conn = get_session(self.config)
        try:
            # Pick up any operator/UI overrides without restart (optional settings table)
            self._maybe_reload_overrides(conn)

            stations = self._load_stations(conn)
            if not stations:
                print("[pinger] no stations to ping (active-only)")
                return

            for idx, s in enumerate(stations):
                sid = s.get("id")
                name = s.get("name") or f"Station {sid}"
                host = s.get("ip_address")
                if not host:
                    continue

                success, latency_ms = self._ping_host(host)
                self._save_ping_result(conn, sid, success, latency_ms)
                print(
                    f"[pinger] {name} ({host}) -> {'OK' if success else 'FAIL'}"
                    + (f" {latency_ms:.1f} ms" if success and latency_ms is not None else "")
                )

                # Gentle spacing between stations if requested
                if self.per_station_sleep > 0:
                    pause = self.per_station_sleep
                    if self.jitter > 0:
                        pause += random.uniform(-self.jitter, self.jitter)
                    if pause > 0:
                        time.sleep(pause)
        finally:
            try: conn.close()
            except Exception: pass

    # ------------------------- Station selection ---------------------------- #
    def _load_stations(self, conn) -> List[Dict[str, Any]]:
        """
        Priority:
          1) DB: SELECT id, name, ip_address FROM stations [WHERE active=1]
          2) Fallback: config stations filtered by 'active' (truthy) unless include_inactive.
        """
        try:
            if self.include_inactive:
                cur = conn.execute("SELECT id, name, ip_address FROM stations;")
            else:
                cur = conn.execute("SELECT id, name, ip_address FROM stations WHERE active = 1;")
            rows = cur.fetchall() or []
            db_stations = [
                {"id": r[0], "name": r[1], "ip_address": r[2]}
                for r in rows if r[2]
            ]
            if db_stations:
                return db_stations
        except Exception:
            pass

        # Fallback to config list
        if self.include_inactive:
            return [s for s in self._stations if s.get("ip_address")]
        else:
            return [s for s in self._stations if s.get("ip_address") and _truthy(s.get("active"))]

    # ----------------------------- DB helpers ------------------------------- #
    def _ensure_ping_table(self, conn) -> None:
        try:
            cur = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='ping_results';"
            )
            if cur.fetchone():
                return
        except Exception:
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
            print(f"[pinger] DB insert failed for station_id={station_id}: {e}", file=sys.stderr)

    # ---------------------------- Ping engines ------------------------------ #
    def _ping_host(self, host: str) -> Tuple[bool, Optional[float]]:
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
                return True, float(r.avg_rtt)  # ms
            return False, None
        except Exception:
            pass
        return self._ping_via_system(host)

    def _ping_via_system(self, host: str) -> Tuple[bool, Optional[float]]:
        is_windows = os.name == "nt"
        count = str(max(1, self.count))
        if is_windows:
            timeout_ms = str(int(max(1.0, self.timeout) * 1000))
            cmd = ["ping", "-n", count, "-w", timeout_ms, host]
        else:
            timeout_s = str(int(max(1.0, self.timeout)))
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
                timeout=max(2.0, self.timeout * (int(self.count) + 1)),
            )
            duration_ms = (time.time() - start) * 1000.0
            stdout = out.stdout or ""

            if out.returncode != 0 and "TTL=" not in stdout.upper() and "time=" not in stdout:
                return False, None

            times = _extract_times_ms(stdout)
            if times:
                return True, sum(times) / len(times)
            return True, duration_ms / max(1, int(self.count))

        except subprocess.TimeoutExpired:
            return False, None
        except Exception:
            return False, None


# --------------------------- parsing helpers -------------------------------- #

_TIME_RE = re.compile(r"time[=<]\s*(\d+(?:\.\d+)?)\s*ms", re.IGNORECASE)
_AVG_RES = [
    re.compile(r"Average\s*=\s*(\d+(?:\.\d+)?)\s*ms", re.IGNORECASE),
    re.compile(r"=\s*\d+(?:\.\d+)?/(\d+(?:\.\d+)?)/", re.IGNORECASE),
]

def _extract_times_ms(text: str) -> Optional[Iterable[float]]:
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


def _truthy(v: Any) -> bool:
    if isinstance(v, bool):
        return v
    if isinstance(v, (int, float)):
        return v != 0
    if isinstance(v, str):
        return v.strip().lower() in {"1", "true", "yes", "y", "on", "t"}
    return False
