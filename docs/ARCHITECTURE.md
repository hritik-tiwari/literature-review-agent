# Architecture

## Goal

The Literature Review Agent is designed as a staged workflow for turning a research question into a structured literature review using deterministic retrieval in Python and reasoning-heavy synthesis in Gemini.

The emphasis is on separation of concerns:

- Python handles query planning, retrieval, deduplication, ranking, application flow, and state
- Gemini handles the reasoning-heavy steps
- each stage produces an inspectable artifact

## Pipeline

### 1. Query Planning

File: [src/literature_review_agent/query_planner.py](../src/literature_review_agent/query_planner.py)

The app first converts the user question into source-specific retrieval queries. This keeps retrieval deterministic and avoids relying on a single raw natural-language query across all APIs.

Outputs include:

- keyword list
- detected domain phrases
- Semantic Scholar query
- arXiv query
- Crossref query

### 2. Retrieval, Deduplication, and Ranking

File: [src/literature_review_agent/retriever.py](../src/literature_review_agent/retriever.py)

The app retrieves from multiple sources and merges overlapping records before ranking them. Successful retrievals are cached locally so repeated runs avoid unnecessary API traffic.

Retrieval sources:

- Semantic Scholar
- arXiv
- Crossref

Current ranking signals:

- title and abstract overlap with important question terms
- citation count
- publication recency
- abstract coverage
- venue availability
- source quality weighting
- multi-source confirmation bonus

### Deduplication Strategy

Papers are deduplicated across sources using DOI-like identifiers when available, with normalized-title fallback when they are not. When duplicate records are merged:

- higher-priority sources keep primary metadata ownership
- missing fields are filled from secondary sources
- source provenance is preserved in `sources_seen`

### 3. Paper Extraction

File: [src/literature_review_agent/agent.py](../src/literature_review_agent/agent.py)

The selected papers are sent in a single batch extraction call so the system can reduce request count while still producing one structured evidence object per paper.

Output fields:

- `title`
- `summary`
- `methods`
- `findings`
- `limitations`
- `relevance_score`

This stage converts unstructured metadata and abstracts into comparable evidence objects.

### 4. Comparison

The extracted records are passed into a comparison step that surfaces common methods, common findings, differences, conflicts, and research gaps.

Output:

- `common_methods`
- `common_findings`
- `differences`
- `conflicts`
- `gaps`

### 5. Final Synthesis

The final stage uses the question, sub-question plan, extracted records, and comparison output to write a review with consistent sections.

Current sections:

- Research Question
- Overview
- Methods Across Papers
- Main Findings
- Conflicts and Disagreements
- Limitations in the Literature
- Research Gaps
- Suggested Next Steps

## Key Modules

### [app.py](../app.py)

Provides the Streamlit UI, validates required input, runs the agent, and renders final output plus trace artifacts.

### [src/literature_review_agent/query_planner.py](../src/literature_review_agent/query_planner.py)

Builds deterministic source-specific search queries from the user question.

### [src/literature_review_agent/retriever.py](../src/literature_review_agent/retriever.py)

Handles multi-source retrieval, deduplication, local caching, deterministic scoring, and ranking.

### [src/literature_review_agent/agent.py](../src/literature_review_agent/agent.py)

Coordinates the multi-stage workflow and assembles the final `ReviewResult`.

### [src/literature_review_agent/gemini_client.py](../src/literature_review_agent/gemini_client.py)

Wraps Gemini requests for both JSON and text generation. It also normalizes fenced JSON responses before parsing.

### [src/literature_review_agent/schemas.py](../src/literature_review_agent/schemas.py)

Defines lightweight result models used by the UI and orchestration layer.

## Why The Intermediate Trace Matters

The trace exists to make each run inspectable. Instead of exposing only a final synthesized answer, the app also shows:

- the retrieval query plan
- the selected paper set with provenance
- per-paper extraction records
- comparison output
- a preview of the final synthesis

This makes debugging easier and keeps the workflow more transparent.

## Current Scope

This repository currently uses automated retrieval plus abstract-level evidence extraction:

- retrieval and ranking are kept outside the LLM for lower token usage
- the Gemini stages focus on extraction, comparison, and synthesis
- the app remains lightweight and inspectable
- cross-source merging reduces duplicate evidence and improves provenance tracking
- batched extraction reduces request count and makes the workflow more practical under free-tier API limits

The next major iteration is to add full-paper ingestion, stronger venue/domain signals, and evaluator-style quality checks.
