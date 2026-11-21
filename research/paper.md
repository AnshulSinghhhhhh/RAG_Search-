# Adaptive Second Brain
## Local multimodal retrieval with verifiable source evidence

Adaptive Second Brain project · Technical paper · 21 November 2026

### Abstract

Personal archives mix screenshots, receipts, notes, and audio. We present a CPU-based system that indexes these files locally, combines keyword and semantic retrieval, and links results to the underlying evidence. An exploratory baseline on 11 unique synthetic assets returned a relevant file in the top five for 30 of 30 answerable queries. All 12 queries whose answers were absent still returned at least one candidate. On three repeated ingestion trials, the combined adaptive path took 8.73 s versus 10.09 s for eager processing. When exact deduplication was held constant, the addition of changed-region OCR increased median ingestion time from 8.50 s to 8.87 s. The 0.2.0 follow-up adds source verification, per-asset ranking limits, bounded audio timestamps, and conservative extraction for receipt totals, invoice identifiers, and product prices. On a separate nine-case synthetic fixture set, the updated system cited the correct value in all three positive cases and declined all six absent or conflicting cases, with and without an explicit OCR retry. These results characterize behavior on small fixtures and motivate larger evaluations of answerability and processing cost.

**Keywords** Local search, multimodal retrieval, evidence attribution, OCR, abstention

### 1. Introduction

A user retrieving a fact from a personal archive needs two things. The system must find the relevant file, and that file must contain evidence for the specific fact. A screenshot can depict the right product without showing its price. A recording can concern the right meeting while omitting its dial-in code. An asset-level hit therefore supplies limited evidence about whether a question can be answered.

The prototype explores three practical questions. How useful is hybrid retrieval on a small mixed collection? Which processing optimizations save work when exact deduplication is controlled? Can a conservative field lookup expose uncertainty while giving users a direct way to verify the result?

We contribute a runnable local implementation, a measured comparison of retrieval and ingestion variants, and documented failure cases that informed three reliability repairs. We then evaluate a limited evidence workflow on a separate synthetic set with positive, missing-field, and conflicting cases.

<!-- pagebreak -->

### 2. System design

**Ingestion.** A SHA-256 digest identifies each distinct asset. Separate location records retain duplicate paths. The image pipeline combines RapidOCR with a CLIP image embedding [2]. Text notes and extracted text use BGE embeddings [5], while optional Whisper inference produces timestamped transcript segments [4]. Asset and chunk records, an FTS5 index, and quantized vectors share an embedded SQLite database.

**Efficient reuse and storage.** The changed-region OCR policy nominates a same-dimension image using a perceptual hash, computes a native-resolution pixel diff, expands the crop across affected text boxes, and falls back to full OCR when the crop is too large. Each stored vector uses one signed byte per component and per-vector scale and norm metadata. The positive scale cancels during cosine normalization of a quantized vector.

**Retrieval.** Searches apply file type, folder, and date filters before ranking. Keyword, BGE text, and CLIP visual channels rank candidates separately. Reciprocal Rank Fusion adds 1/(60 + rank) per available channel, with a single rank per asset [3]. Dense ranking scans the matching vectors exactly. The app preserves paths, text excerpts and audio positions so a user can inspect the source.

**Evidence.** The default workflow returns excerpts. A local Ollama model can optionally generate prose from retrieved passages, which is related to retrieval-augmented generation [1]. Version 0.2.0 adds a deterministic path for three exact field types. This path checks requested subject terms and field labels or currency context within the retrieved image OCR. Successful answers include a filename, a quoted line and image coordinates. Missing or conflicting readings produce an insufficient-evidence status. An explicit retry uses a crop when localizable and presents alternatives without replacing the original field reading.

### 3. Evaluation protocol

**Baseline, 20 November.** The original playground contained 12 paths and 11 unique assets: seven images, two notes, and two voice recordings. The 42 queries included 30 answerable cases and 12 whose requested facts were absent. Query labels were outside the indexed folder. The study was run on Windows with Python 3.11.9, four configured model threads, and six physical CPU cores. It compared eager ingestion, a combined adaptive path, dedup-only full OCR and dedup with changed-region OCR. The explore-and-measure process used a synthetic corpus whose content informed some query labels.

