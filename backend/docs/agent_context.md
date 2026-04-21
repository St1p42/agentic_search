# Agent Context

This is the active implementation context for the current chunk-first pipeline.

The north-star design remains broader future reference. It is useful for direction, but it is not the source of truth for current behavior.

---

## Global Context for All Agents

You are implementing part of a bounded deterministic multi-stage system. Follow the active docs and shared contracts. Do not silently implement north-star features unless the scope is explicitly being expanded.

---

## Non-Negotiable Global Rules

- The system uses a deterministic orchestrator in code, not an LLM orchestrator.
- There is no open-ended loop, recursive orchestration, or free-form agentic control flow.
- Provenance is part of the field model, not optional metadata.
- Planner owns semantic query generation, including bounded rewrites.
- Searcher executes queries and builds result pools; it does not invent semantic rewrites.
- Searcher now also owns source-bucket classification over Brave metadata and diversified shortlist selection.
- Jina-backed retrieved sources are the default deep-retrieval path.
- Downstream retrieval contracts are provider-neutral:
  - `UrlSource`
  - `RetrievedChunk`
  - `RetrievedSourcesOutput`
- Chunk ranking is a first-class stage before `ExtractorLight`.
- ExtractorLight exists to establish candidate entities before full extraction.
- Assessor owns source-level semantic triage.
- Evidence Store Builder owns entity-centric evidence construction from ranked selected chunks.
- Entity reranking happens before extractor construction.
- Extractor consumes evidence-backed candidates and owns structured field extraction.
- Finalizer is a thin response shaper in the active flow.
- Prefer null over unsupported values.
- Keep all stage I/O typed and explicit.

---

## Active Pipeline Order

1. Planner
2. Searcher
3. Source classification / diversified shortlist
4. Retrieved source processing
5. Chunk ranking
6. ExtractorLight
7. Assessor
8. Evidence Store Builder
9. Entity reranker
10. Extractor
11. Finalizer

---

## Active Downscope

The current implementation is intentionally narrower than the north-star design.

Out of scope in active behavior:

- verification-query sub-pass
- repair diagnostics
- repair round execution
- open-ended retrieval expansion loops
- evaluator-style final ranking in the user response
- production-scale retrieval scheduling

If you touch active code, do not partially reintroduce these features by accident.

---

## Shared Engineering Expectations

- Build against the shared contract package only.
- Preserve stage boundaries.
- Keep deterministic parts deterministic.
- Keep prompts structured and bounded.
- Prefer explicit small decisions over implicit cleverness.
- Add or update tests when changing behavior.

---

## Shared Contract Assumptions

Agents should assume the shared contract package contains:

- request/response models
- stage input/output models
- evidence/provenance models
- evidence store model
- SSE event models
- error models

If a needed field is missing, add it through the shared contract package rather than inventing a private payload.

---

## Active Stage Ownership

### Planner

Owns:

- conservative topic-query normalization
- entity type inference
- schema generation
- core aspect generation
- base query generation
- initial query rewrites based on likely user intent slices

Important implementation stance:

- rewrites are semantic coverage, not query spam
- if the input is slightly off but clearly convertible, normalize conservatively
- if the input is non-topic or would require strong reinterpretation, return planner error
- planner should reject aggressively ambiguous inputs rather than over-guess

Does not own:

- retrieval execution
- source assessment
- evidence construction
- extraction

### Searcher

Owns:

- Brave Web Search execution
- result collection with metadata
- mechanical URL pruning
- exact URL deduplication
- multi-query merge
- weighted source scoring
- source-bucket classification over Brave metadata
- diversified shortlist construction

Important implementation stance:

- the active source score combines:
  - Brave rank
  - query-source coverage
- shortlist selection is deterministic
- shortlist diversity is now enforced partly through source buckets, not only domains and query coverage
- the searcher should still be bounded and cheap relative to downstream stages

Does not own:

- semantic rewrite generation
- deep fetch
- chunk ranking
- extraction

### Retrieved Source Processing

Owns:

- deep fetch of shortlisted URLs through the active retrieval provider
- conversion into provider-neutral `UrlSource` objects
- chunking into `RetrievedChunk`

Important implementation stance:

- Jina is the default runtime mode
- deep fetch is only for shortlisted results
- downstream stages should not depend on provider-specific passage artifacts

Does not own:

- candidate extraction
- source assessment
- field extraction

### Chunk Ranker

Owns:

- request-local chunk scoring
- ranking of fetched source passages
- selection of top-k chunk ids for downstream stages

Important implementation stance:

- BM25 is the main relevance engine
- lexical bonuses are allowed where they are transparent and request-local
- chunk ranking is the main bridge between fetched page text and candidate extraction

Does not own:

- candidate naming
- source semantics
- field extraction

### ExtractorLight

Owns:

- candidate name extraction only
- `name_to_source_urls`
- mention counts

Why it matters:

- it creates the candidate entity prior for the rest of the pipeline
- it prevents direct uncontrolled field extraction from raw retrieved text

Does not own:

- field extraction
- final ranking
- final row decisions

### Assessor

Owns:

- heuristic source signals
- source role
- source quality
- officiality
- rough aspect coverage
- evidence sufficiency

Important implementation stance:

- this is still source triage only
- it operates over retrieved sources rather than Brave-context passages
- it is no longer the primary retrieval gate

Does not own:

- semantic query generation
- chunk ranking
- candidate extraction
- repair decisions

### Evidence Store Builder

Owns:

- entity-centric evidence-store construction and merging
- evidence attribution using `name_to_source_urls` first
- conservative string-match fallback
- chunk provenance carry-through
- attachment of:
  - `query_sources`
  - `selected_chunk_rank`

Important attribution policy:

- do not drop ambiguous chunks too early
- do not confuse chunk count with source breadth
- the selected chunk set is the primary evidence source

### Entity Reranker

Owns:

- candidate reranking before extractor construction
- low-score filtering
- support-score computation
- query-alignment computation
- rewrite-diversity-aware final candidate ordering

Important implementation stance:

- entity reranking is now the main pre-extraction gating layer
- entities carry query-provenance information from evidence chunks
- MMR-style rewrite diversification is allowed here because this is the first point where provenance-aware entity selection is well-defined

Does not own:

- candidate extraction
- structured field extraction
- final row shaping

### Extractor

Owns:

- structured extraction over entity evidence slices
- planner-schema field filling
- field-level evidence
- conservative null-default behavior
- top-10 extraction over reranked candidates

Why this is important:

- extractor cost is dominated by per-entity LLM calls
- pre-extraction reranking is the main latency and quality control mechanism

Does not own:

- retrieval
- source triage
- evidence-store construction

### Finalizer

Owns:

- user-facing row shaping only

Current behavior:

- returns only `final_rows`
- each row has `name`, `fields`, and `source_urls`
- no user-facing diagnostics
- no heavy ranking logic

Does not own:

- retrieval
- source triage
- evidence-store construction
- evaluator-style scoring

---

## Current Observability Context

Agents should assume the active runtime already exposes SSE visibility for:

- source retrieval
- source classification
- source processing
- selected passage scoring
- candidate identification
- source assessment
- evidence retrieval
- candidate reranking
- entity building
- finalization

There is also backend-only passive logging for:

- Jina chunk eval accumulation
- source-bucket training data accumulation
- final per-request debug summaries including ranked entity diagnostics
