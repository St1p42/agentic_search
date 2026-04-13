# Agentic Search

Agentic Search is a bounded multi-stage pipeline that takes a topic query, searches the web, gathers lightweight evidence, extracts structured entities with field-level provenance, and returns a table with top-k found entities.

The deployed project is publicly accessible here:

- https://agentic-entity-search.vercel.app/

You do not need to set anything up locally to try the product. The local setup instructions below are only for running or modifying the codebase yourself.

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
- ExtractorLight exists to establish candidate entities before any full field extraction, then removes obvious non-entity strings with a small deterministic cleanup layer.
- Assessor is heuristic-only by default and adds source semantics such as source role, source quality, and officiality.
- Evidence is stored in an entity-centric evidence store, not kept URL-centric all the way through.
- The Extractor performs pre-extraction top-10 gating to reduce latency and cost.
- The Finalizer is intentionally thin and prunes obvious row failures before returning the user-facing rows.

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

- The active pipeline uses LLM-backed Planner, ExtractorLight, and Extractor stages by default. The Assessor defaults to a heuristic-only mode, but still supports an optional LLM-backed mode for comparison.
- If `OPENAI_API_KEY` is missing, the LLM-backed stages will not work.
- If `BRAVE_SEARCH_API_KEY` is missing, search and Brave LLM Context will not work.

## Run the Server

### Backend

From the repo root:

```bash
uvicorn backend.app.main:app --host 127.0.0.1 --port 8000 --reload
```

Then open:

- [http://127.0.0.1:8000/demo](http://127.0.0.1:8000/demo)

This is the simpler backend-served demo page. The primary local frontend experience is the Next.js app described below.

### Frontend

The Next.js frontend lives under `frontend/` and expects the backend server to be running first.

By default, the frontend proxies API requests to:

- `http://127.0.0.1:8000`

So for normal local development:

1. start the backend server
2. start the frontend dev server

From the `frontend/` directory:

```bash
npm install
npm run dev
```

Then open:

- [http://127.0.0.1:3000](http://127.0.0.1:3000)

If you want the frontend to point at a different backend, set either:

```env
BACKEND_URL=http://127.0.0.1:8000
```

or:

```env
NEXT_PUBLIC_BACKEND_URL=http://127.0.0.1:8000
```

## How to Use It

### Browser Demo

Open:

- [http://127.0.0.1:3000](http://127.0.0.1:3000)

This page:

- accepts a normal text query
- streams stage progress live over SSE
- renders the final results as the primary demo UI

Optional simpler backend-served demo:

- [http://127.0.0.1:8000/demo](http://127.0.0.1:8000/demo)

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

## Project Status

The project is currently at the end of its Phase 1 demo-ready milestone:

- the active pipeline is stable enough to demo publicly
- the frontend is usable as a recruiter-facing product surface
- the remaining work is focused on improving quality, coverage, latency, and retrieval depth rather than shipping a first usable version

The broader roadmap is documented here:

- [backend/docs/improvement_plan.md](/Users/a123/PycharmProjects/agentic_search/backend/docs/improvement_plan.md)

That document covers the next planned phases, including deeper retrieval, stronger verification, richer evidence selection, and overall performance improvements.

## Deployment Note

For a simple deploy, the same FastAPI app serves:

- the JSON API
- the SSE endpoint
- the demo HTML page

That keeps local demos and lightweight hosting straightforward.