**Follow-up, 21 November.** Nine new rendered images covered three field types and distinct merchant or product names. Each field type had one positive, one missing, and one conflicting case. RapidOCR and hybrid retrieval ran on the real pipeline, first with ordinary Ask and then with a user-requested retry per query. The test counted exact values from the expected asset and insufficient-evidence outcomes. Deterministic regression tests were run separately to isolate overwrite, ranking, audio, and retry behavior.

<!-- pagebreak -->

### 4. Baseline results

The baseline separates retrieval relevance, extraction fidelity, and system cost.

| Retrieval mode | Hit@1 | Hit@5 | MRR@5 | Empty on absent queries |
| --- | --- | --- | --- | --- |
| Hybrid | 27/30 | 30/30 | 0.950 | 0/12 |
| Keyword only | 27/30 | 28/30 | 0.911 | 2/12 |

**Table 1.** Hit@k requires any expected asset in the top k. MRR@5 averages the reciprocal rank of the first expected asset and assigns zero for a miss. Empty search results measure retrieval abstention. The experiment did not evaluate optional generated answers.

The top-five result needs the context of the candidate pool. A uniform random ranking among each query's filtered candidates had an expected hit@5 of 83.6%. Several filtered pools had only two assets. Top-one ranking and the false-candidate results provide more discrimination here. In a separate repeated warm-query run (25 calls per mode), median latency was 27.2 ms for hybrid search and 10.3 ms for keyword search.

| Ingestion comparison | Median wall time | Interpretation |
| --- | --- | --- |
| Eager processing | 10.09 s | Baseline without the combined reuse path |
| Combined adaptive path | 8.73 s | 13.4% lower median in this comparison |
| Exact deduplication + full OCR | 8.50 s | Control for changed-region OCR |
| Exact deduplication + changed-region OCR | 8.87 s | 4.3% higher median against the control |

**Table 2.** Three trials per condition. The first pair and the controlled pair came from separate experiment groups. The minima and maxima for the controlled pair overlap. Reduced crop area alone does not establish an end-to-end latency improvement.

The 18 stored vectors occupied 7,808 payload bytes, compared with a 31,232-byte float32 equivalent. Vector payload is only part of the collection. The measured database used 151,552 bytes and the model cache stored about 823 MB in the recorded setup. Across 370 cosine comparisons, mean absolute error from quantization was approximately 0.00095. Top-one agreement was 62 of 66 channel comparisons. These are fixture-specific storage and score measurements.

Extraction matched all 12 selected image-field checks in the full-resolution fixtures. Two word edits in 56 reference words gave a raw word error rate of 3.6% over two recordings, including the café name “Juniper” read as “Jennifer.” In a degraded receipt probe, average OCR confidence near 0.938 coexisted with an incorrect invoice identifier. Six recorded refinement attempts on degraded receipts produced zero accepted updates under the original policy.

<!-- pagebreak -->

### 5. Reliability changes and follow-up results

Three implementation failures informed the 0.2.0 update. Each repair has a repeatable test that isolates it from pretrained-model variability.

| Failure | 0.2.0 change and check |
| --- | --- |
| Stale OCR after an overwrite | A replaced image could be compared with itself through the predecessor's old path. Verify the predecessor's digest, trying another unchanged alias or running full OCR if needed. A replacement test checks that the old price stays with an unchanged copy only. |
| Chunk truncation hides relevant files | A 134-chunk document filled the 120-chunk channel quota before fusion, excluding another matching file. Rank each asset by its best chunk before applying the quota. Both keyword and dense regressions require the shorter file to remain eligible. |
| Speech timestamp beyond the original | One recorded segment ended at 17.60 s in a 12.27 s WAV. Clamp overlapping intervals to the source duration and discard invalid intervals. A real-model replay on the same WAV ended at 12.2658 s and recorded the adjustment. |

**Table 3.** The overwrite and candidate-crowding probes are deterministic reproductions. The audio replay used the bundled voice memo and cached models. None measures the prevalence of the defect in personal archives.

