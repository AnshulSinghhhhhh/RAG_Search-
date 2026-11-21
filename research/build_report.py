"""Build the research PDF, editable HTML, figures and CSVs from recorded evidence."""
from __future__ import annotations
import argparse
import csv
from datetime import datetime
from html import escape
import json
import math
from pathlib import Path
import statistics
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image, PageBreak, KeepTogether
from secondbrain.engine import date_filters
from secondbrain.extract import modality

TEAL="#1c6c68"
NAVY="#183444"
ORANGE="#b0522d"
GRAY="#586b76"


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--results",default=str(ROOT/"research/results/2026-11-20"))
    args=ap.parse_args()
    data=Path(args.results).resolve()
    output=ROOT/"output/research"
    figures=output/"figures"
    figures.mkdir(parents=True,exist_ok=True)
    pdfpath=ROOT/"output/pdf/adaptive_secondbrain_research_report.pdf"
    pdfpath.parent.mkdir(parents=True,exist_ok=True)
    load=lambda name:json.loads((data/name).read_text(encoding="utf-8"))
    r=load("results.json")
    manifest=load("manifest.json")
    ingestion=load("ingestion.json")
    retrieval=load("retrieval.json")
    ab=load("ablations.json")
    delta=load("delta_ocr.json")
    extraction=load("extraction.json")
    follow=load("followups.json")
    control=load("ingest_control.json")
    latencies=load("warm_latency.json")
    sources=json.loads((ROOT/"research/sources.json").read_text())
    stats=r["storage"]["stats"]
    pct=lambda x:f"{100*x:.1f}%"
    ms=lambda x:f"{1000*x:.1f} ms"
    med=lambda items,key:statistics.median(x[key] for x in items)
    full=med([x for x in delta["paired"] if x["mode"]=="full"],"wall_seconds")
    crop=med([x for x in delta["paired"] if x["mode"]=="delta"],"wall_seconds")
    eager=r["ingestion"]["eager"]["median"]
    reuse=r["ingestion"]["adaptive"]["median"]
    control_medians={mode:statistics.median(x["timing"]["wall_seconds"] for x in control["runs"] if x["mode"]==mode) for mode in ("dedup_full_ocr","dedup_delta_ocr")}
    fields=extraction["fields"]
    image_fields=[x for x in fields if x["kind"]=="image"]
    raw_edits=sum(x["edit_distance"] for x in extraction["audio"])
    raw_words=sum(x["reference_words"] for x in extraction["audio"])
    now=datetime.fromisoformat(r["started_at"])
    unique={x["sha256"]:x for x in manifest["source_files"]}
    chance=[]
    candidate_counts=[]
    for s in retrieval["hybrid"]:
        if not s["expected_files"]: continue
        _,after,before=date_filters(s["query"],now=now)
        available=[x for x in unique.values() if (not s.get("kind") or modality(Path(x["path"]))==s["kind"]) and (after is None or x["mtime"]>=after) and (before is None or x["mtime"]<before)]
        n=len(available)
        relevant=sum(Path(x["path"]).name in s["expected_files"] or (Path(x["path"]).name=="capture_001_copy.png" and "capture_001.png" in s["expected_files"]) for x in available)
        k=min(5,n)
        chance.append(1-(math.comb(n-relevant,k)/math.comb(n,k) if n-relevant>=k else 0))
        candidate_counts.append({"id":s["id"],"candidates":n,"relevant_assets":relevant})
    q=ab["quantization"]
    stress=follow["refinement_stress"]
    derived={"ingestion_wall_reduction":1-reuse/eager,"isolated_delta_wall_change":crop/full-1,
             "control_medians_seconds":control_medians,"control_delta_wall_change":control_medians["dedup_delta_ocr"]/control_medians["dedup_full_ocr"]-1,
             "uniform_random_hit_at_5":statistics.mean(chance),"candidate_counts":candidate_counts,
             "image_field_successes":sum(x["present"] for x in image_fields),"image_field_checks":len(image_fields),
             "raw_audio_wer":raw_edits/raw_words,"raw_audio_words":raw_words,"raw_audio_edits":raw_edits,
             "min_reconstruction_cosine":min(x["cosine"] for x in q["reconstruction"]),
             "refinement_attempts":sum(x["ocr_attempts"] for x in stress),"refinement_accepted":sum(x["accepted"] for x in stress)}
    (data/"report_evidence.json").write_text(json.dumps(derived,indent=2),encoding="utf-8")
    # Portable tables for independent analysis.
    with (data/"query_results.csv").open("w",newline="",encoding="utf-8") as f:
        writer=csv.DictWriter(f,fieldnames=["mode","id","set","query","kind","expected_files","top_result","first_relevant_rank","hit_at_1","hit_at_5","abstained","wall_seconds"])
        writer.writeheader()
        for mode,rows in retrieval.items():
            for row in rows:
                writer.writerow({"mode":mode,**{k:row.get(k,"") for k in ("id","set","query","kind","first_relevant_rank","hit_at_1","hit_at_5","abstained","wall_seconds")},
                                 "expected_files":"|".join(row["expected_files"]),"top_result":row["results"][0]["name"] if row["results"] else ""})
    with (data/"experiment_summary.csv").open("w",newline="",encoding="utf-8") as f:
        writer=csv.writer(f)
        writer.writerow(["experiment","variant","metric","value","unit","sample_n"])
        for mode in ("eager","adaptive"):
            writer.writerow(["ingestion",mode,"median_wall",r["ingestion"][mode]["median"],"seconds",3])
        for mode,metrics in ab["modes"].items():
            for metric in ("hit_at_1","hit_at_5","mrr_at_5","abstention_rate"):
                writer.writerow(["retrieval",mode,metric,metrics[metric],"fraction",12 if metric=="abstention_rate" else 30])
        for mode,value in (("full",full),("delta",crop)):
            writer.writerow(["delta_ocr",mode,"median_wall",value,"seconds",5])
        for n,value in r["scale"].items():
            writer.writerow(["exact_scan",n,"median_wall",value["median"],"seconds",5])

    plt.rcParams.update({"font.family":"DejaVu Sans","font.size":10,"axes.spines.top":False,"axes.spines.right":False,"axes.labelcolor":NAVY,"text.color":NAVY,"axes.edgecolor":"#b3c1c7","xtick.color":GRAY,"ytick.color":GRAY,"figure.facecolor":"white"})
    fig,ax=plt.subplots(figsize=(7.2,2.7),layout="constrained")
    modes=["keyword","text","keyword_text","hybrid"]
    x=np.arange(4)
    ax.bar(x-.17,[ab["modes"][m]["hit_at_1"]*100 for m in modes],.34,color=TEAL,label="Hit@1")
    ax.bar(x+.17,[ab["modes"][m]["hit_at_5"]*100 for m in modes],.34,color="#a8cdc4",label="Hit@5")
    ax.set_xticks(x,["Keywords","BGE text","Keywords + BGE","Full hybrid"])
    ax.set_ylim(0,110)
    ax.set_ylabel("Answerable queries (%)")
    ax.legend(loc="lower right",frameon=False,ncol=2)
    ax.grid(axis="y",alpha=.15)
    ax.set_axisbelow(True)
    fig.savefig(figures/"retrieval.png",dpi=200)
    plt.close(fig)
    fig,axes=plt.subplots(1,2,figsize=(7.2,2.7),layout="constrained")
    axes[0].bar(["Full image","Delta crop"],[100,1.604],color=["#a8cdc4",TEAL])
    axes[0].set_ylabel("Image area submitted to OCR (%)")
    axes[0].set_ylim(0,115)
    axes[0].text(0,103,"100%",ha="center")
    axes[0].text(1,5,"1.604%",ha="center")
    axes[1].bar(["Full image","Delta crop"],[full*1000,crop*1000],color=["#a8cdc4",ORANGE])
    axes[1].set_ylabel("Median wall time (ms), n=5 each")
    for i,v in enumerate([full,crop]): axes[1].text(i,v*1000+18,f"{v*1000:.0f}",ha="center")
    axes[1].set_ylim(0,max(full,crop)*1250)
    fig.savefig(figures/"delta_ocr.png",dpi=200)
    plt.close(fig)
    fig,ax=plt.subplots(figsize=(7.2,2.7),layout="constrained")
    ns=[100,1000,10000]
    mids=[r["scale"][str(n)]["median"]*1000 for n in ns]
    lower=[(r["scale"][str(n)]["median"]-r["scale"][str(n)]["min"])*1000 for n in ns]
    upper=[(r["scale"][str(n)]["max"]-r["scale"][str(n)]["median"])*1000 for n in ns]
    ax.errorbar(ns,mids,yerr=[lower,upper],color=TEAL,marker="o",capsize=4,lw=2)
    ax.set_xscale("log")
    ax.set_xticks(ns,["100","1,000","10,000"])
    ax.set_xlabel("Repeated real text vectors (384 dimensions)")
    ax.set_ylabel("Production search wall time (ms)")
    ax.grid(alpha=.15)
    for n,v in zip(ns,mids): ax.annotate(f"{v:.1f} ms",(n,v),xytext=(6,8),textcoords="offset points")
    ax.set_ylim(0,max(mids)*1.25)
    fig.savefig(figures/"scale.png",dpi=200)
    plt.close(fig)

    pages=[]
    def page(title,subtitle=""):
        pages.append({"title":title,"subtitle":subtitle,"elements":[]})
    def p(text,kind="body"): pages[-1]["elements"].append(("p",text,kind))
    def table(headers,rows,widths): pages[-1]["elements"].append(("table",headers,rows,widths))
    def img(name,caption): pages[-1]["elements"].append(("image",name,caption))
    def bullets(items):
        for item in items: p("- "+item)
    def note(text): p(text,"note")

    page("Adaptive Second Brain", "Experimental research report | 20 November 2026 | Prototype 0.1.0")
    p("A local multimodal memory: what works, what costs less, and where evidence retrieval fails", "deck")
    table(["30 / 30","27 / 30","0 / 12"],[["Expected file in top five","Expected file ranked first","Absent-answer queries with no candidates"]],[166,166,167])
    p("<b>Research question.</b> Can this prototype retrieve personal screenshots, receipts, notes and voice memos while reducing repeated processing and vector storage, without losing important facts?")
    p(f"<b>Result.</b> On 12 synthetic files representing 11 unique assets, full hybrid retrieval achieved 100% Hit@5 and 90% Hit@1 across 30 answerable queries. It returned candidates for every one of 12 absent-answer queries. The system is effective at locating this small collection, but has no demonstrated answerability calibration.")
    bullets([
        f"Exact duplicate reuse worked. Warm ingestion fell from a median {eager:.2f}s with forced eager processing to {reuse:.2f}s with the current reuse policy ({pct(1-reuse/eager)} lower wall time; three runs each).",
        f"Changed-region OCR preserved INR 2499 and removed INR 2999. Its 1.604% crop did not produce a measured runtime saving: isolated medians were {ms(crop)} for delta and {ms(full)} for full OCR.",
        "INT8 corpus vector payload was 7,808 bytes versus 31,232 equivalent float32 bytes. This 75% payload reduction is much smaller than the total storage occupied by models and metadata.",
        "Fact extraction has consequential failures: Juniper became Jennifer in audio, an invoice digit error survived the OCR confidence gate, and one ASR segment exceeded the WAV duration."
    ])
    note("Evidence status: all numerical results in this report were observed in this research session. The corpus and added queries are synthetic and exploratory. These are prototype measurements, not a representative accuracy study or proof of a new algorithm.")

    page("01  System and research context", "What the implementation actually does")
    p("The application is a Python-served local search system. One shared Brain engine supports the CLI and a localhost web interface. It accepts images, audio and text; PDF and video ingestion are absent. Default answers are quoted source excerpts. A local Ollama generation path exists, but no generative model was evaluated here.")
    table(["Stage","Implemented mechanism"],[
        ["Identify and reuse","SHA-256 exact content IDs with independent file locations; near-image proposals use dHash and the latest 150 images."],
        ["Extract","RapidOCR full/delta image text; faster-whisper base on CPU INT8 for audio; 140-word text chunks with 20-word overlap."],
        ["Embed","BGE-small-en-v1.5 text vectors (384D); paired CLIP ViT-B/32 image and query encoders (512D)."],
        ["Store and retrieve","SQLite metadata, FTS5 keywords and packed INT8 vectors. Dense retrieval is an exact scan after modality/date/folder filtering."],
        ["Fuse and refine","One reciprocal-rank vote per asset per channel, k=60. Rule-based OCR retry for retrieved images with mean confidence below 0.9; 5s soft budget in these probes."]
    ],[104,395])
    p("<b>Relation to prior research.</b> RAG combines external memory with generation [1]; this project primarily evaluates retrieval and evidence presentation. CLIP provides paired image/text spaces [2], while OCR and BGE supply exact and semantic text evidence. Reciprocal rank fusion combines channel orderings without requiring score calibration [3]. Whisper supplies speech transcripts [4]. BGE's model card cautions that absolute cosine scores require task-specific interpretation [5].")
    p("<b>Contribution under study.</b> The engineering hypothesis is that local deduplication, changed-region processing, compact vectors and selective retries can reduce cost while preserving useful evidence. These mechanisms are existing ideas assembled in a prototype. This study establishes local observations; it does not establish algorithmic novelty or transfer the cited papers' benchmark results to this project.")
    note("The current 'adaptive' behavior is a set of fixed rules. There is no trained quality predictor, learned compute allocator, ANN index, ASR refinement controller or VLM captioning stage.")

    page("02  Experimental method", "Controls, sample sizes and measurement definitions")
    table(["Item","Recorded configuration"],[
        ["Machine","AMD Ryzen 5 5600H; 6 physical / 12 logical CPUs; 7.35 GiB physical RAM; Windows build 26300."],
        ["Runtime",f"Python 3.11.9; fastembed {manifest['versions']['fastembed']}; RapidOCR {manifest['versions']['rapidocr']}; ONNX Runtime {manifest['versions']['onnxruntime']}; faster-whisper {manifest['versions']['faster-whisper']}."],
        ["Execution","CPU execution provider, four configured threads. Models loaded from the existing local cache; HF offline mode enabled. No external model API."],
        ["Corpus","8 image files (7 unique), 2 text notes and 2 synthesized English WAVs. One exact duplicate and one changed-price image family. Labels remain outside inbox/."],
        ["Queries","11 original scenarios (10 answerable, 1 absent-answer) plus 31 exploratory scenarios (20 answerable, 11 absent-answer). Same corpus; no model training or held-out split."],
        ["Timing","perf_counter wall time and process CPU time. Three alternating warm ingestion runs per policy; five paired isolated OCR runs; 25 warm queries per retrieval mode; three fresh-process queries."],
        ["Integrity","Separate experiment collections; original files and the existing .secondbrain collection retained. Source/code SHA-256 hashes, file mtimes, settings and package versions recorded."]
    ],[93,406])
    p("<b>Metrics.</b> Hit@k is the fraction of answerable queries with at least one expected unique asset among the first k results. MRR@5 averages reciprocal first-relevant rank, or zero when absent from the top five. These are file relevance metrics, not exact answer accuracy. No-answer abstention means returning zero candidates; it does not assess a generated answer. OCR field checks use case-insensitive literal substrings. Audio WER is word edit distance divided by reference words after lowercasing and punctuation removal.")
    p(f"<b>Small-collection effect.</b> Top-five retrieval is guaranteed when only two audio or text assets survive a modality filter. A uniform-random ranking under these same filters would have expected Hit@5 of approximately {pct(statistics.mean(chance))} over the 30 positive queries. This diagnostic explains why Hit@1 and failure inspection are essential; it is not a statistical comparison against a trained baseline.")
    note("The added queries were authored after inspecting the fixtures. Query outcomes are exploratory and correlated within asset families. Repeated timing samples measure run variability, not independent accuracy evidence. p95 is an empirical percentile of the recorded small sample.")

    page("03  Correctness and processing cost", "Experiments E1-E3: tests, eager ingestion and reuse controls")
    p("<b>E1 - Existing regression suite.</b> The command .venv\\Scripts\\python.exe -m pytest -q completed with 23 passed in 1.92s. It covers transactions, content changes, duplicate aliases, deletion/pruning, date/folder filters, delta OCR behavior, audio chunk offsets, shared API behavior and local request protections. Embeddings and selected extraction paths use test doubles; these results establish tested software behavior, not real-model accuracy.")
    primary_rows=[]
    for mode,label in (("eager","Eager: force every file"),("adaptive","Current: dedup + delta OCR")):
        subset=[x for x in ingestion if x["mode"]==mode]
        primary_rows.append([label,f"{r['ingestion'][mode]['median']:.3f}s",f"{min(x['timing']['wall_seconds'] for x in subset):.3f}-{max(x['timing']['wall_seconds'] for x in subset):.3f}s",f"{statistics.median(x['timing']['cpu_seconds'] for x in subset):.2f}s", "12 indexed" if mode=="eager" else "11 indexed + 1 duplicate"])
    table(["E2 policy (n=3)","Wall median","Wall range","CPU median","Per-run actions"],primary_rows,[155,71,91,75,107])
    p(f"The current policy reduced median wall time by {pct(1-reuse/eager)} against this deliberately eager baseline. Both produced 11 unique assets at 12 locations, with no ingestion errors. Eager forcing reprocesses even the exact duplicate, so the contrast combines duplicate skipping and changed-region OCR. It cannot by itself attribute a gain to the crop.")
    table(["E3 follow-up control (n=3)","Median wall","Observed range"],[
        ["Deduplication + full OCR",f"{control_medians['dedup_full_ocr']:.3f}s",f"{min(x['timing']['wall_seconds'] for x in control['runs'] if x['mode']=='dedup_full_ocr'):.3f}-{max(x['timing']['wall_seconds'] for x in control['runs'] if x['mode']=='dedup_full_ocr'):.3f}s"],
        ["Deduplication + delta OCR",f"{control_medians['dedup_delta_ocr']:.3f}s",f"{min(x['timing']['wall_seconds'] for x in control['runs'] if x['mode']=='dedup_delta_ocr'):.3f}-{max(x['timing']['wall_seconds'] for x in control['runs'] if x['mode']=='dedup_delta_ocr'):.3f}s"]
    ],[285,100,114])
    p(f"With exact deduplication held constant, adding delta OCR was {pct(control_medians['dedup_delta_ocr']/control_medians['dedup_full_ocr']-1)} slower by median in this follow-up. Ranges overlap and n=3 is small. The isolated OCR experiment on the next page agrees that crop area is not a measured wall-time saving here.")
    p(f"<b>Cached re-index.</b> Five unchanged re-indexes returned 12 cached locations each, median {r['cached_reindex_seconds']['median']:.3f}s. Files are still hashed and SQLite events are written. This is reuse of existing extraction/embeddings, not a fresh-ingestion speedup.")
    note(f"Raw evidence: unit_tests.json, ingestion.json, cached_reindex.json and ingest_control.json. The full-OCR eager collection was also queried: Hit@1 and Hit@5 matched the current policy's 90% and 100%; its MRR@5 was {control['eager_metrics']['mrr_at_5']:.3f}, versus 0.950 for the current policy.")

    page("04  Changed-region OCR", "Experiment E4: area reduction did not imply a speedup")
    img("delta_ocr.png","Same changed-price image; real RapidOCR, five alternating measurements per mode. Axes measure different quantities.")
    p(f"The original screenshot shows INR 2999; the modified screenshot shows INR 2499. Delta extraction reused five unchanged OCR lines and processed a crop covering 1.604% of the image. Across all five repetitions, the new value was present and the stale value was absent. Full OCR also preserved the correct value in every repetition.")
    table(["Mode","Wall median","CPU median","OCR area"],[
        ["Full image",ms(full),f"{statistics.median(x['cpu_seconds'] for x in delta['paired'] if x['mode']=='full'):.3f}s","100%"],
        ["Delta crop",ms(crop),f"{statistics.median(x['cpu_seconds'] for x in delta['paired'] if x['mode']=='delta'):.3f}s","1.604%"]
    ],[140,115,115,129])
    p(f"The crop reduced submitted pixels by 98.396%, yet median wall time increased by {pct(crop/full-1)}. The measurement includes the changed-region logic and OCR call. Internal OCR resizing, model overhead and runtime variability are plausible explanations, but this study did not profile those components and cannot establish the cause.")
    table(["One-shot stress probe","Observed strategy","Interpretation"],[
        ["Identical decoded pixels","Reuse; 0% OCR area","All 6 existing lines reused; no new OCR inference."],
        ["JPEG quality 85 recompression","Full OCR; 100% area","Widespread native-pixel differences defeat the crop."],
        ["15px vertical shift","Full OCR; 100% area","The shifted layout triggered the safe full-image path."]
    ],[173,132,194])
    note("These stress probes call the extraction function directly with a known predecessor. They test its fallback behavior, not the accuracy of the dHash predecessor selector. Conclusions are limited to one synthetic image family and two transformations. Evidence: delta_ocr.json.")

    page("05  Retrieval and channel ablations", "Experiment E5: semantic channels recover misses, but fusion can hurt first rank")
    img("retrieval.png","Thirty answerable queries. Accuracy values are from channel replay; full hybrid order was validated against all 42 actual production searches.")
    rows=[]
    labels={"keyword":"FTS5 keywords","text":"BGE only","visual":"CLIP only (all queries)","keyword_text":"Keywords + BGE","hybrid":"Full hybrid"}
    for mode in ("keyword","text","visual","keyword_text","hybrid"):
        v=ab["modes"][mode]
        rows.append([labels[mode],f"{round(v['hit_at_1']*30)}/30",f"{round(v['hit_at_5']*30)}/30",f"{v['mrr_at_5']:.3f}",f"{round(v['abstention_rate']*12)}/12"])
    table(["Channels","Hit@1","Hit@5","MRR@5","Absent: empty"],rows,[185,70,70,79,95])
    p("Full hybrid recovered two lexical top-five misses: 'a pale cream low top shoe' and 'portable illumination for sleeping outdoors'. Both expected files ranked second. All 10 original positives ranked first; only 17 of 20 added positives did. The third hybrid first-rank error was 'olive colored footwear', where a white shoe preceded the green shoe.")
    p("CLIP-only results are modality-limited: among the 19 image-target queries, it achieved 15/19 Hit@1 and 18/19 Hit@5. The all-query row also includes 11 text/audio targets that CLIP cannot retrieve. Adding CLIP to keywords+BGE did not change Hit@1 or Hit@5 here; MRR@5 rose only from 0.944 to 0.950. This corpus does not demonstrate a large incremental CLIP benefit.")
    note("Ablations replay the exact production candidate thresholds (BGE >=0.25, CLIP >=0.12), top-120 channel caps and asset-level RRF. Replay timings are not measurements and are excluded from latency claims. Evidence: retrieval.json, ablations.json, query_results.csv.")

    page("06  Answerability and fact fidelity", "Experiments E6-E7: a retrieved source can still lack the answer")
    p("<b>Absent-answer retrieval.</b> Hybrid returned candidates for all 12 negative queries, including cafe Wi-Fi, a hotel confirmation and a stove serial number that are absent from the fixtures. Keywords abstained on 2/12 and returned candidates on 10/12. These are candidate-selection failures; no generative hallucination rate was measured. The default answer function explicitly presents the results as closest excerpts to inspect.")
    table(["Illustrative BGE-only cutoff","Positive candidate retention","Negative rejection"],[
        [f"{x['threshold']:.2f}",pct(x["positive_candidate_retention"]),pct(x["negative_rejection"])] for x in follow["text_threshold_sweep"] if x["threshold"] in (.25,.55,.65,.75)
    ],[157,171,171])
    p("This same-set sweep only asks whether any text candidate exceeds a threshold; it does not require that candidate to be relevant and does not implement the hybrid pipeline. It illustrates the tradeoff, not a validated replacement cutoff. Raising the cutoff to 0.65 rejects 75% of negatives while retaining any candidate for only 70% of positives. No threshold was changed in production.")
    p(f"<b>Exact extraction.</b> Original-resolution image OCR passed {sum(x['present'] for x in image_fields)}/{len(image_fields)} selected literal field checks: prices, invoice IDs, receipt totals, an error code, port and landmark names. These hand-picked fields are not full-document OCR accuracy. Audio passed 3/5 literal fields, or 4/5 after treating 'three' and '3' as equivalent. The remaining factual error is Juniper -> Jennifer.")
    table(["Audio file","Raw WER","Number-normalized WER","Timestamp bound"],[
        [row["file"],pct(row["wer"]),pct(next(x["canonicalized_wer"] for x in follow["audio_bounds"] if x["file"]==row["file"])),"Valid bounds" if not next(x["out_of_bounds_segments"] for x in follow["audio_bounds"] if x["file"]==row["file"]) else "17.60s end / 12.27s WAV"] for row in extraction["audio"]
    ],[117,83,141,158])
    p(f"Combined raw WER is {pct(raw_edits/raw_words)} ({raw_edits} edits / {raw_words} reference words); one edit is number formatting. For memo_002.wav, the final segment ends 5.33s beyond the measured WAV duration. Its start remains within the file, but the end cannot be a valid source span. Timing alignment accuracy within valid bounds was not measured.")
    note("Label audit: the original 'meeting-owner' text scenario labels a note that names Priya as landing-page owner, not explicitly design-review owner. Its successful file retrieval does not prove the requested responsibility. The audio meeting memo states that responsibility explicitly. Evidence: extraction.json and followups.json.")

    page("07  Compression and storage", "Experiment E8: compact payloads, measurable ranking perturbations")
    table(["Measured or equivalent component","Size / outcome"],[
        ["18 stored INT8 vector payloads","7,808 bytes"],
        ["Same dimensions as float32 payloads","31,232 bytes (calculated equivalent; no float32 database built)"],
        ["INT8 plus 2 x 8-byte numeric fields/vector","8,096 bytes; 74.1% below float32 payload alone; excludes SQLite overhead"],
        ["SQLite database + sidecars at snapshot",f"{stats['database_bytes']:,} bytes; includes metadata, FTS, locations and activity events"],
        ["Thumbnails",f"{r['storage']['thumbnail_bytes']:,} bytes"],
        ["Unique source media",f"{stats['source_bytes']:,} bytes"],
        ["Shared model cache (logical file sizes)",f"{r['storage']['model_cache_file_bytes']:,} bytes ({r['storage']['model_cache_file_bytes']/1024**2:.1f} MiB)"],
        ["Sampled main-process resident memory",f"Peak {r['peak_sampled_process_rss_bytes']/1024**3:.2f} GiB after model warmup"]
    ],[247,252])
    p("Symmetric quantization stores one signed byte per component and a per-vector scale. Cosine retrieval divides by the packed-vector norm, so scale cancels in this scoring path. Re-embedding the actual corpus and comparing its float32 outputs with INT8 reconstruction isolates corpus-vector storage quantization; it does not undo any quantization inside the pretrained ONNX models.")
    table(["Quality diagnostic","Observed result"],[
        ["Minimum original/reconstructed cosine",f"{derived['min_reconstruction_cosine']:.6f}"],
        ["Absolute query-score error",f"Mean {q['mean_absolute_score_error']:.6f}; max {q['max_absolute_score_error']:.6f}; n={q['cosine_error_n']} vector-query pairs"],
        ["Top-one channel rank agreement",f"{pct(q['channel_top1_agreement'])} (62/66 nonempty query-channel comparisons)"],
        ["Mean top-five set Jaccard",f"{q['channel_top5_jaccard']:.4f}; 66 comparisons"],
        ["Candidate-threshold crossings",f"{q['threshold_crossings']} in the scored comparisons"]
    ],[224,275])
    p("Small score errors still changed four channel-level first results, so compression is not rank-identical. Final fused float32 relevance was not separately evaluated. The 75% claim applies to raw vectors only: it neither establishes a 75% reduction in the full database nor materially changes the model cache footprint at this corpus size.")
    note("RSS was sampled every 20ms during the main warmed experiment phase. It is a process working-set observation, not isolated model memory, a system peak, or a measurement of the later subprocesses/follow-ups. Model-cache bytes are logical sizes, not allocated disk blocks. Evidence: ablations.json and results.json.")

    page("08  Latency and scale", "Experiment E9: warm interactions differ sharply from process startup")
    white_warm=statistics.median(x["wall_seconds"] for x in latencies if x["mode"]=="hybrid" and x["id"]=="visual-white-shoe")
    table(["Search condition","Median","Empirical p95 / n"],[
        ["Warm hybrid: five queries x five rounds",ms(r["warm_latency"]["hybrid"]["median"]),f"{ms(r['warm_latency']['hybrid']['p95'])}; n=25"],
        ["Warm keywords: same query mix",ms(r["warm_latency"]["lexical"]["median"]),f"{ms(r['warm_latency']['lexical']['p95'])}; n=25"],
        ["Fresh process: white-sneaker query",f"{r['fresh_process_search_seconds']['median']:.3f}s",f"{r['fresh_process_search_seconds']['p95']:.3f}s; n=3"],
        ["Same white-sneaker query, warmed",ms(white_warm),"n=5; existing model instances"]
    ],[264,94,141])
    p("Fresh-process search timing begins after Brain construction and includes lazy query-model initialization. Existing model files and warmed operating-system caches are retained. It is not a cold-disk or first-install download measurement. Initial per-model first inference, measured separately, took 1.41s for BGE, 0.75s for CLIP image, 0.82s for CLIP text, 2.00s for OCR and 9.33s for ASR on the first memo.")
    img("scale.png","Five warmed production searches per scale; points are medians and error bars show observed minimum/maximum.")
    p("The scan stress test inserted 100, 1,000 and 10,000 independent asset rows carrying a repeated real 384D text vector. It used production SQLite scanning, filtering, fusion and result assembly, but injected a fixed query vector to remove model inference. Median search times rose from 28.4ms to 36.3ms to 148.3ms. The small-N fixed overhead means the measured curve is not proportional across all three points.")
    note("This is a compute microbenchmark, not a meaningful enlarged retrieval dataset. It has no real source files, uses repeated content, and does not establish 10,000-document accuracy, concurrent throughput, ANN comparisons or million-vector performance. Evidence: warm_latency.json, fresh_process_latency.json, warmups.json and scale.json.")

    page("09  Selective OCR refinement", "Experiment E10: the controller saved retries, but recovered no tested fields")
    p("A 400 x 480 downsample of the cafe receipt retained all three selected fields and mean OCR confidence 0.9981. Three fresh-collection queries performed no retry, as expected under the confidence gate. Follow-up probes then reduced the original 760 x 900 image to four smaller widths, with aspect ratio approximately preserved. Each setting was repeated three times and compared with unconditional 2x-upsampled OCR.")
    stress_rows=[]
    for width in (260,160,100,64):
        subset=[x for x in stress if x["width"]==width]
        first=subset[0]
        stress_rows.append([f"{width} x {first['height']}",f"{first['before']['confidence']:.3f}" if first["before"]["confidence"] is not None else "No text",f"{sum(first['before']['fields'].values())}/3",f"{sum(x['ocr_attempts'] for x in subset)}/3",f"{sum(x['accepted'] for x in subset)}/3",f"{sum(first['after']['fields'].values())}/3",f"{sum(first['eager_2x']['fields'].values())}/3"])
    table(["Input pixels","Mean conf.","Fields before","Retries","Accepted","Fields after","Eager 2x"],stress_rows,[88,67,76,56,67,78,67])
    p("<b>High-confidence factual error.</b> At width 160, OCR read INV-2006-1042 instead of INV-2026-1042, despite mean confidence 0.938. The gate therefore made no retry. Unconditional 2x OCR also failed to recover the invoice and had lower mean confidence, so the probe does not show a recoverable field was lost specifically because of the gate. It does show that mean confidence is an inadequate detector of field errors.")
    p("<b>Severe degradation.</b> At width 100, confidence fell below 0.9 and all three runs attempted refinement, but confidence did not improve and none was accepted. At width 64, there was no extracted text before or after retry. Across the 12 follow-up runs there were six OCR attempts, zero accepted updates and no increase in selected-field correctness. The 260px receipt needed no retry and retained all fields.")
    p("The unconditional upsampling comparator also recovered no additional selected fields. The observed benefit of selection is avoiding unnecessary OCR calls on easy images; no accuracy benefit from the refinement transformation was demonstrated. Confidence increases and exact factual corrections require separate scoring.")
    note("The 5s limit is a soft budget, including initial retrieval. These short calls stayed within it, but no hard deadline was enforced or tested. Resolution variants are controlled synthetic stresses, not natural damaged receipts or an independent evaluation set. Evidence: refinement.json and followups.json.")

    page("10  Interpretation and next research", "Supported conclusions, validity limits and proposed work")
    p("<b>Supported conclusions.</b> Exact duplicate reuse and cached re-indexing functioned as intended. The current policy lowered fresh-ingestion cost against forced eager processing on this tiny corpus. INT8 vector payload compression is real and had small score errors, though it changed some ranks. Semantic retrieval recovered two lexical misses. Changed-region OCR preserved a changed amount, but delivered no measured runtime saving in these experiments.")
    p("<b>Claims the data do not support.</b> The work does not establish real-world accuracy, improved generative answers, multilingual transcription quality, a calibrated confidence score, a learned adaptive controller, general delta-OCR speedups, representative 10,000-file retrieval, or production concurrency/security. The absent-answer, invoice and timestamp failures should remain visible in any project presentation.")
    table(["Priority","Proposed next experiment or fix","Acceptance evidence to collect"],[
        ["1","Validate ASR spans against decoded media duration; inspect and flag invalid boundaries.","Zero negative/out-of-range spans; evaluate timestamp alignment on manually labeled speech. Do not infer alignment from valid bounds alone."],
        ["2","Add an answerability check using independent development and test sets with hard negatives.","Report positive retrieval, negative rejection and false-answer risk together; assess questions whose keywords occur in an insufficient source."],
        ["3","Score OCR/ASR names, identifiers and amounts explicitly; compare confidence gates with field-sensitive triggers.","Exact field accuracy, retries, CPU and wall time on natural degraded receipts and real recorded names; separate numeric normalization."],
        ["4","Profile OCR internals and compare reuse policies on varied edit families.","Paired full/delta timings, crop area, text correctness, fallback rate and cumulative ingest-plus-query cost; include crop resizing and selection overhead."],
        ["5","Build an independent, larger collection and compare channel/reranker/index choices.","Family-separated splits, multiple users/devices/languages, Recall@k, Hit@1, field fidelity, first-use/warm latency, RAM, full storage and concurrency."]
    ],[48,206,245])
    p("<b>Validity limits.</b> The same few assets answer many related queries; expected labels were hand-authored; the added set was created after corpus inspection; modality filters make top-five success easy; timing repetitions are few and share one machine and cached models. The scale corpus repeats vectors, field coverage is selected, and no blinded human answer review was performed. No significance claim is warranted.")
    note("Next-work rows are proposals, not completed experiments or deployed fixes. The production engine was not modified as part of this research. The main practical result is a clearer separation of file retrieval, exact evidence fidelity, answerability and processing cost.")

    page("11  Reproducibility and references", "Evidence files and how to repeat the study")
    p("Research harnesses are in research/. The recorded run is research/results/2026-11-20/. All scenario labels are outside playground/inbox/. Run from the repository root using the project virtual environment; cached models are expected under .secondbrain/models/.")
    for command in [
        ".venv\\Scripts\\python.exe -m pytest -q",
        ".venv\\Scripts\\python.exe research\\run_experiments.py --output research/results/reproduction",
        ".venv\\Scripts\\python.exe research\\run_followups.py --output research/results/reproduction",
        ".venv\\Scripts\\python.exe research\\run_ingest_control.py --output research/results/reproduction",
        ".venv\\Scripts\\python.exe research\\build_report.py --results research/results/reproduction"
    ]: p(escape(command),"code")
    p("Use a fresh output directory: the harness refuses to replace completed results. The main run defaults to three ingestion repetitions. If models are missing, prefetch them with brain --home .secondbrain models --audio before starting the offline experiment. Research-only dependencies include psutil, matplotlib and reportlab; observed package versions are recorded beside the evidence. Relative dates must remain consistent with fixture mtimes: regenerate the playground outside this run or use the recorded source manifest to understand date filtering.")
    p("<b>Evidence map.</b> manifest.json records source/code hashes and environment. ingestion.json and ingest_control.json contain per-file actions and extraction calls. retrieval.json and query_results.csv contain actual query outcomes. ablations.json includes validated channel rankings and quantization checks. delta_ocr.json, extraction.json, refinement.json and followups.json preserve quality probes. warm_latency.json, fresh_process_latency.json and scale.json preserve every timing sample. results.json, experiment_summary.csv and report_evidence.json collect summaries and derived values.")
    p("<b>Primary references.</b> Accessed 20 November 2026. These establish background, not this project's measured results.")
    for source in sources:
        p(f"[{source['id']}] {escape(source['authors'])} ({source['year']}). <link href=\"{source['url']}\" color=\"{TEAL}\">{escape(source['title'])}</link>.","reference")
    note("The HTML and PDF are generated from the same recorded evidence by build_report.py. Experiment databases and thumbnails are disposable local artifacts; raw JSON/CSV evidence is retained. No model training was performed and no paid external inference was used.")

    positives=[x for x in retrieval["hybrid"] if x["expected_files"]]
    for index,(label,subset) in enumerate((("Original scenarios",[x for x in positives if x["set"]=="original"]),("Added exploratory scenarios",[x for x in positives if x["set"]=="exploratory"])),1):
        page(f"Appendix A{index}  Query outcomes",label+" | actual full-hybrid search")
        rows=[]
        for x in subset:
            rows.append([x["query"]," / ".join(x["expected_files"]),x["results"][0]["name"] if x["results"] else "None",str(x["first_relevant_rank"])])
        table(["Query","Expected file(s)","First result","First relevant rank"],rows,[195,135,117,52])
        note("Expected file labels measure source relevance only. The exact duplicate is one asset with two file locations; it is not counted as a second retrieval vote. All expected assets were within the top five. Full IDs, aliases, channels, excerpt text and timing are available in retrieval.json.")
    page("Appendix B  Absent-answer queries", "Actual full-hybrid retrieval | all expected-answer lists were empty")
    negatives=[x for x in retrieval["hybrid"] if not x["expected_files"]]
    table(["Query","First returned candidate","Candidates returned"],[[x["query"],x["results"][0]["name"] if x["results"] else "None",str(len(x["results"]))] for x in negatives],[256,160,83])
    p("These queries ask for facts absent from the indexed evidence. Some candidate files are topically related, but none establishes the requested fact. Candidate count is capped at five; an empty list would count as retrieval abstention. A separately evaluated generation stage could still decline to answer after retrieving these files, but that behavior was not tested here.")
    p("The original no-answer scenario reproduces the limitation recorded in playground/verification.json. The added hard negatives broaden it to insufficient evidence within related topics. They remain exploratory labels created after inspection of the tiny corpus.")

    # Render both versions from the shared page model.
    for name,path in (("Arial","C:/Windows/Fonts/arial.ttf"),("Arial-Bold","C:/Windows/Fonts/arialbd.ttf"),("Arial-Italic","C:/Windows/Fonts/ariali.ttf")):
        pdfmetrics.registerFont(TTFont(name,path))
    pdfmetrics.registerFontFamily("Arial",normal="Arial",bold="Arial-Bold",italic="Arial-Italic",boldItalic="Arial-Bold")
    styles={
        "body":ParagraphStyle("body",fontName="Arial",fontSize=9.3,leading=13.5,textColor=colors.HexColor(NAVY),spaceAfter=9),
        "note":ParagraphStyle("note",fontName="Arial-Italic",fontSize=8.1,leading=11.4,textColor=colors.HexColor(GRAY),spaceBefore=4,spaceAfter=7),
        "deck":ParagraphStyle("deck",fontName="Arial",fontSize=14,leading=20,textColor=colors.HexColor(TEAL),spaceAfter=18),
        "code":ParagraphStyle("code",fontName="Courier",fontSize=7.9,leading=11.5,textColor=colors.HexColor(NAVY),backColor=colors.HexColor("#edf4f3"),borderPadding=6,spaceAfter=9),
        "reference":ParagraphStyle("reference",fontName="Arial",fontSize=8.3,leading=11.8,spaceAfter=8,textColor=colors.HexColor(NAVY)),
        "title":ParagraphStyle("title",fontName="Arial-Bold",fontSize=23,leading=28,textColor=colors.HexColor(NAVY),spaceAfter=9),
        "subtitle":ParagraphStyle("subtitle",fontName="Arial",fontSize=9.2,leading=13,textColor=colors.HexColor(TEAL),spaceAfter=18),
        "cell":ParagraphStyle("cell",fontName="Arial",fontSize=8.1,leading=11,textColor=colors.HexColor(NAVY)),
        "head":ParagraphStyle("head",fontName="Arial-Bold",fontSize=8.1,leading=11,textColor=colors.white)
    }
    story=[]
    html_sections=[]
    for number,item in enumerate(pages):
        if number: story.append(PageBreak())
        story.append(Paragraph(escape(item["title"]),styles["title"]))
        story.append(Paragraph(escape(item["subtitle"]),styles["subtitle"]))
        parts=[f'<article id="page-{number+1}"><div class="folio">Adaptive Second Brain / Research / {number+1:02d}</div><h1>{escape(item["title"])}</h1><p class="subtitle">{escape(item["subtitle"])}</p>']
        for element in item["elements"]:
            if element[0]=="p":
                _,text,kind=element
                story.append(Paragraph(text,styles[kind]))
                htmltext=text.replace('<link href=', '<a href=').replace('</link>','</a>')
                parts.append(f'<p class="{kind}">{htmltext}</p>')
            elif element[0]=="table":
                _,heads,rows,widths=element
                cells=[[Paragraph(escape(str(x)),styles["head"]) for x in heads]]+[[Paragraph(escape(str(x)),styles["cell"]) for x in row] for row in rows]
                t=Table(cells,colWidths=widths,repeatRows=1,hAlign="LEFT")
                t.setStyle(TableStyle([("BACKGROUND",(0,0),(-1,0),colors.HexColor(NAVY)),("VALIGN",(0,0),(-1,-1),"TOP"),("LEFTPADDING",(0,0),(-1,-1),7),("RIGHTPADDING",(0,0),(-1,-1),7),("TOPPADDING",(0,0),(-1,-1),6),("BOTTOMPADDING",(0,0),(-1,-1),6),("ROWBACKGROUNDS",(0,1),(-1,-1),[colors.HexColor("#eef4f4"),colors.white]),("LINEBELOW",(0,0),(-1,0),.5,colors.HexColor(NAVY))]))
                story.extend([t,Spacer(1,12)])
                parts.append('<table><thead><tr>'+''.join(f'<th>{escape(str(x))}</th>' for x in heads)+'</tr></thead><tbody>'+''.join('<tr>'+''.join(f'<td>{escape(str(x))}</td>' for x in row)+'</tr>' for row in rows)+'</tbody></table>')
            elif element[0]=="image":
                _,name,caption=element
                story.append(Image(str(figures/name),width=499,height=187.125))
                story.append(Paragraph(escape(caption),styles["note"]))
                parts.append(f'<figure><img src="figures/{name}" alt="{escape(caption)}"><figcaption>{escape(caption)}</figcaption></figure>')
        parts.append('</article>')
        html_sections.append(''.join(parts))
    def footer(canvas,doc):
        canvas.saveState()
        canvas.setFont("Arial",7.5)
        canvas.setFillColor(colors.HexColor(GRAY))
        canvas.drawString(48,23,"ADAPTIVE SECOND BRAIN  /  EXPERIMENTAL RESEARCH  /  20 NOV 2026")
        canvas.drawRightString(A4[0]-48,23,str(doc.page))
        canvas.restoreState()
    document=SimpleDocTemplate(str(pdfpath),pagesize=A4,leftMargin=48,rightMargin=48,topMargin=43,bottomMargin=45,title="Adaptive Second Brain - Experimental Research Report",author="Adaptive Second Brain project",subject="Real-model experiments on retrieval quality, processing reuse, OCR, ASR, storage and latency")
    document.build(story,onFirstPage=footer,onLaterPages=footer)
    css="""*{box-sizing:border-box}body{margin:0;background:#e8eeee;color:#183444;font:15px/1.55 Arial,sans-serif}nav{padding:18px 30px;background:#183444;color:white;position:sticky;top:0}nav a{color:#bde2d7;margin-left:18px}main{max-width:930px;margin:30px auto}article{background:white;padding:48px 58px;margin:0 0 28px;box-shadow:0 3px 20px #18344412}h1{font-size:30px;line-height:1.2;margin:12px 0}.folio{font-size:11px;letter-spacing:.12em;color:#586b76;text-transform:uppercase}.subtitle{color:#1c6c68;font-size:14px;margin:0 0 24px}.deck{font-size:21px;line-height:1.4;color:#1c6c68}.note,figcaption{font-size:12px;line-height:1.5;color:#586b76;font-style:italic}.note{border-left:3px solid #a8cdc4;padding-left:12px}table{width:100%;border-collapse:collapse;margin:18px 0;font-size:12px;line-height:1.45;table-layout:auto}th{text-align:left;background:#183444;color:white}th,td{vertical-align:top;padding:9px}tbody tr:nth-child(odd){background:#eef4f4}figure{margin:16px 0}img{max-width:100%;height:auto}.code{background:#edf4f3;padding:9px;font:11px/1.5 Consolas,monospace;overflow-wrap:anywhere}.reference{font-size:13px}a{color:#1c6c68}@page{size:A4;margin:14mm} @media print{body{background:white;font-size:9.3pt}nav{display:none}main{margin:0;max-width:none}article{box-shadow:none;margin:0;padding:0;break-after:page}article:last-child{break-after:auto}h1{font-size:23pt}table{font-size:8pt}tr{break-inside:avoid}.note,figcaption{font-size:8pt}.deck{font-size:14pt}.folio{display:none}}"""
    html='<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Adaptive Second Brain - Research Report</title><style>'+css+'</style></head><body><nav>Research report <a href="../pdf/adaptive_secondbrain_research_report.pdf">PDF version</a><a href="#page-1">Start</a><a href="#page-13">Query appendix</a></nav><main>'+''.join(html_sections)+'</main></body></html>'
    (output/"report.html").write_text(html,encoding="utf-8")
    (output/"report_content.json").write_text(json.dumps(pages,indent=2),encoding="utf-8")
    print(json.dumps({"pdf":str(pdfpath),"html":str(output/"report.html"),"planned_pages":len(pages),"derived":derived},indent=2))


if __name__=="__main__": main()
