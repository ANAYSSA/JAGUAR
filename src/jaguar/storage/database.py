"""
Local SQLite database for storing historical JAGUAR scans.

Requirement #6: Historical Reports.
Stores previous scans, allowing users to list history and diff
against previous runs.
"""

from __future__ import annotations

import json
import logging
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import TypeAdapter

from jaguar.config import get_config_dir
from jaguar.core.models import ScanResult, ScanSummary

logger = logging.getLogger("jaguar.storage")


class StorageDatabase:
    """Manages local SQLite storage of JAGUAR scans."""

    def __init__(self, db_path: Path | None = None):
        if db_path is None:
            db_path = get_config_dir() / "history.db"

        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _get_conn(self) -> sqlite3.Connection:
        """Get a configured database connection."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        """Initialize the database schema."""
        with self._get_conn() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS scans (
                    id TEXT PRIMARY KEY,
                    url TEXT NOT NULL,
                    hostname TEXT NOT NULL,
                    scanned_at TIMESTAMP NOT NULL,
                    overall_score INTEGER,
                    overall_grade TEXT,
                    data JSON NOT NULL
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_scans_url
                ON scans(url, scanned_at DESC)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_scans_hostname
                ON scans(hostname, scanned_at DESC)
            """)

    def save_scan(self, scan: ScanResult) -> None:
        """Save a ScanResult to the database."""
        # Convert to JSON
        scan_json = scan.model_dump_json()

        score = scan.overall_score.score if scan.overall_score else None
        grade = scan.overall_score.grade.value if scan.overall_score else None

        with self._get_conn() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO scans
                (id, url, hostname, scanned_at, overall_score, overall_grade, data)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    scan.id,
                    scan.url,
                    scan.hostname,
                    scan.scan_started_at.isoformat(),
                    score,
                    grade,
                    scan_json,
                ),
            )

        logger.debug("Saved scan %s to history database.", scan.id)

    def get_scan(self, scan_id: str) -> ScanResult | None:
        """Retrieve a specific ScanResult by ID."""
        with self._get_conn() as conn:
            cursor = conn.execute("SELECT data FROM scans WHERE id = ?", (scan_id,))
            row = cursor.fetchone()

            if not row:
                return None

            try:
                # Use TypeAdapter for Pydantic v2 JSON parsing
                adapter = TypeAdapter(ScanResult)
                return adapter.validate_json(row["data"])
            except Exception as e:
                logger.error("Failed to parse scan %s from database: %s", scan_id, e)
                return None

    def list_history(self, url: str | None = None, limit: int = 50) -> list[ScanSummary]:
        """
        List historical scans, optionally filtered by URL.
        Returns lightweight ScanSummary objects.
        """
        summaries: list[ScanSummary] = []

        query = "SELECT id, url, scanned_at, overall_score, overall_grade, data FROM scans"
        params: list[Any] = []

        if url:
            query += " WHERE url = ? OR hostname = ?"
            params.extend([url, url])

        query += " ORDER BY scanned_at DESC LIMIT ?"
        params.append(limit)

        with self._get_conn() as conn:
            cursor = conn.execute(query, params)

            for row in cursor:
                try:
                    # Extract analyzer scores from JSON data efficiently
                    # without loading the entire Pydantic model
                    data = json.loads(row["data"])
                    analyzer_scores = {}

                    for cat, res in data.get("analyzer_results", {}).items():
                        score_exp = res.get("score_explanation", {})
                        if "score" in score_exp:
                            analyzer_scores[cat] = score_exp["score"]

                    # Parse timestamp handling timezone info
                    dt_str = row["scanned_at"]
                    if dt_str.endswith("Z"):
                        dt_str = dt_str[:-1] + "+00:00"

                    try:
                        scanned_at = datetime.fromisoformat(dt_str)
                    except ValueError:
                        # Fallback for older formats
                        scanned_at = datetime.strptime(
                            dt_str.split(".")[0], "%Y-%m-%dT%H:%M:%S"
                        ).replace(tzinfo=UTC)

                    summaries.append(
                        ScanSummary(
                            id=row["id"],
                            url=row["url"],
                            scanned_at=scanned_at,
                            overall_score=row["overall_score"] or 0,
                            overall_grade=row["overall_grade"] or "F",  # type: ignore
                            analyzer_scores=analyzer_scores,
                        )
                    )
                except Exception as e:
                    logger.warning("Error parsing history row %s: %s", row["id"], e)

        return summaries
