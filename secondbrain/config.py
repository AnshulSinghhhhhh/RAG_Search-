from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass
class Settings:
    text_model: str = "BAAI/bge-small-en-v1.5"
    vision_model: str = "Qdrant/clip-ViT-B-32-vision"
    vision_text_model: str = "Qdrant/clip-ViT-B-32-text"
    vision: bool = True
    ocr: bool = True
    audio_model: str = "base"
    audio_language: str | None = None
    threads: int = 4
    max_file_mb: int = 250
    ollama_model: str = ""


def default_home() -> Path:
    if os.environ.get("SECONDBRAIN_HOME"):
        return Path(os.environ["SECONDBRAIN_HOME"]).expanduser().resolve()
    if os.name == "nt":
        return Path(os.environ.get("LOCALAPPDATA", Path.home())) / "SecondBrain"
    return Path.home() / ".local" / "share" / "secondbrain"


class Workspace:
    def __init__(self, home: str | Path | None = None):
        self.home = Path(home).expanduser().resolve() if home else default_home()
        self.home.mkdir(parents=True, exist_ok=True)
        self.cache = self.home / "models"
        self.thumbnails = self.home / "thumbnails"
        self.thumbnails.mkdir(exist_ok=True)
        self.config_path = self.home / "config.json"
        self.settings = Settings()
        if self.config_path.exists():
            raw = json.loads(self.config_path.read_text(encoding="utf-8"))
            valid = asdict(self.settings)
            self.settings = Settings(**{k: v for k, v in raw.items() if k in valid})

    def save(self) -> None:
        # Atomic replacement avoids a truncated config if a process is interrupted.
        temporary = self.config_path.with_suffix(".tmp")
        temporary.write_text(json.dumps(asdict(self.settings), indent=2), encoding="utf-8")
        temporary.replace(self.config_path)

    def index_signature(self) -> str:
        values = asdict(self.settings)
        return json.dumps({"pipeline_version": 1, **{k: values[k] for k in (
            "text_model", "vision_model", "vision", "ocr", "audio_model", "audio_language"
        )}}, sort_keys=True)
