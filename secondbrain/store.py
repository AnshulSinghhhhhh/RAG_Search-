from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

SCHEMA = """
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;
CREATE TABLE IF NOT EXISTS assets (
 id TEXT PRIMARY KEY, name TEXT NOT NULL, kind TEXT NOT NULL,
 size INTEGER NOT NULL, captured_at REAL NOT NULL, indexed_at REAL NOT NULL,
 metadata TEXT NOT NULL, signature TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS locations (
 path TEXT PRIMARY KEY, asset_id TEXT NOT NULL REFERENCES assets(id) ON DELETE CASCADE,
 mtime_ns INTEGER NOT NULL, size INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS chunks (
 id TEXT PRIMARY KEY, asset_id TEXT NOT NULL REFERENCES assets(id) ON DELETE CASCADE,
 text TEXT NOT NULL, start REAL, end REAL, ordinal INTEGER NOT NULL
);
CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(
 text, content='chunks', content_rowid='rowid', tokenize='unicode61'
);
CREATE TRIGGER IF NOT EXISTS chunks_ai AFTER INSERT ON chunks BEGIN
 INSERT INTO chunks_fts(rowid,text) VALUES(new.rowid,new.text);
END;
CREATE TRIGGER IF NOT EXISTS chunks_ad AFTER DELETE ON chunks BEGIN
 INSERT INTO chunks_fts(chunks_fts,rowid,text) VALUES('delete',old.rowid,old.text);
END;
CREATE TRIGGER IF NOT EXISTS chunks_au AFTER UPDATE OF text ON chunks BEGIN
 INSERT INTO chunks_fts(chunks_fts,rowid,text) VALUES('delete',old.rowid,old.text);
 INSERT INTO chunks_fts(rowid,text) VALUES(new.rowid,new.text);
END;
CREATE TABLE IF NOT EXISTS vectors (
 chunk_id TEXT NOT NULL REFERENCES chunks(id) ON DELETE CASCADE,
 space TEXT NOT NULL, model TEXT NOT NULL, dim INTEGER NOT NULL,
 data BLOB NOT NULL, scale REAL NOT NULL, qnorm REAL NOT NULL,
 PRIMARY KEY(chunk_id,space)
);
CREATE TABLE IF NOT EXISTS sources (
 path TEXT PRIMARY KEY, added_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS events (
 id INTEGER PRIMARY KEY, time REAL NOT NULL, path TEXT NOT NULL,
 action TEXT NOT NULL, seconds REAL NOT NULL, detail TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_chunks_asset ON chunks(asset_id);
CREATE INDEX IF NOT EXISTS ix_locations_asset ON locations(asset_id);
CREATE INDEX IF NOT EXISTS ix_assets_date ON assets(captured_at);
CREATE INDEX IF NOT EXISTS ix_vectors_space ON vectors(space,model);
"""


class Store:
    def __init__(self, home: Path):
        self.path = home / "memory.sqlite3"
        with self.connection() as db:
            db.executescript(SCHEMA)

    @contextmanager
    def connection(self) -> Iterator[sqlite3.Connection]:
        db = sqlite3.connect(self.path, timeout=30)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        try:
            yield db
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    def asset(self, asset_id: str) -> dict | None:
        with self.connection() as db:
            row = db.execute("SELECT * FROM assets WHERE id=?", (asset_id,)).fetchone()
            if not row:
                return None
            item = dict(row)
            item["metadata"] = json.loads(item["metadata"])
            item["paths"] = [r[0] for r in db.execute(
                "SELECT path FROM locations WHERE asset_id=? ORDER BY path", (asset_id,))]
            item["chunks"] = [dict(r) for r in db.execute(
                "SELECT id,text,start,end FROM chunks WHERE asset_id=? ORDER BY ordinal", (asset_id,))]
            return item

    def event(self, path: str, action: str, seconds: float, detail: dict) -> None:
        import time
        with self.connection() as db:
            db.execute("INSERT INTO events(time,path,action,seconds,detail) VALUES(?,?,?,?,?)",
                       (time.time(), path, action, seconds, json.dumps(detail)))

    def stats(self) -> dict:
        with self.connection() as db:
            kinds = dict(db.execute("SELECT kind,count(*) FROM assets GROUP BY kind"))
            row = db.execute("SELECT count(*),coalesce(sum(length(data)),0),coalesce(sum(dim*4),0) FROM vectors").fetchone()
            events = [dict(r) for r in db.execute("SELECT * FROM events ORDER BY id DESC LIMIT 12")]
            for event in events:
                event["detail"] = json.loads(event["detail"])
            return {
                "assets": sum(kinds.values()), "kinds": kinds,
                "locations": db.execute("SELECT count(*) FROM locations").fetchone()[0],
                "chunks": db.execute("SELECT count(*) FROM chunks").fetchone()[0],
                "vectors": row[0], "vector_bytes": row[1], "float32_vector_bytes": row[2],
                "database_bytes": sum(p.stat().st_size for p in self.path.parent.glob("memory.sqlite3*")),
                "source_bytes": db.execute("SELECT coalesce(sum(size),0) FROM assets").fetchone()[0],
                "sources": [dict(r) for r in db.execute("SELECT * FROM sources ORDER BY path")],
                "events": events,
            }

    def remove(self, path: Path) -> int:
        """Forget exact/descendant locations; never delete source files."""
        with self.connection() as db:
            paths = [r[0] for r in db.execute("SELECT path FROM locations")
                     if Path(r[0]) == path or path in Path(r[0]).parents]
            db.executemany("DELETE FROM locations WHERE path=?", ((p,) for p in paths))
            db.execute("DELETE FROM assets WHERE id NOT IN (SELECT asset_id FROM locations)")
            return len(paths)
