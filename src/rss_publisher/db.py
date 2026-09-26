from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

_SCHEMA = """
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;
CREATE TABLE IF NOT EXISTS meta (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS feed_config (
  id INTEGER PRIMARY KEY CHECK (id = 1),
  json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS entries (
  id TEXT PRIMARY KEY,
  continuity_key TEXT,
  lifecycle TEXT NOT NULL,
  published_at TEXT,
  updated_at TEXT,
  sort_published_at TEXT,
  semantic_hash TEXT,
  json TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_entries_continuity ON entries(continuity_key);
CREATE INDEX IF NOT EXISTS idx_entries_lifecycle ON entries(lifecycle, sort_published_at DESC);
CREATE TABLE IF NOT EXISTS assets (
  id TEXT PRIMARY KEY,
  sha256 TEXT NOT NULL UNIQUE,
  original_filename TEXT,
  mime_type TEXT NOT NULL,
  size_bytes INTEGER NOT NULL,
  width INTEGER,
  height INTEGER,
  public_path TEXT NOT NULL,
  storage_path TEXT NOT NULL,
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS embeddings (
  entry_id TEXT PRIMARY KEY REFERENCES entries(id) ON DELETE CASCADE,
  model TEXT NOT NULL,
  dimensions INTEGER NOT NULL,
  semantic_hash TEXT NOT NULL,
  vector_json TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS audit (
  seq INTEGER PRIMARY KEY AUTOINCREMENT,
  at TEXT NOT NULL,
  operation TEXT NOT NULL,
  entry_id TEXT,
  detail_json TEXT NOT NULL
);
"""


class Database:
    def __init__(self, path: Path):
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as conn:
            conn.executescript(_SCHEMA)
            conn.execute("INSERT OR IGNORE INTO meta(key,value) VALUES('schema_version','1')")
            conn.execute("INSERT OR IGNORE INTO meta(key,value) VALUES('feed_revision','0')")
            conn.commit()

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.path, timeout=30)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        try:
            yield conn
        finally:
            conn.close()

    def revision(self, conn: sqlite3.Connection | None = None) -> int:
        if conn is None:
            with self.connect() as c:
                return self.revision(c)
        row = conn.execute("SELECT value FROM meta WHERE key='feed_revision'").fetchone()
        return int(row[0])

    def bump_revision(self, conn: sqlite3.Connection) -> int:
        current = self.revision(conn) + 1
        conn.execute("UPDATE meta SET value=? WHERE key='feed_revision'", (str(current),))
        return current

    def audit(self, conn: sqlite3.Connection, operation: str, entry_id: str | None, detail: dict, at: str) -> None:
        conn.execute(
            "INSERT INTO audit(at,operation,entry_id,detail_json) VALUES(?,?,?,?)",
            (at, operation, entry_id, json.dumps(detail, sort_keys=True, ensure_ascii=False)),
        )
