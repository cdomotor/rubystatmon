# File: statmon_daemon/filestore_ingest.py
# Full path: statmon_daemon/filestore_ingest.py
"""
filestore_ingest.py - Ingests data from on‑prem logger file storage
- Loads ingest tasks (stations, source paths, selected parameters, trend windows)
  from config_loader.load_filestore_tasks()
- Reads only user‑selected parameters
- Trims data to the configured rolling trend window
- Persists into shared DB (e.g., Reading table) for the Rails UI

Assumptions:
- You have models.get_session() and models.reading.Reading available
- Files are CSV or similar; replace _read_latest_file/_parse_file_rows with your format
"""

import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Any, List, Iterable

from statmon_daemon.config_loader import load_filestore_tasks
from models import get_session

# Optional; adapt to your schema
try:
    from models.reading import Reading  # fields: station_id, name, value, timestamp
except Exception:
    Reading = None  # allows the module to load even before model exists

logger = logging.getLogger("statmon_daemon")


class FileStoreIngest:
    def __init__(self, _config_ignored: dict = None):
        pass

    def run(self):
        """Execute one ingest pass across all configured file sources."""
        plan = load_filestore_tasks()
        tasks: List[Dict[str, Any]] = plan.get("tasks", [])

        if not tasks:
            logger.info("No filestore ingest tasks configured.")
            return

        logger.info(f"Filestore ingest starting ({len(tasks)} task(s)).")
        session = None
        try:
            session = get_session()

            for t in tasks:
                station_id = t["station_id"]
                station_name = t.get("station_name", f"Station {station_id}")
                source_path = Path(t["source_path"])
                params: Dict[str, Dict[str, Any]] = t.get("parameters", {})
                # params example: { "flow_rate": {"trend_days": 3}, "turbidity": {"trend_days": 7} }

                if not source_path.exists():
                    logger.warning(f"[{station_name}] Source path not found: {source_path}")
                    continue

                file_path = self._read_latest_file(source_path)
                if not file_path:
                    logger.info(f"[{station_name}] No files to ingest in {source_path}")
                    continue

                rows = self._parse_file_rows(file_path)  # iterable of dicts: {"timestamp": dt, "<param>": value, ...}
                if not rows:
                    logger.info(f"[{station_name}] No rows found in {file_path.name}")
                    continue

                now = datetime.utcnow()
                for param_name, meta in params.items():
                    trend_days = int(meta.get("trend_days", 7))
                    cutoff = now - timedelta(days=trend_days)

                    # Filter and upsert readings for this parameter
                    count = 0
                    for r in rows:
                        ts: datetime = r.get("timestamp")
                        if not ts or ts < cutoff:
                            continue
                        if param_name not in r:
                            continue

                        value = r[param_name]
                        if value is None:
                            continue

                        if Reading is None:
                            # Model not available yet—log only
                            logger.debug(f"[{station_name}] ({param_name}) {ts.isoformat()} = {value}")
                        else:
                            session.add(Reading(
                                station_id=station_id,
                                name=param_name,
                                value=float(value),
                                timestamp=ts,
                            ))
                        count += 1

                    logger.info(f"[{station_name}] {param_name}: ingested {count} row(s) (<= {trend_days} days).")

            if session:
                session.commit()
            logger.info("Filestore ingest complete.")

        except Exception:
            if session:
                session.rollback()
            logger.exception("Filestore ingest failed; rolled back DB transaction.")
        finally:
            if session:
                session.close()

    # ---------- Helpers you can customize to your actual file format ----------

    def _read_latest_file(self, directory: Path) -> Path | None:
        """Return the most recent file in a directory (by modified time)."""
        files = [p for p in directory.glob("*") if p.is_file()]
        if not files:
            return None
        return max(files, key=lambda p: p.stat().st_mtime)

    def _parse_file_rows(self, file_path: Path) -> Iterable[Dict[str, Any]]:
        """
        Parse rows from a data file.
        Default CSV implementation; replace with your actual format (.dat/.TOA5/etc).
        Expected to yield dicts with at least a 'timestamp' datetime and any param keys.
        """
        import csv
        from dateutil import parser as dtparse  # pip install python-dateutil

        rows: List[Dict[str, Any]] = []
        try:
            with file_path.open("r", newline="", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for raw in reader:
                    r: Dict[str, Any] = {}
                    # Try common timestamp headers (customize)
                    ts_key = next((k for k in ("Timestamp", "timestamp", "DateTime", "time") if k in raw), None)
                    if not ts_key:
                        continue
                    try:
                        r["timestamp"] = dtparse.parse(raw[ts_key]).replace(tzinfo=None)
                    except Exception:
                        continue

                    # Copy numeric fields (best effort)
                    for k, v in raw.items():
                        if k == ts_key:
                            continue
                        try:
                            r[k] = float(v)
                        except Exception:
                            # Non-numeric or empty; ignore
                            pass
                    rows.append(r)
        except Exception:
            logger.exception(f"Failed parsing file: {file_path}")
        return rows
