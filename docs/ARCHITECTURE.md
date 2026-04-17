# Architecture

## Goal

The Literature Review Agent is designed as a staged workflow for turning a research question into a structured literature review using deterministic retrieval in Python and reasoning-heavy synthesis in Gemini.

The emphasis is on separation of concerns:

- Python handles retrieval, ranking, application flow, and state
- Gemini handles the reasoning-heavy steps
- each stage produces an inspectable artifact

## Pipeline

### 1. Planning

File: [src/literature_review_agent/prompts.py](../src/literature_review_agent/prompts.py)

The agent first decomposes the user question into a set of sub-questions. This helps the later extraction stage stay focused on the same analytical frame across papers.

Output:

- `sub_questions`

### 2. Retrieval, Fallback, and Ranking

File: [src/literature_review_agent/retriever.py](../src/literature_review_agent/retriever.py)

The app first tries Semantic Scholar for the user question. If that fails, including on rate limits, it falls back to Crossref. Successful retrievals are cached locally so repeated runs avoid unnecessary API traffic.

Retrieval sources:

- Semantic Scholar
- Crossref

Current ranking signals:

- title and abstract overlap with important question terms
- citation count
- publication recency
- abstract availability
- venue availability

Each selected paper includes a human-readable ranking reason so the UI can explain why it was kept.

### 3. Paper Extraction

File: [src/literature_review_agent/agent.py](../src/literature_review_agent/agent.py)

Each selected paper is processed independently into a structured record.

Output fields:

- `title`
- `summary`
- `methods`
- `findings`
- `limitations`
- `relevance_score`

This stage converts unstructured text into comparable evidence objects.

### 4. Comparison

The extracted records are passed into a comparison step that surfaces common methods, common findings, differences, conflicts, and research gaps.

Output:

- `common_methods`
- `common_findings`
- `differences`
- `conflicts`
- `gaps`

### 5. Final Synthesis

The final stage uses the question, plan, extracted records, and comparison output to write a review with consistent sections.

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

### [src/literature_review_agent/agent.py](../src/literature_review_agent/agent.py)

Coordinates the multi-stage workflow and assembles the final `ReviewResult`.

### [src/literature_review_agent/gemini_client.py](../src/literature_review_agent/gemini_client.py)

Wraps Gemini requests for both JSON and text generation. It also normalizes fenced JSON responses before parsing.

### [src/literature_review_agent/retriever.py](../src/literature_review_agent/retriever.py)

Handles retrieval fallback, local caching, deterministic scoring, and ranking.

### [src/literature_review_agent/schemas.py](../src/literature_review_agent/schemas.py)

Defines lightweight result models used by the UI and orchestration layer.

### [src/literature_review_agent/utils.py](../src/literature_review_agent/utils.py)

Contains helper utilities used by the pipeline.

## Why The Intermediate Trace Matters

The trace exists to make each run inspectable. Instead of exposing only a final synthesized answer, the app also shows:

- the sub-question plan
- per-paper extraction records
- comparison output
- a preview of the final synthesis

This makes debugging easier and keeps the workflow more transparent.

## Current Scope

This repository currently uses automated retrieval plus abstract-level evidence extraction:

- retrieval and ranking are kept outside the LLM for lower token usage
- the Gemini stages focus on extraction, comparison, and synthesis
- the app remains lightweight and inspectable

The next major iteration is to add caching, citation-aware enrichment, and full-paper ingestion.
