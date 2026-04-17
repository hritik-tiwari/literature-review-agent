# Architecture

## Goal

The Literature Review Agent is designed as a staged LLM workflow for turning a research question and a small set of paper abstracts into a structured literature review.

The emphasis is on separation of concerns:

- Python handles application flow and state
- Gemini handles the reasoning-heavy steps
- each stage produces an inspectable artifact

## Pipeline

### 1. Planning

File: [src/literature_review_agent/prompts.py](../src/literature_review_agent/prompts.py)

The agent first decomposes the user question into a set of sub-questions. This helps the later extraction stage stay focused on the same analytical frame across papers.

Output:

- `sub_questions`

### 2. Paper Extraction

File: [src/literature_review_agent/agent.py](../src/literature_review_agent/agent.py)

Each paper is processed independently into a structured record.

Output fields:

- `title`
- `summary`
- `methods`
- `findings`
- `limitations`
- `relevance_score`

This stage converts unstructured text into comparable evidence objects.

### 3. Comparison

The extracted records are passed into a comparison step that surfaces common methods, common findings, differences, conflicts, and research gaps.

Output:

- `common_methods`
- `common_findings`
- `differences`
- `conflicts`
- `gaps`

### 4. Final Synthesis

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

### [src/literature_review_agent/schemas.py](../src/literature_review_agent/schemas.py)

Defines lightweight result models used by the UI and orchestration layer.

### [src/literature_review_agent/utils.py](../src/literature_review_agent/utils.py)

Contains helper utilities such as splitting multiple papers from a shared input block.

## Why The Intermediate Trace Matters

The trace exists to make each run inspectable. Instead of exposing only a final synthesized answer, the app also shows:

- the sub-question plan
- per-paper extraction records
- comparison output
- a preview of the final synthesis

This makes debugging easier and keeps the workflow more transparent.

## Current Scope

This repository currently focuses on the review pipeline itself, not on automated paper retrieval. That is intentional for the MVP:

- it keeps API usage smaller
- it isolates the reasoning workflow
- it makes it easier to validate each stage independently

The next major iteration is to add deterministic retrieval and ranking in Python before the LLM steps.
