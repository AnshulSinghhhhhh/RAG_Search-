"""Follow-up probes prompted by dormant refinement and ASR timestamp observations."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import sys
import wave
import numpy as np

from run_experiments import ROOT, InstrumentedExtractors, Embeddings, Workspace, Brain, open_image, file_hash, timed, save, tokens, levenshtein


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--output",default=str(ROOT/"research/results/2026-11-20"))
    args=parser.parse_args()
    out=Path(args.output).resolve()
    if (out/"followups.json").exists():
        raise SystemExit("Follow-up results exist; preserve them and choose another --output.")
    workspace=Workspace(out/"collections/followup-model-owner")
    workspace.cache=ROOT/".secondbrain/models"
    embeddings=Embeddings(workspace)
    extractors=InstrumentedExtractors(workspace)
    embeddings.text(["Juniper cafe receipt"])
    embeddings.image(str(ROOT/"playground/inbox/receipts/receipt_001.png"))
    embeddings.visual_query("Juniper cafe receipt")
    extractors.ocr(open_image(ROOT/"playground/inbox/receipts/receipt_001.png"))
    rows=[]
    full=open_image(ROOT/"playground/inbox/receipts/receipt_001.png")
    fields=["690","INV-2026-1042","JUNIPER"]
    for width in (260,160,100,64):
        image=full.resize((width,round(full.height*width/full.width)))
        path=out/f"collections/receipt-width-{width}.png"
        image.save(path)
        for rep in range(3):
            brain=Brain(out/f"collections/followup-{width}-{rep}",embeddings=embeddings,extractors=extractors)
            brain.ingest_file(path)
            before=brain.store.asset(file_hash(path))
            count=len(extractors.calls)
            result,timing=timed(lambda:brain.refine("Juniper cafe receipt",budget_seconds=5,kind="image",limit=5))
            attempts=len(extractors.calls)-count
            after=brain.store.asset(file_hash(path))
            eager_lines,eager_timing=timed(lambda:extractors.ocr(image.resize((image.width*2,image.height*2))))
            def measure(item):
                text=" ".join(c["text"] for c in item["chunks"])
                return {"text":text,"confidence":item["metadata"].get("ocr_confidence"),
                        "fields":{field:field.lower() in text.lower() for field in fields}}
            eager_text=" ".join(line["text"] for line in eager_lines)
            row={"width":width,"height":image.height,"repetition":rep+1,"before":measure(before),"after":measure(after),
                 "ocr_attempts":attempts,"accepted":bool(result["refinement"]["completed"]),"refinement":result["refinement"],**timing,
                 "eager_2x":{"text":eager_text,"confidence":float(np.mean([x["confidence"] for x in eager_lines])) if eager_lines else None,
                             "fields":{field:field.lower() in eager_text.lower() for field in fields},**eager_timing}}
            rows.append(row)
        print(f"Refinement {width}px: {json.dumps(rows[-1])}",flush=True)
    extraction=json.loads((out/"extraction.json").read_text())
    audio=[]
    for row in extraction["audio"]:
        with wave.open(str(ROOT/"playground/inbox/voice"/row["file"]),"rb") as wav:
            duration=wav.getnframes()/wav.getframerate()
        canonical=lambda s:tokens(s.replace("three","3"))
        ref,actual=canonical(row["reference"]),canonical(row["transcript"])
        audio.append({"file":row["file"],"wav_duration_seconds":duration,
                      "max_segment_end":max(s["end"] for s in row["metadata"]["segments"]),
                      "out_of_bounds_segments":[s for s in row["metadata"]["segments"] if s["start"]<0 or s["end"]>duration+.05],
                      "canonicalized_wer":levenshtein(ref,actual)/len(ref),
                      "numeric_normalization":"Lowercase, strip punctuation, map English 'three' to digit '3'; name errors remain errors."})
    # Exploratory threshold diagnostics only; no thresholds are deployed or selected as validated.
    ablations=json.loads((out/"ablations.json").read_text())
    original=json.loads((ROOT/"playground/scenarios.json").read_text())["scenarios"]
    extra=json.loads((ROOT/"research/evaluation_queries.json").read_text())["additional_scenarios"]
    scenarios={x["id"]:x for x in original+extra}
    maxima=[]
    for item in ablations["channels"]:
        rankings=item["rankings"].get("text",[])
        maxima.append({"id":item["id"],"answerable":bool(scenarios[item["id"]]["expected_files"]),
                       "max_text_cosine":max((x["score"] for x in rankings),default=0)})
    sweep=[]
    for threshold in (.25,.35,.45,.55,.65,.75):
        positive=[x for x in maxima if x["answerable"]]
        negative=[x for x in maxima if not x["answerable"]]
        sweep.append({"threshold":threshold,"positive_candidate_retention":sum(x["max_text_cosine"]>=threshold for x in positive)/len(positive),
                      "negative_rejection":sum(x["max_text_cosine"]<threshold for x in negative)/len(negative)})
    save(out/"followups.json",{"reason":"The 400px receipt did not activate refinement; one ASR segment exceeded its source WAV duration. These exploratory follow-ups inspect those observations.",
                               "refinement_stress":rows,"audio_bounds":audio,"text_score_maxima":maxima,"text_threshold_sweep":sweep})
    print("FOLLOWUPS COMPLETE",flush=True)


if __name__=="__main__": main()
