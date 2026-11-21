"""Isolate duplicate reuse from delta OCR; evaluate the full-OCR collection."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
from run_experiments import ROOT, Workspace, Embeddings, InstrumentedExtractors, Brain, open_image, timed, save, evaluate, aggregate


class FullOCRDedupBrain(Brain):
    def _near_image(self, image, image_hash):
        return None


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--output",default=str(ROOT/"research/results/2026-11-20"))
    args=parser.parse_args()
    out=Path(args.output).resolve()
    if (out/"ingest_control.json").exists(): raise SystemExit("Preserve existing control results.")
    workspace=Workspace(out/"collections/control-model-owner")
    workspace.cache=ROOT/".secondbrain/models"
    embeddings=Embeddings(workspace)
    extractors=InstrumentedExtractors(workspace)
    fixtures=ROOT/"playground/inbox"
    embeddings.text(["warmup"])
    embeddings.image(str(fixtures/"screenshots/capture_001.png"))
    embeddings.visual_query("white sneakers")
    extractors.ocr(open_image(fixtures/"screenshots/capture_001.png"))
    extractors.audio(fixtures/"voice/memo_001.wav")
    rows=[]
    for rep in range(3):
        order=("dedup_full_ocr","dedup_delta_ocr") if rep%2==0 else ("dedup_delta_ocr","dedup_full_ocr")
        for mode in order:
            cls=FullOCRDedupBrain if mode=="dedup_full_ocr" else Brain
            brain=cls(out/f"collections/control-{mode}-{rep}",embeddings=embeddings,extractors=extractors)
            index=len(extractors.calls)
            result,timing=timed(lambda:brain.ingest(fixtures))
            if result["errors"]: raise RuntimeError(result["errors"])
            rows.append({"mode":mode,"repetition":rep+1,"report":result,"timing":timing,"extractor_calls":extractors.calls[index:]})
            print(f"Control {mode} rep {rep+1}: {timing['wall_seconds']:.3f}s",flush=True)
    original=json.loads((ROOT/"playground/scenarios.json").read_text())["scenarios"]
    extra=json.loads((ROOT/"research/evaluation_queries.json").read_text())["additional_scenarios"]
    eager=Brain(out/"collections/eager-1",embeddings=embeddings,extractors=extractors)
    queries=evaluate(eager,[{**s,"set":"original"} for s in original]+[{**s,"set":"exploratory"} for s in extra])
    save(out/"ingest_control.json",{"runs":rows,"eager_retrieval":queries,"eager_metrics":aggregate(queries),
                                   "note":"Fresh process with all models prewarmed. Paired, alternating ingestion policies. This control isolates delta OCR with exact deduplication enabled in both policies."})
    print("INGEST CONTROL COMPLETE",flush=True)


if __name__=="__main__": main()
