# Literature Review Agent

A Gemini-powered agent that turns a research question and a small set of paper texts into a structured literature review.

## What makes it agentic

This is not a one-shot summarizer. The system uses a multi-step workflow:

1. plan sub-questions
2. extract structured paper evidence
3. compare methods and findings across papers
4. detect conflicts and gaps
5. synthesize a final review

Each stage produces structured intermediate state so the review is traceable and easier to discuss in interviews.

## Interview framing

You can describe it like this:

> I built a literature review agent rather than a simple summarizer. The system decomposes a research question, extracts evidence from multiple papers, compares results across sources, flags conflicts, and then writes a structured review. I wanted something that behaved more like a research assistant than a chatbot prompt.

## Features

- Gemini-based orchestration
- Structured JSON outputs for each step
- Agent trace so you can inspect what happened
- Streamlit UI for demoing
- Support for pasted abstracts or notes from multiple papers

## Setup

1. Install dependencies:

```bash
python -m pip install -r requirements.txt
```

2. Set your Gemini API key:

PowerShell:

```powershell
$env:GEMINI_API_KEY="your_key_here"
```

Git Bash:

```bash
export GEMINI_API_KEY="your_key_here"
```

3. Run the app:

```bash
streamlit run app.py
```

## Project structure

```text
literature_review_agent/
├── app.py
├── requirements.txt
├── README.md
└── src/
    ├── literature_review_agent/
    │   ├── __init__.py
    │   ├── agent.py
    │   ├── gemini_client.py
    │   ├── prompts.py
    │   ├── schemas.py
    │   └── utils.py
```

## Future improvements

- PDF ingestion
- citation-aware output
- export to Markdown
- paper clustering by theme
- evaluator for output quality

