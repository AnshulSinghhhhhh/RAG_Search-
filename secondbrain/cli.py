from __future__ import annotations

import argparse
import importlib.util
import json
import sys
import time
import webbrowser
from datetime import datetime, timedelta
from pathlib import Path

from . import __version__
from .answers import answer
from .engine import Brain
from .extract import modality


def emit(value, as_json=False):
    if as_json or isinstance(value, (dict, list)):
        print(json.dumps(value, indent=2, ensure_ascii=True))
    else:
        print(value)


def date_argument(value: str | None, inclusive_end=False):
    if not value:
        return None
    stamp = datetime.fromisoformat(value).astimezone()
    if inclusive_end:
        stamp += timedelta(days=1)
    return stamp.timestamp()


def parser():
    root = argparse.ArgumentParser(prog="brain", description="Your screenshots, receipts, and voice notes. Searchable locally.")
    root.add_argument("--home", help="Collection data directory (or set SECONDBRAIN_HOME)")
    root.add_argument("--version", action="version", version=__version__)
    commands = root.add_subparsers(dest="command", required=True)
    init = commands.add_parser("init", help="Create a local collection and configure processing")
    init.add_argument("--no-vision", action="store_true", help="Skip visual models; OCR/text search still works")
    init.add_argument("--no-ocr", action="store_true")
    init.add_argument("--audio-model", choices=["tiny", "base", "small", "medium"], default="base")
    init.add_argument("--language", help="Whisper language, e.g. en or hi; default: detect automatically")
    init.add_argument("--ollama-model", default="", help="Optional installed local Ollama model for ask")
    index = commands.add_parser("index", aliases=["add"], help="Embed one file or recursively index a selected folder")
    index.add_argument("path")
    index.add_argument("--force", action="store_true", help="Reprocess even cached files")
    index.add_argument("--json", action="store_true")
    for name, description in [("search", "Search visual, semantic, and keyword indexes"), ("ask", "Answer from source excerpts, optionally using local Ollama")]:
        search = commands.add_parser(name, help=description)
        search.add_argument("query")
        search.add_argument("--kind", choices=["image", "audio", "text"])
        search.add_argument("--folder", help="Restrict to a selected source folder")
        search.add_argument("--after", metavar="YYYY-MM-DD")
        search.add_argument("--before", metavar="YYYY-MM-DD", help="Inclusive end date")
        search.add_argument("--lexical-only", action="store_true", help="Search extracted keywords without loading embedding models")
        search.add_argument("--json", action="store_true")
        if name == "search":
            search.add_argument("--limit", type=int, default=10)
            search.add_argument("--refine", action="store_true", help="Retry low-confidence image OCR on relevant results")
            search.add_argument("--budget", type=float, default=5.0, help="Soft refinement budget in seconds")
        else:
            search.add_argument("--model", help="Installed Ollama model; omit for quoted evidence")
            search.add_argument("--refine", action="store_true", help="Retry OCR for matching images")
    sources = commands.add_parser("sources", help="List, add, or remove watched/indexed folder sources")
    source_commands = sources.add_subparsers(dest="source_command", required=True)
    source_commands.add_parser("list")
    for verb in ("add", "remove"):
        source_commands.add_parser(verb).add_argument("path")
    commands.add_parser("sync", help="Index additions and changes in all saved source folders")
    repair = commands.add_parser("repair", help="Refresh image and audio evidence created by older versions")
    repair.add_argument("--dry-run", action="store_true", help="Count affected assets without reindexing")
    watch = commands.add_parser("watch", help="Watch chosen folders and incrementally index stable file changes")
    watch.add_argument("paths", nargs="*", help="Folders, or omit to watch saved sources")
    serve = commands.add_parser("serve", help="Open the local visual interface")
    serve.add_argument("--port", type=int, default=8765)
    serve.add_argument("--no-browser", action="store_true")
    status = commands.add_parser("status", help="Show real collection, processing, and storage statistics")
    status.add_argument("--json", action="store_true")
    commands.add_parser("doctor", help="Check local environment and optional audio support")
    forget = commands.add_parser("forget", help="Remove a file or folder from the index; preserve originals")
    forget.add_argument("path")
    commands.add_parser("prune", help="Forget indexed locations whose original files no longer exist")
    models = commands.add_parser("models", help="Download local models in advance for offline use")
    models.add_argument("--audio", action="store_true")
    benchmark = commands.add_parser("benchmark", help="Run labeled search scenarios without indexing their answer labels")
    benchmark.add_argument("scenarios")
    benchmark.add_argument("--output", help="Write the actual results as JSON")
    return root


