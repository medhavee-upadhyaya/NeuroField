"""SQLite snapshot logger — persists every sensor tick for replay."""
import asyncio
import json
import sqlite3
import time
from pathlib import Path
from typing import List, Optional

DB_PATH = Path(__file__).parent.parent / "data" / "replay.db"
MAX_SNAPSHOTS = 2000  # ~5.5 hours at 10s intervals


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def _init_db():
    with _connect() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS snapshots (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp    REAL    NOT NULL,
                sectors      TEXT    NOT NULL,
                anomalies    TEXT    NOT NULL,
                stats        TEXT    NOT NULL,
                agent_action TEXT
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_ts ON snapshots(timestamp)")
        conn.execute("""
            CREATE TABLE IF NOT EXISTS events (
                id        INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp REAL NOT NULL,
                type      TEXT NOT NULL,
                data      TEXT NOT NULL
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_event_ts ON events(timestamp)")
        conn.commit()


class SnapshotLogger:
    def __init__(self):
        _init_db()
        self._loop = None

    def _write_snapshot(self, snapshot: dict, agent_action: Optional[dict]):
        with _connect() as conn:
            conn.execute(
                "INSERT INTO snapshots (timestamp, sectors, anomalies, stats, agent_action) VALUES (?,?,?,?,?)",
                (
                    snapshot["timestamp"],
                    json.dumps(snapshot["sectors"]),
                    json.dumps(snapshot.get("active_anomalies", [])),
                    json.dumps(snapshot.get("stats", {})),
                    json.dumps(agent_action) if agent_action else None,
                ),
            )
            # prune old rows
            conn.execute(
                "DELETE FROM snapshots WHERE id NOT IN "
                "(SELECT id FROM snapshots ORDER BY timestamp DESC LIMIT ?)",
                (MAX_SNAPSHOTS,),
            )
            conn.commit()

    def _write_event(self, event_type: str, data: dict):
        with _connect() as conn:
            conn.execute(
                "INSERT INTO events (timestamp, type, data) VALUES (?,?,?)",
                (time.time(), event_type, json.dumps(data)),
            )
            conn.commit()

    async def log_snapshot(self, snapshot: dict, agent_action: Optional[dict] = None):
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, self._write_snapshot, snapshot, agent_action)

    async def log_event(self, event_type: str, data: dict):
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, self._write_event, event_type, data)

    def get_timeline(self, from_ts: float = 0, to_ts: Optional[float] = None) -> List[dict]:
        to_ts = to_ts or time.time()
        with _connect() as conn:
            rows = conn.execute(
                "SELECT timestamp, stats, agent_action FROM snapshots "
                "WHERE timestamp BETWEEN ? AND ? ORDER BY timestamp ASC",
                (from_ts, to_ts),
            ).fetchall()
        result = []
        for r in rows:
            stats = json.loads(r["stats"])
            result.append({
                "timestamp": r["timestamp"],
                "anomaly_count": stats.get("anomaly_count", 0),
                "critical_count": stats.get("critical_sectors", 0),
                "has_action": r["agent_action"] is not None,
            })
        return result

    def get_snapshot_at(self, timestamp: float) -> Optional[dict]:
        with _connect() as conn:
            row = conn.execute(
                "SELECT * FROM snapshots ORDER BY ABS(timestamp - ?) LIMIT 1",
                (timestamp,),
            ).fetchone()
        if not row:
            return None
        return {
            "timestamp": row["timestamp"],
            "sectors": json.loads(row["sectors"]),
            "active_anomalies": json.loads(row["anomalies"]),
            "stats": json.loads(row["stats"]),
            "agent_action": json.loads(row["agent_action"]) if row["agent_action"] else None,
        }

    def get_snapshots_range(self, from_ts: float, to_ts: float, limit: int = 100) -> List[dict]:
        with _connect() as conn:
            rows = conn.execute(
                "SELECT * FROM snapshots WHERE timestamp BETWEEN ? AND ? "
                "ORDER BY timestamp ASC LIMIT ?",
                (from_ts, to_ts, limit),
            ).fetchall()
        return [
            {
                "timestamp": r["timestamp"],
                "sectors": json.loads(r["sectors"]),
                "active_anomalies": json.loads(r["anomalies"]),
                "stats": json.loads(r["stats"]),
                "agent_action": json.loads(r["agent_action"]) if r["agent_action"] else None,
            }
            for r in rows
        ]

    def get_bounds(self) -> dict:
        with _connect() as conn:
            row = conn.execute(
                "SELECT MIN(timestamp) as min_ts, MAX(timestamp) as max_ts, COUNT(*) as total FROM snapshots"
            ).fetchone()
        return {
            "min_ts": row["min_ts"] or time.time(),
            "max_ts": row["max_ts"] or time.time(),
            "total": row["total"],
        }

    def get_events(self, from_ts: float = 0, to_ts: Optional[float] = None) -> List[dict]:
        to_ts = to_ts or time.time()
        with _connect() as conn:
            rows = conn.execute(
                "SELECT timestamp, type, data FROM events WHERE timestamp BETWEEN ? AND ? ORDER BY timestamp ASC",
                (from_ts, to_ts),
            ).fetchall()
        return [{"timestamp": r["timestamp"], "type": r["type"], **json.loads(r["data"])} for r in rows]
