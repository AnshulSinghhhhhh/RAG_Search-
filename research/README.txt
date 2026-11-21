ADAPTIVE SECOND BRAIN - RESEARCH EVALUATION
Recorded study: 20 November 2026

DELIVERABLES
  ../output/pdf/adaptive_secondbrain_research_report.pdf
  ../output/research/report.html
  results/2026-11-20/experiment_summary.csv
  results/2026-11-20/query_results.csv

The 15-page report covers 10 experiment groups: existing regression tests,
eager/current ingestion, a deduplication-controlled OCR comparison, isolated
delta OCR, retrieval channel ablations, absent-answer behavior, exact OCR/ASR
fields and timestamps, quantization/storage, latency/scaling, and selective
OCR refinement. It includes all 42 query outcomes and primary references.

All reported results came from actual commands or real-model inference.
The existing tests use deterministic doubles and are reported separately.
The corpus and added queries are synthetic and exploratory, not held out.
The application source and the existing .secondbrain database were not edited.

REPEAT THE EXPERIMENTS
Run from the repository root with Python 3.11 and the project environment.
Models must already be cached in .secondbrain/models. If missing, use:
  .venv\Scripts\python.exe -m secondbrain --home .secondbrain models --audio

Research-only packages used: psutil, matplotlib and reportlab.
requirements-observed.txt records the observed environment, excluding the
editable project installation. Install the project itself with its audio
and dev extras when creating a new environment.

Use a new output directory to preserve recorded evidence:
  .venv\Scripts\python.exe -m pytest -q
  .venv\Scripts\python.exe research\run_experiments.py --output research/results/reproduction
  .venv\Scripts\python.exe research\run_followups.py --output research/results/reproduction
  .venv\Scripts\python.exe research\run_ingest_control.py --output research/results/reproduction
  .venv\Scripts\python.exe research\build_report.py --results research/results/reproduction

The report builder is the narrative for this recorded study. Review its
interpretations before using it for a run with different data/results.
Relative-date queries follow the production engine's current local date:
fixture mtimes must correspond to the intended month. Regenerating fixtures
changes the input hashes and constitutes a new study rather than the exact
recorded run. Fresh-process latency retains the model and OS caches.

EVIDENCE
  manifest.json              Input/code hashes, mtimes, environment/settings
  integrity.json             Final source checks and model/harness hashes
  unit_tests.json            Actual initial pytest output (23 passed)
  ingestion.json             Per-file actions and extraction timings
  ingest_control.json        Dedup-only/full-OCR control and eager retrieval
  cached_reindex.json        Five unchanged re-index measurements
  retrieval.json             Actual hybrid/lexical responses and query timings
  ablations.json             Channel replay, validation and quantization checks
  delta_ocr.json             Paired full/delta OCR and transformation probes
  extraction.json            Selected fields, transcripts and raw WER
  refinement.json            Initial 400px receipt probe
  followups.json             Four resolution levels, audio bounds, score sweep
  warmups.json               First inference with each cached model
  warm_latency.json          Every repeated warm query timing
  fresh_process_latency.json Three fresh-process searches and startup timings
  scale.json                 Repeated-vector scan timings (not accuracy)
  results.json               Main machine-readable summaries
  report_evidence.json       Values derived for the written report
  experiment_summary.csv    Compact comparison table
  query_results.csv         Query outcomes suitable for independent analysis

Experiment collections/thumbnails are ignored by Git and disposable.
The JSON/CSV evidence and scripts are the retained research record.
No production fixes, model training, or generative-answer evaluation were
performed. Proposed improvements in the report remain future work.
