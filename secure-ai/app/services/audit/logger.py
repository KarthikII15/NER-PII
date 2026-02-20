"""
logger.py — SQLite-backed audit logger for document processing jobs.
Uses WAL mode for concurrent read/write performance.
"""
import json
import logging
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path

from app.models.document import ProcessResult

logger = logging.getLogger(__name__)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    job_id       TEXT PRIMARY KEY,
    filename     TEXT NOT NULL,
    status       TEXT NOT NULL,
    entity_count INTEGER DEFAULT 0,
    entities     TEXT,           -- JSON array of detected entities
    output_path  TEXT,
    error        TEXT,
    duration_s   REAL DEFAULT 0.0,
    created_at   TEXT NOT NULL
);
"""


class AuditLogger:
    """Thread-safe SQLite audit logger."""

    def __init__(self, db_path: str):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._init_db()

    def _init_db(self):
        with self._lock:
            conn = sqlite3.connect(str(self.db_path))
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")
            conn.executescript(_SCHEMA)
            conn.close()
            logger.info("Audit DB initialized at %s (WAL mode)", self.db_path)

    def log(self, result: ProcessResult):
        """Insert a completed job record into the audit database."""
        entities_json = json.dumps(
            [e.model_dump() for e in result.entities], default=str
        )
        with self._lock:
            conn = sqlite3.connect(str(self.db_path))
            try:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO jobs
                        (job_id, filename, status, entity_count, entities,
                         output_path, error, duration_s, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        result.job_id,
                        result.filename,
                        result.status.value,
                        result.entity_count,
                        entities_json,
                        result.output_path,
                        result.error,
                        result.duration_seconds,
                        result.created_at,
                    ),
                )
                conn.commit()
                logger.info("Audit logged: job=%s status=%s entities=%d",
                            result.job_id, result.status.value, result.entity_count)
            finally:
                conn.close()

    def get_job(self, job_id: str) -> dict | None:
        """Retrieve a single job record."""
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM jobs WHERE job_id = ?", (job_id,)).fetchone()
        conn.close()
        return dict(row) if row else None

    def get_stats(self) -> dict:
        """Return aggregate processing statistics."""
        conn = sqlite3.connect(str(self.db_path))
        cur = conn.execute("""
            SELECT
                COUNT(*) as total_jobs,
                SUM(CASE WHEN status = 'completed' THEN 1 ELSE 0 END) as completed,
                SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) as failed,
                SUM(entity_count) as total_entities,
                AVG(duration_s) as avg_duration_s
            FROM jobs
        """)
        row = cur.fetchone()
        conn.close()
        return {
            "total_jobs": row[0] or 0,
            "completed": row[1] or 0,
            "failed": row[2] or 0,
            "total_entities_detected": row[3] or 0,
            "avg_duration_seconds": round(row[4] or 0, 2),
        }