def watch_folders(brain, paths):
    import queue
    import threading
    from watchdog.events import FileSystemEventHandler
    from watchdog.observers import Observer
    folders = paths or [source["path"] for source in brain.store.stats()["sources"]]
    if not folders:
        raise ValueError('No sources configured. Run: brain sources add "C:\\path\\to\\folder"')
    pending = {}
    guard = threading.Lock()
    class Changes(FileSystemEventHandler):
        def on_any_event(self, event):
            if event.is_directory or event.event_type not in {"created", "modified", "moved"}:
                return
            path = Path(getattr(event, "dest_path", "") or event.src_path).resolve()
            skipped = {"node_modules", "__pycache__", "venv"}
            relative_parts = next((path.relative_to(Path(folder).expanduser().resolve()).parts
                                   for folder in folders if Path(folder).expanduser().resolve() in path.parents), ())
            ignored = any(part.startswith(".") or part in skipped for part in relative_parts[:-1])
            if modality(path) and not ignored and brain.workspace.home not in path.parents:
                with guard:
                    pending[str(path)] = time.monotonic()
    observer = Observer()
    for folder in folders:
        brain.add_source(folder)
        emit(brain.ingest(folder))
        observer.schedule(Changes(), str(Path(folder).expanduser().resolve()), recursive=True)
    observer.start()
    print("Watching selected folders. Press Ctrl+C to stop. Deleted locations can be removed with brain prune.")
    try:
        while True:
            with guard:
                ready = [p for p, stamp in pending.items() if time.monotonic() - stamp > 1.5]
                for path in ready:
                    pending.pop(path, None)
            for path in ready:
                if not Path(path).is_file():
                    continue
                try:
                    emit(brain.ingest_file(path))
                except Exception as exc:
                    print(f"Could not index {path}: {exc}", file=sys.stderr)
            time.sleep(0.3)
    except KeyboardInterrupt:
        pass
    finally:
        observer.stop()
        observer.join()


def run_benchmark(brain, path):
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    results = []
    for scenario in payload["scenarios"]:
        response = brain.search(scenario["query"], limit=5, kind=scenario.get("kind"))
        filenames = [Path(p).name for item in response["results"] for p in item["paths"]]
        expected = scenario.get("expected_files", [])
        # No-answer queries are reported separately: weak similarity can still return candidates.
        hit = any(name in filenames for name in expected) if expected else not response["results"]
        results.append({"id": scenario["id"], "query": scenario["query"], "hit_at_5": hit,
                        "expected_files": expected, "retrieved_files": filenames,
                        "seconds": response["seconds"], "warnings": response["warnings"]})
    answerable = [r for r in results if r["expected_files"]]
    return {"scenarios": results, "answerable_count": len(answerable),
            "hit_rate_at_5": sum(r["hit_at_5"] for r in answerable) / len(answerable) if answerable else None,
            "note": "Small synthetic smoke benchmark; not a production accuracy or speed claim.",
            "storage": brain.store.stats()}


