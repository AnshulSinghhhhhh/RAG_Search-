from __future__ import annotations

import hashlib
import threading
from pathlib import Path

import numpy as np
from PIL import Image, ImageChops, ImageOps

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff"}
AUDIO_EXTENSIONS = {".wav", ".mp3", ".m4a", ".ogg", ".flac", ".aac", ".opus"}
TEXT_EXTENSIONS = {".txt", ".md", ".csv", ".json", ".log", ".rst"}


def modality(path: Path) -> str | None:
    ext = path.suffix.lower()
    return "image" if ext in IMAGE_EXTENSIONS else "audio" if ext in AUDIO_EXTENSIONS else "text" if ext in TEXT_EXTENSIONS else None


def file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def open_image(path: Path) -> Image.Image:
    with Image.open(path) as original:
        return ImageOps.exif_transpose(original).convert("RGB")


def dhash(image: Image.Image) -> str:
    pixels = np.asarray(image.convert("L").resize((9, 8)))
    bits = pixels[:, 1:] > pixels[:, :-1]
    return f"{int.from_bytes(np.packbits(bits).tobytes(), 'big'):016x}"


def distance(left: str, right: str) -> int:
    return (int(left, 16) ^ int(right, 16)).bit_count()


def intersection(left: list | tuple, right: list | tuple) -> bool:
    return left[0] < right[2] and left[2] > right[0] and left[1] < right[3] and left[3] > right[1]


def changed_region(previous: Image.Image, current: Image.Image) -> tuple | None:
    if previous.size != current.size:
        return (0, 0, current.width, current.height)
    # Native-resolution, exact differences preserve even a one-digit price edit.
    box = ImageChops.difference(previous, current).getbbox()
    if not box:
        return None
    return (max(0, box[0] - 24), max(0, box[1] - 24),
            min(current.width, box[2] + 24), min(current.height, box[3] + 24))


class Extractors:
    def __init__(self, workspace):
        self.workspace = workspace
        self._ocr = None
        self._whisper = None
        self.lock = threading.RLock()

    def ocr(self, image: Image.Image) -> list[dict]:
        with self.lock:
            if self._ocr is None:
                from rapidocr import RapidOCR
                self._ocr = RapidOCR(params={"Global.log_level": "error",
                                            "EngineConfig.onnxruntime.intra_op_num_threads": self.workspace.settings.threads})
            result = self._ocr(np.asarray(image))
        if result.txts is None:
            return []
        lines = []
        for polygon, text, confidence in zip(result.boxes, result.txts, result.scores):
            points = np.asarray(polygon)
            lines.append({"text": text, "confidence": float(confidence),
                          "box": [int(points[:, 0].min()), int(points[:, 1].min()),
                                  int(points[:, 0].max()) + 1, int(points[:, 1].max()) + 1]})
        return lines

    def image_text(self, image: Image.Image, previous_image: Image.Image | None = None,
                   previous_lines: list[dict] | None = None, force: bool = False) -> tuple[list[dict], dict]:
        if previous_image is None or force:
            return self.ocr(image), {"ocr_strategy": "full", "ocr_area_fraction": 1.0, "reused_lines": 0}
        region = changed_region(previous_image, image)
        if region is None:
            return previous_lines or [], {"ocr_strategy": "reuse", "ocr_area_fraction": 0.0,
                                          "reused_lines": len(previous_lines or [])}
        # Include entire affected text lines so cropping never cuts a price in half.
        for line in previous_lines or []:
            if intersection(region, line["box"]):
                box = line["box"]
                region = (min(region[0], max(0, box[0] - 16)), min(region[1], max(0, box[1] - 16)),
                          max(region[2], min(image.width, box[2] + 16)), max(region[3], min(image.height, box[3] + 16)))
        fraction = (region[2] - region[0]) * (region[3] - region[1]) / (image.width * image.height)
        if fraction > 0.45:
            return self.ocr(image), {"ocr_strategy": "full", "ocr_area_fraction": 1.0, "reused_lines": 0}
        retained = [line for line in previous_lines or [] if not intersection(region, line["box"])]
        fresh = self.ocr(image.crop(region))
        for line in fresh:
            box = line["box"]
            line["box"] = [box[0] + region[0], box[1] + region[1], box[2] + region[0], box[3] + region[1]]
        return sorted(retained + fresh, key=lambda line: (line["box"][1], line["box"][0])), {
            "ocr_strategy": "delta", "ocr_area_fraction": round(fraction, 5), "reused_lines": len(retained)}

    def audio(self, path: Path) -> tuple[list[dict], dict]:
        try:
            from faster_whisper import WhisperModel
        except ImportError as exc:
            raise RuntimeError('Audio support is not installed. Run: pip install -e ".[audio]"') from exc
        with self.lock:
            config = self.workspace.settings
            if self._whisper is None:
                self._whisper = WhisperModel(config.audio_model, device="cpu", compute_type="int8",
                                             cpu_threads=config.threads, download_root=str(self.workspace.cache / "whisper"))
            segments, info = self._whisper.transcribe(str(path), vad_filter=True, beam_size=3,
                                                     language=config.audio_language)
            segments = [{"text": segment.text.strip(), "start": segment.start, "end": segment.end,
                         "confidence": float(np.exp(segment.avg_logprob))} for segment in segments if segment.text.strip()]
        return segments, {"duration": info.duration, "speech_seconds": info.duration_after_vad,
                          "language": info.language, "segments": segments}


def text_chunks(text: str, words_per_chunk: int = 140, overlap: int = 20) -> list[dict]:
    words = text.split()
    chunks = []
    for start in range(0, len(words), words_per_chunk - overlap):
        chunks.append({"text": " ".join(words[start:start + words_per_chunk]), "start": None, "end": None})
        if start + words_per_chunk >= len(words):
            break
    return chunks


def audio_chunks(segments: list[dict]) -> list[dict]:
    chunks, current = [], []
    for segment in segments:
        if current and (segment["end"] - current[0]["start"] > 30 or
                        segment["start"] - current[-1]["end"] > 2):
            chunks.append({"text": " ".join(s["text"] for s in current),
                           "start": current[0]["start"], "end": current[-1]["end"]})
            current = []
        current.append(segment)
    if current:
        chunks.append({"text": " ".join(s["text"] for s in current), "start": current[0]["start"], "end": current[-1]["end"]})
    return chunks
