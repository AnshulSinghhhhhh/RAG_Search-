"""Run the frozen 0.2 field cases through real OCR and hybrid retrieval."""

import argparse
from hashlib import sha256
import json
from pathlib import Path
import platform
import statistics
from tempfile import TemporaryDirectory
import time
from importlib.metadata import version

from PIL import Image, ImageDraw, ImageFont

from secondbrain.answers import answer
from secondbrain.engine import Brain


ROOT = Path(__file__).resolve().parents[1]
FONT = ROOT / "secondbrain/web/fonts/DM-Sans.ttf"


def create_image(case, path, index):
    image = Image.new("RGB", (900, 400 + index * 4), (246, 247, 243))
    draw = ImageDraw.Draw(image)
    draw.text((60, 42), case["lines"][0], fill="#172920", font=ImageFont.truetype(str(FONT), 42))
    draw.line((60, 112, 840, 112), fill="#68776c", width=2)
    for row, content in enumerate(case["lines"][1:]):
        draw.text((60, 144 + row * 68), content, fill="#172920", font=ImageFont.truetype(str(FONT), 35))
    image.save(path)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--cache", type=Path, help="Use existing downloaded models")
    args = parser.parse_args()
    if args.output.exists():
        parser.error("Choose a new output path to preserve the recorded run.")
    manifest = Path(__file__).with_name("field_cases.json").read_bytes()
    cases = json.loads(manifest)
    rows = []
    with TemporaryDirectory(prefix="secondbrain-field-eval-") as directory:
        root = Path(directory)
        brain = Brain(root / "collection")
        if args.cache:
            brain.workspace.cache = args.cache.resolve()
        assets = {}
        for index, case in enumerate(cases):
            path = root / (case["id"] + ".png")
            create_image(case, path, index)
            assets[case["id"]] = brain.ingest_file(path)["id"]
        for case in cases:
            for refine in (False, True):
                started = time.perf_counter()
                result = answer(brain, case["query"], refine=refine)
                seconds = time.perf_counter() - started
                citations = result["citations"]
                value = citations[0]["value"] if result["evidence_status"] == "supported" else None
                source_ok = value is None or citations[0]["asset_id"] == assets[case["id"]]
                expected_status = "insufficient" if case["expected"] is None else "supported"
                rows.append({"id": case["id"], "refine": refine, "expected": case["expected"], "value": value,
                             "status": result["evidence_status"], "citations": citations,
                             "attempts": result.get("refinement", {}).get("attempted", 0),
                             "seconds": round(seconds, 4), "warnings": result["warnings"],
                             "passed": result["evidence_status"] == expected_status and value == case["expected"] and source_ok})
    summaries = {}
    for refine in (False, True):
        group = [row for row in rows if row["refine"] == refine]
        positives = [row for row in group if row["expected"] is not None]
        negatives = [row for row in group if row["expected"] is None]
        summaries["retry" if refine else "default"] = {
            "cases": len(group), "positive_exact_and_cited": sum(row["passed"] for row in positives),
            "positive_cases": len(positives), "negative_abstentions": sum(row["passed"] for row in negatives),
            "negative_cases": len(negatives), "ocr_attempts": sum(row["attempts"] for row in group),
            "p95_seconds": round(statistics.quantiles([row["seconds"] for row in group], n=100, method="inclusive")[94], 4),
        }
    result = {"description": "Frozen synthetic image families separate from the original playground.",
              "manifest_sha256": sha256(manifest).hexdigest(), "python": platform.python_version(),
              "platform": platform.system(), "packages": {p: version(p) for p in ("rapidocr", "fastembed", "onnxruntime", "Pillow")},
              "summary": summaries, "cases": rows}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as stream:
        json.dump(result, stream, indent=2, ensure_ascii=False)
        stream.write("\n")
    print(json.dumps(summaries, indent=2))
    return int(not all(row["passed"] for row in rows))


if __name__ == "__main__":
    raise SystemExit(main())
