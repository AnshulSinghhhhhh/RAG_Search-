from __future__ import annotations

import threading
import numpy as np
from .config import Workspace


def quantize(vector: np.ndarray) -> tuple[bytes, float, float]:
    vector = np.asarray(vector, dtype=np.float32).reshape(-1)
    if not vector.size or not np.isfinite(vector).all():
        raise ValueError("The embedding model returned an invalid vector.")
    scale = float(np.max(np.abs(vector))) / 127 or 1.0
    packed = np.clip(np.rint(vector / scale), -127, 127).astype(np.int8)
    return packed.tobytes(), scale, float(np.linalg.norm(packed.astype(np.float32)))


class Embeddings:
    """Lazily loaded real ONNX models; no synthetic semantic fallback."""
    def __init__(self, workspace: Workspace):
        self.workspace = workspace
        self.models: dict = {}
        self.lock = threading.RLock()

    def _model(self, space: str):
        with self.lock:
            if space not in self.models:
                from fastembed import TextEmbedding, ImageEmbedding
                config = self.workspace.settings
                names = {"text": config.text_model, "visual": config.vision_model,
                         "visual_query": config.vision_text_model}
                cls = ImageEmbedding if space == "visual" else TextEmbedding
                self.models[space] = cls(model_name=names[space], cache_dir=str(self.workspace.cache),
                                         threads=config.threads, providers=["CPUExecutionProvider"])
            return self.models[space]

    def text(self, texts: list[str], query: bool = False) -> list[np.ndarray]:
        if not texts:
            return []
        with self.lock:
            model = self._model("text")
            method = model.query_embed if query else model.embed
            return list(method(texts))

    def image(self, path: str) -> np.ndarray:
        with self.lock:
            return next(iter(self._model("visual").embed([path])))

    def visual_query(self, text: str) -> np.ndarray:
        with self.lock:
            # CLIP's paired text model shares the vision model's vector space.
            return next(iter(self._model("visual_query").embed([text])))
