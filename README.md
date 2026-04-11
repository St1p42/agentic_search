# Agentic Search

Agentic Search is a bounded multi-stage pipeline that takes a topic query, searches the web, gathers lightweight evidence, extracts structured entities with field-level provenance, and returns a top-10 table. 

- UPD: accessible at

  https://agentic-search-jvk1.onrender.com/demo](https://agentic-entity-search.vercel.app/

  (might take around a minute or so to wake up the server as I am using a free-tier deployment plan).

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

- The active implementation is intentionally downscoped from the broader north-star design in order to ship a working v1 within the challenge timeline.

- The current pipeline is **not yet latency-optimized**.  
  A faster version would likely come from being more selective much earlier: pruning weak sources sooner, issuing fewer but better query expansions, merging search results more carefully, and passing smaller, more targeted evidence chunks into downstream stages. Additional gains are likely from making source assessment leaner and adding an optional **per-entity evidence summarization step** so later stages consume compressed evidence rather than raw accumulated context.

- The **frontend is intentionally minimal** in v1.  
  It is currently a simple HTML page served by the backend and is functional rather than polished. A fuller version would improve usability, progress visibility, evidence inspection, and general presentation quality.

- There is no **verification-query sub-pass** in the active runtime flow.  
  In the fuller design, this step would issue targeted follow-up searches for promising entities that are missing strong verification sources. The goal is to improve the likelihood that important schema columns can be filled with grounded evidence rather than left empty or weakly supported.

- There is no **repair round** in the active runtime flow.  
  In the fuller design, the system would inspect the provisional final table for weak rows, under-covered aspects, or missing important fields, then run one bounded follow-up retrieval/extraction pass to improve coverage before returning results.

- There is no **Jina-based selective deep-fetch step** in the active runtime flow.  
  In the fuller design, this would provide more direct page content beyond Brave LLM Context, giving the system better evidence for extraction and verification. It would also enable lightweight in-memory chunking and more focused downstream context selection, rather than relying only on the pre-extracted context returned by Brave.

- There is no **MMR/diversity selector** in the active runtime flow.  
  In the fuller design, the system would first keep a somewhat larger candidate pool, then apply an MMR-style selection step to choose a more diverse final top-10 (across planner-derived aspects).

- Some **extraction quality issues** can still remain when retrieved text mixes closely related entities, product variants, or overlapping mentions on the same page.  
  This can lead to partial field leakage or less precise row construction. Additional retrieval refinement and stronger evidence separation would likely improve this.

- The current retrieval/extraction pipeline can still be improved overall.  
  Better early source selection, stronger evidence filtering, and richer source coverage would likely improve both entity discovery quality and schema completeness.

## Deployment Note

For a simple deploy, the same FastAPI app serves:

- the JSON API
- the SSE endpoint
- the demo HTML page

That keeps local demos and lightweight hosting straightforward.