def main(argv=None) -> int:
    arguments = parser().parse_args(argv)
    try:
        brain = Brain(arguments.home)
        command = arguments.command
        if command == "init":
            settings = brain.workspace.settings
            settings.vision, settings.ocr = not arguments.no_vision, not arguments.no_ocr
            settings.audio_model, settings.audio_language = arguments.audio_model, arguments.language
            settings.ollama_model = arguments.ollama_model
            brain.workspace.save()
            print(f"Collection ready: {brain.workspace.home}\nModels download on first use; originals stay in place.")
        elif command in {"index", "add"}:
            def progress(value):
                if not arguments.json:
                    print(f"[{value['current'] + 1}/{value['total']}] {value['path']}", flush=True)
            report = brain.ingest(arguments.path, arguments.force, progress)
            emit(report)
            return 1 if report["errors"] else 0
        elif command in {"search", "ask"}:
            filters = {"kind": arguments.kind, "folder": arguments.folder,
                       "after": date_argument(arguments.after), "before": date_argument(arguments.before, True),
                       "lexical_only": arguments.lexical_only}
            if command == "ask":
                result = answer(brain, arguments.query, arguments.model or brain.workspace.settings.ollama_model or None,
                                refine=arguments.refine, **filters)
            else:
                if not 1 <= arguments.limit <= 100 or not 0 <= arguments.budget <= 120:
                    raise ValueError("Use --limit between 1 and 100 and --budget between 0 and 120 seconds.")
                result = brain.refine(arguments.query, arguments.budget, limit=arguments.limit, **filters) if arguments.refine else brain.search(arguments.query, limit=arguments.limit, **filters)
            if arguments.json:
                emit(result)
            else:
                if "answer" in result:
                    print(result["answer"] + "\n")
                for number, citation in enumerate(result.get("citations", []), 1):
                    print(f"[{number}] {citation['source']}: {citation['text']}")
                for i, item in enumerate(result["results"], 1):
                    stamp = f" @{item['start']:.1f}s" if item["start"] is not None else ""
                    print(f"{i}. [{item['kind']}]{stamp} {item['name']}\n   {item['paths'][0]}\n   {item['text'][:220]}\n")
                print(f"{len(result['results'])} results in {result['seconds']:.3f}s")
                for warning in result["warnings"]:
                    print(f"Warning: {warning}", file=sys.stderr)
        elif command == "sources":
            if arguments.source_command == "list":
                emit(brain.store.stats()["sources"])
            elif arguments.source_command == "add":
                print(f"Source added: {brain.add_source(arguments.path)}\nRun brain sync to index it.")
            else:
                path = Path(arguments.path).expanduser().resolve()
                with brain.store.connection() as db:
                    db.execute("DELETE FROM sources WHERE path=?", (str(path),))
                print("Source removed. Existing memories remain searchable; use brain forget to remove them.")
        elif command == "sync":
            reports = [brain.ingest(source["path"]) for source in brain.store.stats()["sources"]]
            emit(reports)
            return int(any(report["errors"] for report in reports))
        elif command == "repair":
            report = brain.repair(arguments.dry_run)
            emit(report)
            return int(bool(report["errors"] or report["unavailable"]))
        elif command == "watch":
            watch_folders(brain, arguments.paths)
        elif command == "serve":
            import uvicorn
            from .api import create_app
            if not 1 <= arguments.port <= 65535:
                raise ValueError("Choose a port between 1 and 65535.")
            url = f"http://127.0.0.1:{arguments.port}"
            print(f"Second Brain: {url}\nCollection: {brain.workspace.home}", flush=True)
            if not arguments.no_browser:
                import threading
                threading.Timer(1.0, lambda: webbrowser.open(url)).start()
            uvicorn.run(create_app(brain=brain), host="127.0.0.1", port=arguments.port, log_level="warning")
        elif command == "status":
            emit({"home": str(brain.workspace.home), **brain.store.stats()})
        elif command == "doctor":
            print(f"Python {sys.version.split()[0]} | collection {brain.workspace.home}")
            for module in ["fastembed", "rapidocr", "onnxruntime", "watchdog", "faster_whisper"]:
                print(f"{module}: {'installed' if importlib.util.find_spec(module) else 'not installed'}")
            print("Model loading is checked by brain models. No models are downloaded by doctor.")
        elif command == "forget":
            removed = brain.store.remove(Path(arguments.path).expanduser().resolve())
            print(f"Forgot {removed} indexed locations. Original files were preserved.")
        elif command == "prune":
            print(f"Removed {brain.prune()} missing locations from the index.")
        elif command == "models":
            brain.embeddings.text(["Model warmup"])
            if brain.workspace.settings.vision:
                brain.embeddings._model("visual")
                brain.embeddings.visual_query("A photograph")
            if brain.workspace.settings.ocr:
                from PIL import Image
                brain.extractors.ocr(Image.new("RGB", (300, 100), "white"))
            if arguments.audio:
                from faster_whisper import WhisperModel
                WhisperModel(brain.workspace.settings.audio_model, device="cpu", compute_type="int8", download_root=str(brain.workspace.cache / "whisper"))
            print("Selected models are cached for offline processing.")
        elif command == "benchmark":
            result = run_benchmark(brain, arguments.scenarios)
            if arguments.output:
                Path(arguments.output).write_text(json.dumps(result, indent=2), encoding="utf-8")
            emit(result)
        return 0
    except KeyboardInterrupt:
        return 130
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