Older image and audio records can be reprocessed with a resumable repair command. The field answer path uses only current image OCR whose source bytes still match the indexed asset. A receipt total is tied to a total label, an invoice identifier to a label or recognized prefix, and a product price to the displayed product and monetary context. A plausible change in a digit after a retry is shown as a conflict. Neither the similarity score nor the image's average OCR confidence serves as a probability of answerability.

| Follow-up condition | Exact value and correct source | Missing/conflict declines | OCR calls | p95 wall time |
| --- | --- | --- | --- | --- |
| Ordinary Ask | 3/3 | 6/6 | 0 | 0.694 s |
| Explicit OCR retry | 3/3 | 6/6 | 9 | 1.347 s |

**Table 4.** Each row contains nine requests in the recorded sequence. The same fixtures were used in both conditions. Latencies include retrieval, evidence verification, and any requested retry. They describe this run, including initial model use in the sequence. The sample provides limited information about latency tails.

The field evaluation demonstrates the supported behavior on clear examples. The measured retry added work without changing the nine final decisions. A separate deterministic regression shows how retry can recover a missing identifier and how a conflicting reading stays visible. Evidence remains inspectable in both the terminal and the browser.

<!-- pagebreak -->

### 6. Limitations and future work

The baseline and follow-up use two small synthetic collections. Repeated queries on a few assets are correlated, original labels were partly written against known fixtures, and voice transcription uses two short synthesized recordings. Differences in layout, language, OCR error patterns and archive size can change the results. Bounded timestamps establish valid playback ranges. Verifying word-level alignment requires separately annotated recordings. No inference about optional Ollama accuracy, multilingual performance, or production latency follows from this study.

The field rules favor explicit wording and clear visual labels. Presented values still depend on OCR and can be wrong even when linked to a source. Absolute score cutoffs cannot resolve examples where a file is highly related but omits the requested fact. Future work should split near-duplicate families across tuning and held-out sets, include scanned and noisy documents, and jointly report exact-field accuracy, support coverage, unsupported-answer rate, and time to verify the source. Larger and more varied collections should be used before deciding whether any approximate vector index is needed.

### 7. Reproducibility

The [public repository](https://github.com/AnshulSinghhhhhh/RAG_Search-) contains application code, the two fixture sets, query definitions, and evidence. The 20 November baseline is associated with commit 3c3fd13 and retained in the [baseline results](https://github.com/AnshulSinghhhhhh/RAG_Search-/tree/main/research/results/2026-11-20). The [0.2.0 field results](https://github.com/AnshulSinghhhhhh/RAG_Search-/blob/main/research/results/2026-11-21/field_evaluation.json) include a case-manifest digest, package versions, timings and case-level outcomes. The [research instructions](https://github.com/AnshulSinghhhhhh/RAG_Search-/blob/main/research/README.txt) describe how to reproduce each study with a fresh output path. The final local implementation passed 36 automated tests. These tests establish covered program behavior separately from measured model accuracy.

### References

[1] Lewis, P., Perez, E., Piktus, A., et al. (2020). Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks. NeurIPS 33. [arXiv:2005.11401](https://arxiv.org/abs/2005.11401).

[2] Radford, A., Kim, J. W., Hallacy, C., et al. (2021). Learning Transferable Visual Models From Natural Language Supervision. ICML, PMLR 139, 8748-8763. [Publication](https://proceedings.mlr.press/v139/radford21a.html).

[3] Cormack, G. V., Clarke, C. L. A., and Büttcher, S. (2009). Reciprocal Rank Fusion Outperforms Condorcet and Individual Rank Learning Methods. SIGIR, 758-759. [Author copy](https://cormack.uwaterloo.ca/cormack/cormacksigir09-rrf.pdf).

[4] Radford, A., Kim, J. W., Xu, T., et al. (2023). Robust Speech Recognition via Large-Scale Weak Supervision. ICML, PMLR 202, 28492-28518. [Publication](https://proceedings.mlr.press/v202/radford23a.html).

[5] Beijing Academy of Artificial Intelligence. (2023). BGE Small English v1.5. [Model card](https://huggingface.co/BAAI/bge-small-en-v1.5).
