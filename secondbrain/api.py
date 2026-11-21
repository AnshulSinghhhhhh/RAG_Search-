from __future__ import annotations

import json
import os
import secrets
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import urlparse

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .answers import answer
from .engine import Brain

WEB = Path(__file__).parent / "web"


class IndexRequest(BaseModel):
    path: str = Field(min_length=1, max_length=4096)
    force: bool = False


class SearchRequest(BaseModel):
    query: str = Field(default="", max_length=2000)
    kind: str | None = None
    folder: str | None = None
    limit: int = Field(default=30, ge=1, le=100)
    after: float | None = None
    before: float | None = None
    lexical_only: bool = False
    refine: bool = False


def create_app(home: str | Path | None = None, brain: Brain | None = None) -> FastAPI:
    brain = brain or Brain(home)
    executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="brain-index")
    jobs: dict[str, dict] = {}
    jobs_lock = threading.RLock()
    token = secrets.token_urlsafe(32)

    @asynccontextmanager
    async def lifespan(app):
        yield
        executor.shutdown(wait=False, cancel_futures=True)

    app = FastAPI(title="Second Brain", version="0.1.0", lifespan=lifespan)
    app.state.brain = brain

    @app.middleware("http")
    async def local_only(request: Request, call_next):
        host = request.url.hostname
        if host not in {"127.0.0.1", "localhost", "::1", "testserver"}:
            return JSONResponse({"detail": "This app accepts localhost requests only."}, status_code=403)
        origin = request.headers.get("origin")
        if origin and urlparse(origin).netloc != request.headers.get("host"):
            return JSONResponse({"detail": "Cross-origin requests are not allowed."}, status_code=403)
        if request.method not in {"GET", "HEAD", "OPTIONS"} and request.headers.get("x-brain-token") != token:
            return JSONResponse({"detail": "Reload the app to refresh your local session."}, status_code=403)
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Content-Security-Policy"] = "default-src 'self'; img-src 'self' data:; media-src 'self'; style-src 'self'; script-src 'self'; font-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
        return response

    @app.get("/", response_class=HTMLResponse)
    def index():
        return HTMLResponse(WEB.joinpath("index.html").read_text(encoding="utf-8").replace("__SESSION_TOKEN__", token),
                            headers={"Cache-Control": "no-store"})

    @app.get("/api/status")
    def status():
        return {**brain.store.stats(), "home": str(brain.workspace.home),
                "settings": vars(brain.workspace.settings), "supported": ["image", "audio", "text"]}

    @app.post("/api/search")
    def search(body: SearchRequest):
        if body.kind not in {None, "image", "audio", "text"}:
            raise HTTPException(400, "Choose image, audio, or text.")
        arguments = body.model_dump(exclude={"refine"})
        try:
            return brain.refine(**arguments) if body.refine else brain.search(**arguments)
        except Exception as exc:
            raise HTTPException(400, str(exc)) from exc

    @app.post("/api/ask")
    def ask(body: SearchRequest):
        try:
            return answer(brain, body.query, brain.workspace.settings.ollama_model or None,
                          kind=body.kind, folder=body.folder, after=body.after, before=body.before,
                          lexical_only=body.lexical_only)
        except Exception as exc:
            raise HTTPException(400, str(exc)) from exc

    def run_job(job_id: str, path: str, force: bool):
        with jobs_lock:
            jobs[job_id].update(state="running", started=time.time())
        def progress(value):
            with jobs_lock:
                jobs[job_id].update(value)
        try:
            report = brain.ingest(path, force, progress)
            with jobs_lock:
                jobs[job_id].update(state="complete", current=report["total"], report=report)
        except Exception as exc:
            with jobs_lock:
                jobs[job_id].update(state="error", error=str(exc))

    @app.post("/api/index", status_code=202)
    def start_index(body: IndexRequest):
        path = Path(body.path).expanduser().resolve()
        if not path.exists():
            raise HTTPException(400, "That path does not exist on this computer. Check it and try again.")
        with jobs_lock:
            if any(job["state"] in {"queued", "running"} for job in jobs.values()):
                raise HTTPException(409, "Indexing is already running. Wait for it to finish before adding another path.")
            job_id = secrets.token_hex(8)
            jobs[job_id] = {"id": job_id, "state": "queued", "current": 0, "total": 0, "path": str(path)}
            executor.submit(run_job, job_id, str(path), body.force)
        return {"job_id": job_id}

    @app.get("/api/jobs/{job_id}")
    def job_status(job_id: str):
        with jobs_lock:
            if job_id not in jobs:
                raise HTTPException(404, "Indexing job not found. It may belong to an earlier server session.")
            return dict(jobs[job_id])

    @app.get("/api/jobs")
    def active_jobs():
        with jobs_lock:
            return list(jobs.values())[-10:]

    @app.get("/api/folders")
    def folders(path: str | None = None):
        if not path:
            roots = [str(Path.home())]
            if os.name == "nt":
                roots += [f"{letter}:\\" for letter in "ABCDEFGHIJKLMNOPQRSTUVWXYZ" if Path(f"{letter}:\\").is_dir()]
            return {"path": None, "parent": None, "folders": roots}
        root = Path(path).expanduser().resolve()
        if not root.is_dir():
            raise HTTPException(400, "This folder is not available.")
        try:
            children = sorted(str(p) for p in root.iterdir() if p.is_dir() and not p.name.startswith(".") and not p.is_symlink())[:200]
        except OSError as exc:
            raise HTTPException(403, "This folder cannot be read. Choose another folder.") from exc
        return {"path": str(root), "parent": str(root.parent) if root != root.parent else None, "folders": children}

    @app.get("/api/assets/{asset_id}")
    def asset(asset_id: str):
        item = brain.store.asset(asset_id)
        if not item:
            raise HTTPException(404, "This memory is no longer indexed.")
        return item

    @app.get("/api/files/{asset_id}")
    def source_file(asset_id: str):
        item = brain.store.asset(asset_id)
        if not item:
            raise HTTPException(404, "This memory is no longer indexed.")
        path = next((Path(p) for p in item["paths"] if Path(p).is_file()), None)
        if not path:
            raise HTTPException(404, "The original file was moved or removed. Index its new location.")
        return FileResponse(path, media_type="text/plain; charset=utf-8" if item["kind"] == "text" else None)

    @app.get("/api/thumbnails/{asset_id}")
    def thumbnail(asset_id: str):
        if not brain.store.asset(asset_id):
            raise HTTPException(404, "This memory is no longer indexed.")
        path = brain.workspace.thumbnails / f"{asset_id}.webp"
        if not path.is_file():
            raise HTTPException(404, "No preview is available for this file.")
        return FileResponse(path, media_type="image/webp")

    @app.delete("/api/sources")
    def forget_source(body: IndexRequest):
        path = Path(body.path).expanduser().resolve()
        with brain.write_lock:
            removed = brain.store.remove(path)
            with brain.store.connection() as db:
                db.execute("DELETE FROM sources WHERE path=?", (str(path),))
        return {"removed_locations": removed, "original_files_deleted": False}

    app.mount("/static", StaticFiles(directory=WEB), name="static")
    return app
