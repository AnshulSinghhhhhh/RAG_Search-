"""Real-model, local exploratory evaluation. Production files/collection stay unchanged.

Run from the repository root with .venv/Scripts/python.exe research/run_experiments.py.
All labels remain outside the indexed corpus. No external model API is used.
"""
from __future__ import annotations

import argparse
from collections import Counter
from contextlib import contextmanager
from dataclasses import asdict
from datetime import datetime
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import re
import sqlite3
import statistics
import subprocess
import sys
import threading
import time

os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import numpy as np
from PIL import Image, ImageChops
import psutil
from secondbrain.config import Workspace
from secondbrain.engine import Brain, date_filters
from secondbrain.embeddings import Embeddings, quantize
from secondbrain.extract import Extractors, file_hash, open_image


def save(path, value):
    Path(path).write_text(json.dumps(value, indent=2, ensure_ascii=False), encoding="utf-8")


def timed(fn):
    start = time.perf_counter()
    cpu = time.process_time()
    value = fn()
    return value, {"wall_seconds": time.perf_counter()-start, "cpu_seconds": time.process_time()-cpu}


def summary(values):
    return {"n": len(values), "median": float(np.median(values)),
            "p95": float(np.percentile(values, 95)), "min": min(values), "max": max(values)}


class InstrumentedExtractors(Extractors):
    def __init__(self, workspace):
        super().__init__(workspace)
        self.calls = []

    def ocr(self, image):
        result, timing = timed(lambda: super(InstrumentedExtractors, self).ocr(image))
        self.calls.append({"operation": "ocr", "size": list(image.size), **timing})
        return result

    def audio(self, path):
        result, timing = timed(lambda: super(InstrumentedExtractors, self).audio(path))
        self.calls.append({"operation": "asr", "name": path.name, **timing})
        return result


class RSSSampler:
    def __init__(self):
        self.stop = threading.Event()
        self.samples = []
    def __enter__(self):
        def run():
            while not self.stop.is_set():
                self.samples.append(psutil.Process().memory_info().rss)
                self.stop.wait(.02)
        self.thread = threading.Thread(target=run, daemon=True)
        self.thread.start()
        return self
    def __exit__(self, *_):
        self.stop.set()
        self.thread.join()


def levenshtein(reference, actual):
    previous = list(range(len(actual)+1))
    for i, token in enumerate(reference, 1):
        current = [i]
        for j, other in enumerate(actual, 1):
            current.append(min(previous[j]+1, current[j-1]+1, previous[j-1]+(token != other)))
        previous = current
    return previous[-1]


def tokens(text):
    return re.findall(r"[a-z0-9]+", text.lower())


def rank_metric(results, expected):
    ranks = [i for i, item in enumerate(results, 1) if any(Path(p).name in expected for p in item["paths"])]
    return {"hit_at_1": bool(ranks and min(ranks)==1), "hit_at_5": bool(ranks and min(ranks)<=5),
            "reciprocal_rank_at_5": 1/min(ranks) if ranks and min(ranks)<=5 else 0,
            "first_relevant_rank": min(ranks) if ranks else None,
            "abstained": not results}


def evaluate(brain, scenarios, lexical=False):
    rows = []
    for scenario in scenarios:
        result, timing = timed(lambda: brain.search(scenario["query"], kind=scenario.get("kind"), limit=5, lexical_only=lexical))
        rows.append({**scenario, **rank_metric(result["results"], scenario["expected_files"]),
                     **timing, "warnings": result["warnings"],
                     "results": [{k:v for k,v in item.items() if k in ("id","name","paths","text","score","channels","start","end")} for item in result["results"]]})
    return rows


def aggregate(rows):
    positive = [r for r in rows if r["expected_files"]]
    negative = [r for r in rows if not r["expected_files"]]
    return {"answerable_n":len(positive), "no_answer_n":len(negative),
            "hit_at_1":sum(r["hit_at_1"] for r in positive)/len(positive) if positive else None,
            "hit_at_5":sum(r["hit_at_5"] for r in positive)/len(positive) if positive else None,
            "mrr_at_5":sum(r["reciprocal_rank_at_5"] for r in positive)/len(positive) if positive else None,
            "abstention_rate":sum(r["abstained"] for r in negative)/len(negative) if negative else None,
            "latency_seconds":summary([r["wall_seconds"] for r in rows])}


