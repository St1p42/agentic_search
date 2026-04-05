# Agentic Search

Agentic Search is a bounded multi-stage pipeline that takes a topic query, searches the web, gathers lightweight evidence, extracts structured entities with field-level provenance, and returns a top-10 table.

The easiest way to demo it locally is the built-in browser page:

- [http://127.0.0.1:8000/demo](http://127.0.0.1:8000/demo)

## High-Level Approach

The active implementation uses a deterministic orchestrator with a fixed stage order:

1. Planner
2. Searcher
3. Brave LLM Context helper
4. ExtractorLight
5. Assessor
6. Evidence Store Builder
7. Extractor
8. Thin Finalizer

Key design decisions:

- Planner owns semantic query rewrites based on likely user intent slices.
- Searcher is mechanical: execute queries, prune weak URLs, merge results, and build a bounded shortlist.
- ExtractorLight exists to establish candidate entities before any full field extraction.
- Assessor adds source semantics: source role, source quality, and officiality.
- Evidence is stored in an entity-centric evidence store, not kept URL-centric all the way through.
- The Extractor performs pre-extraction top-10 gating to reduce latency and cost.
- The Finalizer is intentionally thin and only shapes the user-facing rows.

## Detailed Documentation

The detailed system design and active contract boundaries are in:

- [backend/docs/design_flow.md](/Users/a123/PycharmProjects/agentic_search/backend/docs/design_flow.md)
- [backend/docs/stage_contracts.md](/Users/a123/PycharmProjects/agentic_search/backend/docs/stage_contracts.md)
- [backend/docs/agent_context.md](/Users/a123/PycharmProjects/agentic_search/backend/docs/agent_context.md)

## Setup

Requirements:

- Python 3.11+
- Brave Search API key
- OpenAI API key

Install dependencies:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Create an environment file:

```bash
cp .env.example .env
```

Fill in at least:

```env
OPENAI_API_KEY=...
BRAVE_SEARCH_API_KEY=...
PLANNER_MODE=llm
PLANNER_MODEL=gpt-5-mini
SEARCHER_MODE=brave
```

Notes:

- The active pipeline also uses LLM-backed ExtractorLight, Assessor, and Extractor stages.
- If `OPENAI_API_KEY` is missing, the LLM-backed stages will not work.
- If `BRAVE_SEARCH_API_KEY` is missing, search and Brave LLM Context will not work.

## Run the Server

From the repo root:

```bash
uvicorn backend.app.main:app --host 127.0.0.1 --port 8000 --reload
```

Then open:

- [http://127.0.0.1:8000/demo](http://127.0.0.1:8000/demo)

## How to Use It

### Browser Demo

Open:

- [http://127.0.0.1:8000/demo](http://127.0.0.1:8000/demo)

This page:

- accepts a normal text query
- streams stage progress live over SSE
- renders the final results as an HTML table

### Raw JSON Endpoint

Open in the browser or call directly:

- `http://127.0.0.1:8000/api/v1/search?query=best phone models in 2026`

### SSE Progress Endpoint

For raw event streaming:

- `http://127.0.0.1:8000/api/v1/search/stream?query=best phone models in 2026`

### Health Check

- `http://127.0.0.1:8000/health`

## Running Tests

```bash
pytest backend/tests -q
```

## Known Limitations

- The active implementation is intentionally downscoped from the broader north-star design.
- There is no verification-query sub-pass in the active runtime flow.
- There is no Jina selection/fetch step in the active runtime flow.
- There is no repair round.
- There is no MMR/diversity selector in the active runtime flow.
- Some extraction quality issues can still remain when source text mixes nearby product variants.
- Brave LLM Context can fail for some queries; the system now falls back to Brave search snippets instead of failing the run.

## Deployment Note

For a simple deploy, the same FastAPI app serves:

- the JSON API
- the SSE endpoint
- the demo HTML page

That keeps local demos and lightweight hosting straightforward.
