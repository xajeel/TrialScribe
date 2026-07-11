# TrialScribe

**TrialScribe** is an AI-powered clinical research assistant that researches and drafts clinical trial protocol documents in the **ICH M11 format**. A multi-agent pipeline (planner → researcher → writer → composer) built with LangGraph gathers evidence from PubMed, ClinicalTrials.gov data, and domain-restricted web search (Tavily), then composes structured, citation-backed protocol sections.

## Features

- **Multi-agent workflow** — planner, researcher, and writer agents orchestrated with LangGraph
- **Evidence retrieval** — PubMed, clinical trial data processing, and Tavily web search restricted to trusted domains
- **M11 protocol drafting** — generates complete outlines or specific sections of a clinical trial protocol
- **Two interfaces** — FastAPI backend and a Streamlit app

## Getting Started

```
pip install uv
```

Use the uv runner to start the process:

```
uv sync


uv run streamlit run app.py

or 

uv run main.py
```