def replay(brain, scenarios, production_rows):
    """Replay the production candidate rules; validate hybrid order before using ablations."""
    modes = {"keyword": ("keyword",), "text": ("text",), "visual": ("visual",),
             "keyword_text": ("keyword", "text"), "hybrid": ("keyword", "text", "visual")}
    all_rows = {key:[] for key in modes}
    saved_channels, queries = [], {}
    with brain.store.connection() as db:
        corpus = [dict(r) for r in db.execute("SELECT c.*,a.kind,a.captured_at,v.space,v.data,v.qnorm,v.dim FROM vectors v JOIN chunks c ON c.id=v.chunk_id JOIN assets a ON a.id=c.asset_id")]
    float_vectors = {}
    for row in corpus:
        key = (row["id"],row["space"])
        if row["space"] == "text":
            vec = brain.embeddings.text([row["text"]])[0]
        else:
            vec = brain.embeddings.image(brain.store.asset(row["asset_id"])["paths"][0])
        float_vectors[key] = np.asarray(vec,dtype=np.float32)
    errors, overlaps, top1, threshold_crossings = [], [], [], []
    for index, scenario in enumerate(scenarios):
        clean, after, before = date_filters(scenario["query"])
        kind = scenario.get("kind")
        where, params = brain._filters(kind,after,before,None)
        rankings = {}
        with brain.store.connection() as db:
            words = re.findall(r"[^\W_]+", clean, flags=re.UNICODE)[:40]
            expression = " OR ".join('"'+w+'"' for w in words)
            rankings["keyword"] = [(r["asset_id"],-float(r["bm"])) for r in db.execute("SELECT c.asset_id,bm25(chunks_fts) bm FROM chunks_fts JOIN chunks c ON c.rowid=chunks_fts.rowid JOIN assets a ON a.id=c.asset_id WHERE chunks_fts MATCH ?"+where+" ORDER BY bm LIMIT 120",[expression,*params])]
        allowed = [r for r in corpus if (kind is None or r["kind"]==kind) and (after is None or r["captured_at"]>=after) and (before is None or r["captured_at"]<before)]
        queries[scenario["id"]] = {}
        for space in ("text","visual"):
            if space == "visual" and kind not in (None,"image"):
                continue
            query_vec = brain.embeddings.text([clean],query=True)[0] if space=="text" else brain.embeddings.visual_query(clean)
            query_vec = np.asarray(query_vec,dtype=np.float32)
            query_vec = query_vec/max(float(np.linalg.norm(query_vec)),1e-10)
            queries[scenario["id"]][space] = query_vec
            packed_scores, float_scores = [], []
            threshold = .25 if space=="text" else .12
            for row in allowed:
                if row["space"]!=space:
                    continue
                packed = np.frombuffer(row["data"],dtype=np.int8).astype(np.float32)
                packed_score = float(np.dot(packed,query_vec)/max(row["qnorm"],1e-10))
                original = float_vectors[(row["id"],space)]
                original_score = float(np.dot(original,query_vec)/max(float(np.linalg.norm(original)),1e-10))
                errors.append({"space":space,"absolute_error":abs(original_score-packed_score)})
                threshold_crossings.append((original_score>=threshold)!=(packed_score>=threshold))
                if packed_score>=threshold: packed_scores.append((row["asset_id"],packed_score))
                if original_score>=threshold: float_scores.append((row["asset_id"],original_score))
            rankings[space] = sorted(packed_scores,key=lambda x:x[1],reverse=True)[:120]
            float_scores.sort(key=lambda x:x[1],reverse=True)
            int_ids = list(dict.fromkeys(a for a,_ in rankings[space]))[:5]
            float_ids = list(dict.fromkeys(a for a,_ in float_scores))[:5]
            if int_ids and float_ids:
                overlaps.append(len(set(int_ids)&set(float_ids))/len(set(int_ids)|set(float_ids)))
                top1.append(int_ids[0]==float_ids[0])
        saved_channels.append({"id":scenario["id"],"rankings":{k:[{"asset_id":a,"score":s} for a,s in v] for k,v in rankings.items()}})
        for mode, channels in modes.items():
            fused = {}
            for channel in channels:
                seen = set()
                for asset_id,_ in rankings.get(channel,[]):
                    if asset_id in seen: continue
                    seen.add(asset_id)
                    fused[asset_id] = fused.get(asset_id,0)+1/(60+len(seen))
            ids = sorted(fused,key=fused.get,reverse=True)[:5]
            results = [brain.store.asset(asset_id) for asset_id in ids]
            all_rows[mode].append({**scenario, **rank_metric(results,scenario["expected_files"]),"wall_seconds":0,
                                  "retrieved_names":[r["name"] for r in results]})
            if mode=="hybrid":
                expected_ids = [r["id"] for r in production_rows[index]["results"]]
                if ids != expected_ids:
                    raise AssertionError(f"Replay disagreed for {scenario['id']}: {ids} != {expected_ids}")
    reconstruction=[]
    for (chunk_id,space),vec in float_vectors.items():
        packed,scale,_ = quantize(vec)
        rebuilt=np.frombuffer(packed,dtype=np.int8).astype(np.float32)*scale
        cosine=float(np.dot(vec,rebuilt)/(np.linalg.norm(vec)*np.linalg.norm(rebuilt)))
        reconstruction.append({"chunk_id":chunk_id,"space":space,"cosine":cosine})
    return {"validated_hybrid_queries":len(scenarios),"modes":{k:aggregate(v) for k,v in all_rows.items()},
            "per_query":all_rows,"channels":saved_channels,
            "quantization":{"reconstruction":reconstruction,"cosine_error_n":len(errors),
                            "mean_absolute_score_error":float(np.mean([r["absolute_error"] for r in errors])),
                            "max_absolute_score_error":max(r["absolute_error"] for r in errors),
                            "channel_top1_agreement":float(np.mean(top1)),"channel_top5_jaccard":float(np.mean(overlaps)),
                            "channel_comparisons":len(top1),"threshold_crossings":sum(threshold_crossings)}}, queries


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output",default=str(ROOT/"research/results/2026-11-20"))
    parser.add_argument("--repetitions",type=int,default=3)
    args = parser.parse_args()
    out = Path(args.output).resolve()
    out.mkdir(parents=True,exist_ok=True)
    if (out/"results.json").exists():
        raise SystemExit("Results already exist; choose another --output to preserve the run.")
    started_at = datetime.now().astimezone().isoformat()
    fixtures = ROOT/"playground/inbox"
    paths = sorted(p for p in fixtures.rglob("*") if p.is_file())
    extra = json.loads((ROOT/"research/evaluation_queries.json").read_text())
    original = json.loads((ROOT/"playground/scenarios.json").read_text())["scenarios"]
    scenarios = [{**s,"set":"original"} for s in original]+[{**s,"set":"exploratory"} for s in extra["additional_scenarios"]]
    save(out/"manifest.json", {"started_at":started_at,"source_files":[{"path":str(p.relative_to(ROOT)),"sha256":file_hash(p),"bytes":p.stat().st_size,"mtime":p.stat().st_mtime} for p in paths],
                               "code_files":[{"path":str(p.relative_to(ROOT)),"sha256":file_hash(p)} for p in sorted((ROOT/"secondbrain").glob("*.py"))],
                               "harness_sha256":file_hash(Path(__file__)),"queries_sha256":file_hash(ROOT/"research/evaluation_queries.json"),
                               "query_count":len(scenarios),"python":sys.version,"platform":platform.platform(),
                               "logical_cpus":psutil.cpu_count(),"physical_cpus":psutil.cpu_count(logical=False),
                               "ram_bytes":psutil.virtual_memory().total,
                               "versions":{p:importlib.metadata.version(p) for p in ("adaptive-secondbrain","fastembed","rapidocr","faster-whisper","onnxruntime","numpy","Pillow","psutil")}})
    workspace = Workspace(out/"collections/model-owner")
    workspace.cache = ROOT/".secondbrain/models"
    embeddings = Embeddings(workspace)
    extractors = InstrumentedExtractors(workspace)
    warmups = {}
    print("Initializing cached models (no model API)...",flush=True)
    _,warmups["text_model_first_inference"] = timed(lambda:embeddings.text(["local multimodal research"]))
    _,warmups["clip_image_first_inference"] = timed(lambda:embeddings.image(str(fixtures/"screenshots/capture_001.png")))
    _,warmups["clip_text_first_inference"] = timed(lambda:embeddings.visual_query("white sneakers"))
    _,warmups["ocr_first_inference"] = timed(lambda:extractors.ocr(open_image(fixtures/"screenshots/capture_001.png")))
    _,warmups["asr_first_inference"] = timed(lambda:extractors.audio(fixtures/"voice/memo_001.wav"))
    save(out/"warmups.json",warmups)
    print("Model initialization:",json.dumps(warmups),flush=True)
    runs=[]
    retained = None
    with RSSSampler() as rss:
        for rep in range(args.repetitions):
            order=("adaptive","eager") if rep%2==0 else ("eager","adaptive")
            for mode in order:
                home=out/f"collections/{mode}-{rep+1}"
                if (home/"memory.sqlite3").exists():
                    raise RuntimeError(f"Non-empty collection: {home}; choose a fresh --output")
                brain=Brain(home,embeddings=embeddings,extractors=extractors)
                index=len(extractors.calls)
                report,timing=timed(lambda:brain.ingest(fixtures,force=(mode=="eager")))
                calls=extractors.calls[index:]
                result={"mode":mode,"repetition":rep+1,"timing":timing,"report":report,"stats":brain.store.stats(),"extractor_calls":calls}
                if report["errors"]:
                    raise RuntimeError(f"Ingest errors: {report['errors']}")
                runs.append(result)
                print(f"Ingest {mode} rep {rep+1}: {timing['wall_seconds']:.3f}s, actions: {Counter(f['action'] for f in report['files'])}",flush=True)
                save(out/"ingestion.json",runs)
                if mode=="adaptive" and retained is None: retained=brain
        adaptive=retained
        cached=[]
        for rep in range(5):
            report,timing=timed(lambda:adaptive.ingest(fixtures))
            cached.append({"report":report,**timing})
        save(out/"cached_reindex.json",cached)
        print("Evaluating actual hybrid and lexical retrieval...",flush=True)
        hybrid=evaluate(adaptive,scenarios)
        lexical=evaluate(adaptive,scenarios,True)
        save(out/"retrieval.json",{"hybrid":hybrid,"lexical":lexical})
        print("Retrieval:",json.dumps({"hybrid":aggregate(hybrid),"lexical":aggregate(lexical)}),flush=True)
        ablations,query_vectors=replay(adaptive,scenarios,hybrid)
        save(out/"ablations.json",ablations)
        print("Channel replay validated",flush=True)
        fields=[]
        audio=[]
        with adaptive.store.connection() as db:
            assets=[adaptive.store.asset(r[0]) for r in db.execute("SELECT id FROM assets")]
        for item in assets:
            text=" ".join(c["text"] for c in item["chunks"])
            for field in extra["exact_fields"].get(item["name"],[]):
                fields.append({"file":item["name"],"kind":item["kind"],"expected":field,"present":field.lower() in text.lower(),"actual_text":text})
            if item["kind"]=="audio":
                reference=extra["audio_references"][item["name"]]
                ref,actual=tokens(reference),tokens(text)
                edits=levenshtein(ref,actual)
                audio.append({"file":item["name"],"reference":reference,"transcript":text,"reference_words":len(ref),"edit_distance":edits,"wer":edits/len(ref),"metadata":item["metadata"],"chunks":item["chunks"]})
        save(out/"extraction.json",{"fields":fields,"audio":audio})
        image1=open_image(fixtures/"screenshots/capture_001.png")
        image2=open_image(fixtures/"screenshots/capture_002.png")
        prior_lines=extractors.ocr(image1)
        delta=[]
        for rep in range(5):
            for mode in (("delta","full") if rep%2==0 else ("full","delta")):
                (lines,metrics),timing=timed(lambda:extractors.image_text(image2,image1,prior_lines,force=(mode=="full")))
                txt=" ".join(line["text"] for line in lines)
                delta.append({"mode":mode,"repetition":rep+1,**timing,"metrics":metrics,"text":txt,"new_price_present":"2499" in txt,"stale_price_present":"2999" in txt})
        jpeg=out/"collections/recompressed.jpg"
        image2.save(jpeg,quality=85)
        shifted=ImageChops.offset(image2,0,15)
        stress=[]
        for name,image in (("same_pixels",image1),("jpeg_recompression",open_image(jpeg)),("vertical_shift_15px",shifted)):
            (lines,metrics),timing=timed(lambda:extractors.image_text(image,image1,prior_lines))
            stress.append({"case":name,**timing,**metrics,"text":" ".join(x["text"] for x in lines)})
        save(out/"delta_ocr.json",{"paired":delta,"stress":stress})
        print("Delta OCR isolated comparison complete",flush=True)
        # Controlled low-resolution stress image; truth is used only for scoring.
        degraded=out/"collections/degraded-receipt.png"
        open_image(fixtures/"receipts/receipt_001.png").resize((400,480)).save(degraded)
        refiners=[]
        for rep in range(3):
            brain=Brain(out/f"collections/refine-{rep+1}",embeddings=embeddings,extractors=extractors)
            brain.ingest_file(degraded)
            before=brain.store.asset(file_hash(degraded))
            result,timing=timed(lambda:brain.refine("Juniper cafe receipt",budget_seconds=5,kind="image",limit=5))
            after=brain.store.asset(file_hash(degraded))
            def details(item):
                txt=" ".join(c["text"] for c in item["chunks"])
                return {"confidence":item["metadata"].get("ocr_confidence"),"text":txt,
                        "exact_fields":{field:field.lower() in txt.lower() for field in extra["exact_fields"]["receipt_001.png"]}}
            refiners.append({"repetition":rep+1,"before":details(before),"after":details(after),"refinement":result["refinement"],**timing})
        save(out/"refinement.json",refiners)
        # Production warm latency includes model inference, SQLite, fusion and result assembly.
        latencies=[]
        selected=[scenarios[i] for i in (0,2,6,8,10)]
        for rep in range(5):
            for mode in (("hybrid","lexical") if rep%2==0 else ("lexical","hybrid")):
                for s in selected:
                    _,timing=timed(lambda:adaptive.search(s["query"],kind=s.get("kind"),limit=5,lexical_only=(mode=="lexical")))
                    latencies.append({"mode":mode,"id":s["id"],"repetition":rep+1,**timing})
        save(out/"warm_latency.json",latencies)
        # Exact production scan with repeated real BGE vectors. This is a compute stress test.
        with adaptive.store.connection() as db:
            template=dict(db.execute("SELECT * FROM vectors WHERE space='text' LIMIT 1").fetchone())
        class FixedQuery:
            def text(self, texts, query=False):
                if not query: raise RuntimeError("Only queries are supported in scan stress test")
                return [query_vectors[scenarios[0]["id"]]["text"] for _ in texts]
        scale=[]
        for n in (100,1000,10000):
            home=out/f"scale-{n}"
            brain=Brain(home,embeddings=FixedQuery())
            brain.workspace.settings.vision=False
            now=time.time()
            with brain.store.connection() as db:
                db.executemany("INSERT INTO assets VALUES(?,?,?,?,?,?,?,?)",((f"a{i}",f"sample-{i}.txt","text",1,now,now,"{}","stress") for i in range(n)))
                db.executemany("INSERT INTO locations VALUES(?,?,?,?)",((str(home/f"sample-{i}.txt"),f"a{i}",0,1) for i in range(n)))
                db.executemany("INSERT INTO chunks VALUES(?,?,?,?,?,?)",((f"c{i}",f"a{i}","repeated corpus vector for scan timing",None,None,0) for i in range(n)))
                db.executemany("INSERT INTO vectors VALUES(?,?,?,?,?,?,?)",((f"c{i}","text",template["model"],template["dim"],template["data"],template["scale"],template["qnorm"]) for i in range(n)))
            brain.search("white sneakers",limit=5)
            for rep in range(5):
                _,timing=timed(lambda:brain.search("white sneakers",limit=5))
                scale.append({"vectors":n,"repetition":rep+1,**timing})
            print(f"Exact-scan stress {n}: {summary([x['wall_seconds'] for x in scale if x['vectors']==n])}",flush=True)
            # These known, generated database files are disposable; preserve raw timings.
            for p in home.glob("memory.sqlite3*"): p.unlink()
        save(out/"scale.json",scale)
    stats=adaptive.store.stats()
    cache_bytes=sum(p.stat().st_size for p in workspace.cache.rglob("*") if p.is_file())
    thumbnail_bytes=sum(p.stat().st_size for p in adaptive.workspace.thumbnails.glob("*"))
    # Fresh process, existing model cache and warmed OS cache; not a cold disk measurement.
    cold_code="from secondbrain.engine import Brain; from pathlib import Path; import time,json,sys; b=Brain(sys.argv[1]); b.workspace.cache=Path(sys.argv[2]); s=time.perf_counter(); r=b.search('white sneakers',kind='image',limit=5); print(json.dumps({'seconds':time.perf_counter()-s,'warnings':r['warnings'],'names':[x['name'] for x in r['results']]}))"
    fresh=[]
    for rep in range(3):
        start=time.perf_counter()
        run=subprocess.run([sys.executable,"-c",cold_code,str(adaptive.workspace.home),str(workspace.cache)],cwd=ROOT,capture_output=True,text=True,check=True)
        fresh.append({"repetition":rep+1,"process_wall_seconds":time.perf_counter()-start,"search":json.loads(run.stdout.strip().splitlines()[-1]),"stderr":run.stderr})
    save(out/"fresh_process_latency.json",fresh)
    results={"started_at":started_at,"finished_at":datetime.now().astimezone().isoformat(),"settings":asdict(workspace.settings),
             "warmups":warmups,"ingestion":{mode:summary([r["timing"]["wall_seconds"] for r in runs if r["mode"]==mode]) for mode in ("eager","adaptive")},
             "cached_reindex_seconds":summary([r["wall_seconds"] for r in cached]),
             "retrieval":{"hybrid":aggregate(hybrid),"lexical":aggregate(lexical),
                          "original_hybrid":aggregate([r for r in hybrid if r["set"]=="original"]),"exploratory_hybrid":aggregate([r for r in hybrid if r["set"]=="exploratory"])},
             "ablations":ablations["modes"],"quantization":{k:v for k,v in ablations["quantization"].items() if k!="reconstruction"},
             "storage":{"stats":stats,"model_cache_file_bytes":cache_bytes,"thumbnail_bytes":thumbnail_bytes,
                        "int8_payload_plus_two_float64_metadata_bytes":stats["vector_bytes"]+stats["vectors"]*16},
             "peak_sampled_process_rss_bytes":max(rss.samples),
             "warm_latency":{m:summary([r["wall_seconds"] for r in latencies if r["mode"]==m]) for m in ("hybrid","lexical")},
             "scale":{n:summary([r["wall_seconds"] for r in scale if r["vectors"]==n]) for n in (100,1000,10000)},
             "fresh_process_search_seconds":summary([r["search"]["seconds"] for r in fresh])}
    save(out/"results.json",results)
    print("COMPLETE",json.dumps(results),flush=True)


if __name__=="__main__":
    main()
