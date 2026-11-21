# Product

<!-- impeccable:product-schema 1 -->

## Platform
web

## Stack
Confirmed: Python-served frontend, one installation, no Node.js build. The user chose building directly in code.

## Users
People downloading this project from GitHub who want to index selected local files or folders and retrieve screenshots, receipts, and voice notes through either CMD or a local visual interface.

## Product Purpose
A local second brain with shared ingestion and search logic behind separate CLI commands and a browser interface. Users control the folders being indexed.

## Positioning
Explore efficiency through exact-duplicate reuse, changed-region OCR, compact embeddings, and selective refinement. Efficiency gains are experimental and must be measured, not invented.

## Operating Context
Windows CMD is explicitly requested. Keep Python commands portable. A repository playground contains synthetic files and explicit search scenarios. Runtime data stays local; initial model downloads require internet access.

## Capabilities and Constraints
Index one file or a recursive folder; manage sources; search by meaning, keywords, modality, and date; inspect source images and timestamped audio; show indexing progress and actual storage measurements. Run on localhost. No cloud hosting requested.

## Evidence on Hand
The repository initially contained no source code or existing design. The original user-provided architecture describes multimodal RAG for screenshots and voice notes. There are no measured speedups or customer claims.

## Product Principles
- CLI and UI operate on the same collection.
- Preserve originals and show evidence.
- Never substitute synthetic embeddings for semantic models silently.
- Clearly distinguish cached results, pending work, and failures.
- Make the first successful local search easy.
