from __future__ import annotations

import json
import os
import re
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Callable

import numpy as np

from .config import Workspace
from .embeddings import Embeddings, quantize
from .extract import (Extractors, audio_chunks, dhash, distance, file_hash, modality,
                      open_image, text_chunks)
from .store import Store


def date_filters(query: str, now: datetime | None = None) -> tuple[str, float | None, float | None]:
    now = now or datetime.now().astimezone()
    today = now.replace(hour=0, minute=0, second=0, microsecond=0)
    rules = {
        "last month": ((today.replace(day=1) - timedelta(days=1)).replace(day=1), today.replace(day=1)),
        "this month": (today.replace(day=1), now),
        "yesterday": (today - timedelta(days=1), today),
        "today": (today, today + timedelta(days=1)),
        "last week": (today - timedelta(days=today.weekday() + 7), today - timedelta(days=today.weekday())),
        "past week": (now - timedelta(days=7), now),
    }
    for phrase, (after, before) in rules.items():
        if re.search(r"\b" + phrase + r"\b", query, re.I):
            return re.sub(r"\b" + phrase + r"\b", "", query, flags=re.I).strip(), after.timestamp(), before.timestamp()
    return query, None, None


class Brain:
    def __init__(self, home: str | Path | None = None, embeddings=None, extractors=None):
        self.workspace = Workspace(home)
        self.store = Store(self.workspace.home)
        self.embeddings = embeddings or Embeddings(self.workspace)
        self.extractors = extractors or Extractors(self.workspace)
        self.write_lock = threading.RLock()

    def add_source(self, path: str | Path) -> str:
        root = Path(path).expanduser().resolve()
        if not root.is_dir():
            raise ValueError(f"Folder does not exist: {root}")
        if root == self.workspace.home or self.workspace.home in root.parents:
            raise ValueError("Choose a folder outside the Second Brain data directory.")
        with self.store.connection() as db:
            db.execute("INSERT OR IGNORE INTO sources VALUES(?,?)", (str(root), time.time()))
        return str(root)

    def _near_image(self, image, image_hash: str) -> dict | None:
        with self.store.connection() as db:
            rows = db.execute("SELECT id,metadata FROM assets WHERE kind='image' ORDER BY indexed_at DESC LIMIT 150").fetchall()
        candidates = []
        for row in rows:
            meta = json.loads(row["metadata"])
            if meta.get("dimensions") == list(image.size) and meta.get("dhash"):
                gap = distance(image_hash, meta["dhash"])
                if gap <= 4:
                    candidates.append((gap, row["id"]))
        for _, asset_id in sorted(candidates):
            asset = self.store.asset(asset_id)
            if asset and asset["metadata"].get("ocr_complete") and any(Path(p).is_file() for p in asset["paths"]):
                return asset
        return None

    def ingest_file(self, path: str | Path, force: bool = False) -> dict:
        started = time.perf_counter()
        path = Path(path).expanduser().resolve()
        kind = modality(path)
        if not path.is_file():
            raise ValueError(f"File does not exist: {path}")
        if not kind:
            return {"path": str(path), "action": "unsupported", "seconds": 0}
        if self.workspace.home == path or self.workspace.home in path.parents:
            return {"path": str(path), "action": "ignored", "seconds": 0}
        stat = path.stat()
        if stat.st_size > self.workspace.settings.max_file_mb * 1024 * 1024:
            raise ValueError(f"File exceeds the {self.workspace.settings.max_file_mb} MB configured limit.")
        with self.write_lock:
            # Hash even unchanged files: equal size/mtime do not prove equal content.
            asset_id = file_hash(path)
            signature = self.workspace.index_signature()
            old = self.store.asset(asset_id)
            if old and old["signature"] == signature and not force:
                with self.store.connection() as db:
                    previous = db.execute("SELECT asset_id FROM locations WHERE path=?", (str(path),)).fetchone()
                    db.execute("INSERT OR REPLACE INTO locations VALUES(?,?,?,?)", (str(path), asset_id, stat.st_mtime_ns, stat.st_size))
                    db.execute("DELETE FROM assets WHERE id NOT IN (SELECT asset_id FROM locations)")
                action = "cached" if previous and previous[0] == asset_id else "duplicate"
                elapsed = time.perf_counter() - started
                self.store.event(str(path), action, elapsed, {})
                return {"id": asset_id, "path": str(path), "action": action, "seconds": elapsed}
            metadata: dict = {}
            visual = None
            if kind == "image":
                image = open_image(path)
                metadata.update(dimensions=list(image.size), dhash=dhash(image))
                lines = []
                if self.workspace.settings.ocr:
                    near = self._near_image(image, metadata["dhash"]) if not force else None
                    previous_image = None
                    if near:
                        try:
                            previous_image = open_image(next(Path(p) for p in near["paths"] if Path(p).is_file()))
                        except (OSError, StopIteration):
                            near = None
                    lines, metrics = self.extractors.image_text(image, previous_image,
                                        near["metadata"].get("ocr_lines", []) if near else None, force)
                    metadata.update(metrics, ocr_lines=lines, ocr_complete=True)
                    if near:
                        metadata["related_asset"] = near["id"]
                chunks = text_chunks("\n".join(line["text"] for line in lines))
                metadata["ocr_confidence"] = float(np.mean([line["confidence"] for line in lines])) if lines else None
                if self.workspace.settings.vision:
                    visual = self.embeddings.image(str(path))
                image.thumbnail((720, 720))
                image.save(self.workspace.thumbnails / f"{asset_id}.webp", "WEBP", quality=82)
            elif kind == "audio":
                segments, metadata = self.extractors.audio(path)
                chunks = audio_chunks(segments)
            else:
                chunks = text_chunks(path.read_text(encoding="utf-8-sig", errors="replace"))
            # Always keep one row so images with no text can own a visual vector.
            if not chunks:
                chunks = [{"text": "", "start": None, "end": None}]
            nonempty = [chunk for chunk in chunks if chunk["text"].strip()]
            text_vectors = iter(self.embeddings.text([chunk["text"] for chunk in nonempty]))
            packed = []
            for index, chunk in enumerate(chunks):
                chunk["id"] = f"{asset_id}:{index}"
                if chunk["text"].strip():
                    vector = next(text_vectors)
                    packed.append((chunk["id"], "text", self.workspace.settings.text_model, len(vector), *quantize(vector)))
            if visual is not None:
                packed.append((chunks[0]["id"], "visual", self.workspace.settings.vision_model, len(visual), *quantize(visual)))
            # Detect a file being modified during processing; do not commit mixed evidence.
            if file_hash(path) != asset_id:
                raise RuntimeError("File changed during indexing. Retry once the write has finished.")
            elapsed = time.perf_counter() - started
            metadata["processing_seconds"] = elapsed
            with self.store.connection() as db:
                db.execute("INSERT INTO assets VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET metadata=excluded.metadata,signature=excluded.signature,indexed_at=excluded.indexed_at",
                           (asset_id, path.name, kind, stat.st_size, stat.st_mtime, time.time(), json.dumps(metadata), signature))
                db.execute("DELETE FROM chunks WHERE asset_id=?", (asset_id,))
                db.executemany("INSERT INTO chunks VALUES(?,?,?,?,?,?)", ((chunk["id"], asset_id, chunk["text"], chunk["start"], chunk["end"], i) for i, chunk in enumerate(chunks)))
                db.executemany("INSERT INTO vectors VALUES(?,?,?,?,?,?,?)", packed)
                db.execute("INSERT OR REPLACE INTO locations VALUES(?,?,?,?)", (str(path), asset_id, stat.st_mtime_ns, stat.st_size))
                db.execute("DELETE FROM assets WHERE id NOT IN (SELECT asset_id FROM locations)")
            detail = {"chunks": len(chunks), "vectors": len(packed), **{k: metadata[k] for k in ("ocr_strategy", "ocr_area_fraction", "reused_lines") if k in metadata}}
            self.store.event(str(path), "indexed", elapsed, detail)
            return {"id": asset_id, "path": str(path), "action": "indexed", "seconds": elapsed, **detail}

    def ingest(self, path: str | Path, force: bool = False, progress: Callable | None = None) -> dict:
        root = Path(path).expanduser().resolve()
        if not root.exists():
            raise ValueError(f"Path does not exist: {root}")
        files = []
        if root.is_file():
            files = [root]
        else:
            self.add_source(root)
            # Ignore hidden/runtime folders and symlinks; never crawl model caches or .git.
            for current, directories, names in os.walk(root, followlinks=False):
                directories[:] = sorted(d for d in directories if not d.startswith(".") and d not in {"node_modules", "__pycache__", "venv"}
                                        and not (Path(current) / d).is_symlink()
                                        and (Path(current) / d).resolve() != self.workspace.home)
                files.extend(Path(current) / name for name in sorted(names)
                             if modality(Path(name)) and not (Path(current) / name).is_symlink())
        started = time.perf_counter()
        report = {"total": len(files), "indexed": 0, "cached": 0, "duplicate": 0, "errors": [], "files": []}
        for index, file in enumerate(files):
            if progress:
                progress({"current": index, "total": len(files), "path": str(file)})
            try:
                result = self.ingest_file(file, force)
                report[result["action"]] = report.get(result["action"], 0) + 1
                report["files"].append(result)
            except Exception as exc:
                report["errors"].append({"path": str(file), "error": str(exc)})
                self.store.event(str(file), "error", 0, {"error": str(exc)})
        report["seconds"] = round(time.perf_counter() - started, 3)
        return report

    def _filters(self, kind: str | None, after: float | None, before: float | None, folder: str | None):
        sql, params = [], []
        if kind:
            sql.append("a.kind=?")
            params.append(kind)
        if after is not None:
            sql.append("a.captured_at>=?")
            params.append(after)
        if before is not None:
            sql.append("a.captured_at<?")
            params.append(before)
        if folder:
            root = str(Path(folder).expanduser().resolve())
            # Escape SQL LIKE metacharacters in literal folder names.
            prefix = (root + os.sep).replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            sql.append("EXISTS(SELECT 1 FROM locations l WHERE l.asset_id=a.id AND (l.path=? OR l.path LIKE ? ESCAPE '\\'))")
            params.extend([root, prefix + "%"])
        return (" AND " + " AND ".join(sql) if sql else ""), params

    def search(self, query: str, limit: int = 12, kind: str | None = None, after: float | None = None,
               before: float | None = None, folder: str | None = None, lexical_only: bool = False) -> dict:
        started = time.perf_counter()
        clean, inferred_after, inferred_before = date_filters(query.strip())
        after = after if after is not None else inferred_after
        before = before if before is not None else inferred_before
        where, params = self._filters(kind, after, before, folder)
        rankings: dict[str, list[tuple[str, float]]] = {}
        matched: dict[str, dict] = {}
        warnings = []
        with self.store.connection() as db:
            if not clean.strip():
                ids = [r[0] for r in db.execute("SELECT a.id FROM assets a WHERE 1=1" + where + " ORDER BY a.captured_at DESC LIMIT ?", [*params, limit])]
                return {"results": [self._result(asset_id, None, {}, 0) for asset_id in ids],
                        "seconds": round(time.perf_counter() - started, 3), "query": query, "warnings": []}
            words = re.findall(r"[^\W_]+", clean, flags=re.UNICODE)[:40]
            if words:
                expression = " OR ".join('"' + word.replace('"', '""') + '"' for word in words)
                rows = db.execute("SELECT c.*,bm25(chunks_fts) AS bm FROM chunks_fts JOIN chunks c ON c.rowid=chunks_fts.rowid JOIN assets a ON a.id=c.asset_id WHERE chunks_fts MATCH ?" + where + " ORDER BY bm LIMIT 120", [expression, *params]).fetchall()
                rankings["keyword"] = [(row["id"], -float(row["bm"])) for row in rows]
                matched.update({row["id"]: dict(row) for row in rows})
            spaces = ["text"] + (["visual"] if self.workspace.settings.vision and kind in (None, "image") else [])
            if not lexical_only:
                for space in spaces:
                    model = self.workspace.settings.text_model if space == "text" else self.workspace.settings.vision_model
                    count = db.execute("SELECT count(*) FROM vectors v JOIN chunks c ON c.id=v.chunk_id JOIN assets a ON a.id=c.asset_id WHERE v.space=? AND v.model=?" + where, [space, model, *params]).fetchone()[0]
                    if not count:
                        continue
                    try:
                        query_vector = self.embeddings.text([clean or query], query=True)[0] if space == "text" else self.embeddings.visual_query(clean or query)
                        query_vector = np.asarray(query_vector, dtype=np.float32)
                        query_vector /= max(float(np.linalg.norm(query_vector)), 1e-10)
                        cursor = db.execute("SELECT c.*,v.data,v.dim,v.qnorm FROM vectors v JOIN chunks c ON c.id=v.chunk_id JOIN assets a ON a.id=c.asset_id WHERE v.space=? AND v.model=?" + where, [space, model, *params])
                        scores = []
                        while rows := cursor.fetchmany(512):
                            for row in rows:
                                if row["dim"] != len(query_vector):
                                    continue
                                score = float(np.dot(np.frombuffer(row["data"], dtype=np.int8).astype(np.float32), query_vector) / max(row["qnorm"], 1e-10))
                                # Keep weak visual similarities out of evidence summaries.
                                if score >= (0.12 if space == "visual" else 0.25):
                                    scores.append((row["id"], score))
                                    matched[row["id"]] = {k: row[k] for k in ("id", "asset_id", "text", "start", "end")}
                        rankings[space] = sorted(scores, key=lambda item: item[1], reverse=True)[:120]
                    except Exception as exc:
                        warnings.append(f"{space.capitalize()} search unavailable: {exc}")
        fused: dict[str, float] = {}
        channels: dict[str, dict] = {}
        for channel, ranking in rankings.items():
            # An asset gets one vote per channel, regardless of chunk count.
            seen = set()
            for chunk_id, raw_score in ranking:
                asset_id = matched[chunk_id]["asset_id"]
                if asset_id in seen:
                    continue
                seen.add(asset_id)
                fused[asset_id] = fused.get(asset_id, 0) + 1 / (60 + len(seen))
                channels.setdefault(asset_id, {})[channel] = {"score": round(raw_score, 5), "chunk": matched[chunk_id]}
        results = []
        for asset_id, score in sorted(fused.items(), key=lambda pair: pair[1], reverse=True)[:limit]:
            evidence = channels[asset_id]
            best = evidence.get("keyword") or evidence.get("text") or evidence.get("visual")
            results.append(self._result(asset_id, best["chunk"], evidence, score))
        return {"query": query, "results": results, "warnings": warnings,
                "filters": {"after": after, "before": before, "kind": kind},
                "seconds": round(time.perf_counter() - started, 3)}

    def _result(self, asset_id: str, chunk: dict | None, channels: dict, score: float) -> dict:
        item = self.store.asset(asset_id)
        metadata = item["metadata"]
        return {"id": asset_id, "name": item["name"], "kind": item["kind"], "paths": item["paths"],
                "captured_at": item["captured_at"], "size": item["size"],
                "text": (chunk["text"] if chunk else " ".join(c["text"] for c in item["chunks"]))[:1000],
                "start": chunk.get("start") if chunk else None, "end": chunk.get("end") if chunk else None,
                "score": round(score, 6), "channels": list(channels), "metadata": metadata,
                "available": any(Path(p).is_file() for p in item["paths"])}

    def refine(self, query: str, budget_seconds: float = 5, **filters) -> dict:
        """A soft compute budget: start bounded OCR jobs; don't kill in-flight inference."""
        started = time.perf_counter()
        initial = self.search(query, **filters)
        candidates = [item for item in initial["results"] if item["kind"] == "image" and
                      (item["metadata"].get("ocr_confidence") or 0) < 0.9 and item["available"]
                      and not item["metadata"].get("refined")]
        completed = []
        for candidate in candidates:
            if time.perf_counter() - started >= budget_seconds:
                break
            path = next(Path(p) for p in candidate["paths"] if Path(p).is_file())
            with self.write_lock:
                image = open_image(path)
                if max(image.size) <= 2400:
                    image = image.resize((image.width * 2, image.height * 2))
                lines = self.extractors.ocr(image)
                # Reindex only if OCR confidence improves; preserve existing grounding boxes.
                confidence = float(np.mean([line["confidence"] for line in lines])) if lines else 0
                if confidence > (candidate["metadata"].get("ocr_confidence") or 0):
                    ratio = open_image(path).width / image.width
                    for line in lines:
                        line["box"] = [round(v * ratio) for v in line["box"]]
                    self._replace_ocr(candidate["id"], lines, confidence)
                    completed.append(candidate["id"])
        final = self.search(query, **filters) if completed else initial
        final["refinement"] = {"completed": completed, "budget_seconds": budget_seconds,
                               "elapsed_seconds": round(time.perf_counter() - started, 3),
                               "policy": "low-confidence OCR; soft budget includes search; one in-flight task may exceed it"}
        return final

    def _replace_ocr(self, asset_id: str, lines: list[dict], confidence: float):
        chunks = text_chunks(" ".join(line["text"] for line in lines))
        vectors = self.embeddings.text([chunk["text"] for chunk in chunks])
        with self.store.connection() as db:
            # Preserve the existing visual vector while replacing text and its FTS entries.
            visual = db.execute("SELECT v.* FROM vectors v JOIN chunks c ON c.id=v.chunk_id WHERE c.asset_id=? AND v.space='visual'", (asset_id,)).fetchone()
            db.execute("DELETE FROM chunks WHERE asset_id=?", (asset_id,))
            for i, chunk in enumerate(chunks or [{"text": ""}]):
                chunk_id = f"{asset_id}:{i}"
                db.execute("INSERT INTO chunks VALUES(?,?,?,?,?,?)", (chunk_id, asset_id, chunk["text"], None, None, i))
                if i < len(vectors):
                    db.execute("INSERT INTO vectors VALUES(?,?,?,?,?,?,?)", (chunk_id, "text", self.workspace.settings.text_model, len(vectors[i]), *quantize(vectors[i])))
            if visual:
                db.execute("INSERT INTO vectors VALUES(?,?,?,?,?,?,?)", tuple(visual))
            metadata = json.loads(db.execute("SELECT metadata FROM assets WHERE id=?", (asset_id,)).fetchone()[0])
            metadata.update(ocr_lines=lines, ocr_confidence=confidence, refined=True)
            db.execute("UPDATE assets SET metadata=? WHERE id=?", (json.dumps(metadata), asset_id))

    def prune(self) -> int:
        with self.store.connection() as db:
            missing = [row[0] for row in db.execute("SELECT path FROM locations") if not Path(row[0]).is_file()]
            db.executemany("DELETE FROM locations WHERE path=?", ((path,) for path in missing))
            db.execute("DELETE FROM assets WHERE id NOT IN (SELECT asset_id FROM locations)")
        return len(missing)
