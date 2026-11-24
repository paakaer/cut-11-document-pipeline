"""SQLite storage for documents, extractions and reviews."""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS documents (
    id INTEGER PRIMARY KEY,
    filename TEXT NOT NULL,
    media_type TEXT NOT NULL,
    image_path TEXT NOT NULL,
    status TEXT NOT NULL,          -- queued | processing | needs_review | approved | failed
    error TEXT,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS extractions (
    id INTEGER PRIMARY KEY,
    document_id INTEGER NOT NULL REFERENCES documents(id),
    model TEXT NOT NULL,
    data TEXT NOT NULL,            -- NotebookPage JSON
    input_tokens INTEGER NOT NULL,
    output_tokens INTEGER NOT NULL,
    cost_usd REAL NOT NULL,
    latency_ms INTEGER NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS reviews (
    document_id INTEGER PRIMARY KEY REFERENCES documents(id),
    extraction_id INTEGER NOT NULL REFERENCES extractions(id),
    data TEXT NOT NULL,            -- approved NotebookPage JSON
    review_seconds INTEGER NOT NULL,
    reviewed_at TEXT NOT NULL
);
"""


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Store:
    def __init__(self, path: Path):
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        with self.conn() as c:
            c.executescript(SCHEMA)

    @contextmanager
    def conn(self):
        c = sqlite3.connect(self.path, timeout=10)
        c.row_factory = sqlite3.Row
        try:
            yield c
            c.commit()
        finally:
            c.close()

    def add_document(self, filename: str, media_type: str, image_path: str) -> int:
        with self.conn() as c:
            cur = c.execute(
                "INSERT INTO documents (filename, media_type, image_path, status, created_at) VALUES (?,?,?,?,?)",
                (filename, media_type, image_path, "queued", now()),
            )
            return cur.lastrowid

    def set_status(self, doc_id: int, status: str, error: str | None = None) -> None:
        with self.conn() as c:
            c.execute("UPDATE documents SET status=?, error=? WHERE id=?", (status, error, doc_id))

    def add_extraction(self, doc_id: int, model: str, data: str, input_tokens: int, output_tokens: int, cost: float, latency_ms: int) -> int:
        with self.conn() as c:
            cur = c.execute(
                "INSERT INTO extractions (document_id, model, data, input_tokens, output_tokens, cost_usd, latency_ms, created_at)"
                " VALUES (?,?,?,?,?,?,?,?)",
                (doc_id, model, data, input_tokens, output_tokens, cost, latency_ms, now()),
            )
            return cur.lastrowid

    def save_review(self, doc_id: int, extraction_id: int, data: str, seconds: int) -> None:
        with self.conn() as c:
            c.execute(
                "INSERT OR REPLACE INTO reviews (document_id, extraction_id, data, review_seconds, reviewed_at) VALUES (?,?,?,?,?)",
                (doc_id, extraction_id, data, seconds, now()),
            )
            c.execute("UPDATE documents SET status='approved' WHERE id=?", (doc_id,))

    def document(self, doc_id: int) -> sqlite3.Row | None:
        with self.conn() as c:
            return c.execute("SELECT * FROM documents WHERE id=?", (doc_id,)).fetchone()

    def latest_extraction(self, doc_id: int) -> sqlite3.Row | None:
        with self.conn() as c:
            return c.execute(
                "SELECT * FROM extractions WHERE document_id=? ORDER BY id DESC LIMIT 1", (doc_id,)
            ).fetchone()

    def review(self, doc_id: int) -> sqlite3.Row | None:
        with self.conn() as c:
            return c.execute("SELECT * FROM reviews WHERE document_id=?", (doc_id,)).fetchone()

    def list_documents(self) -> list[sqlite3.Row]:
        with self.conn() as c:
            return c.execute(
                """SELECT d.*, e.model, e.cost_usd, e.latency_ms, e.data AS extraction
                   FROM documents d
                   LEFT JOIN extractions e ON e.id = (SELECT MAX(id) FROM extractions WHERE document_id = d.id)
                   ORDER BY d.id DESC"""
            ).fetchall()

    def all_extractions(self) -> list[sqlite3.Row]:
        with self.conn() as c:
            return c.execute("SELECT * FROM extractions").fetchall()

    def reviewed_pairs(self) -> list[sqlite3.Row]:
        """Approved pages with the extraction the reviewer started from."""
        with self.conn() as c:
            return c.execute(
                """SELECT r.data AS approved, r.review_seconds, e.data AS extracted, e.model, e.cost_usd
                   FROM reviews r JOIN extractions e ON e.id = r.extraction_id"""
            ).fetchall()
