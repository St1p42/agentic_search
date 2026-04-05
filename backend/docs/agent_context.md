# Agent Context

This is the active implementation context for the current downscoped pipeline.

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
- Brave LLM Context runs only on a bounded shortlist.
- ExtractorLight exists to establish candidate entities before full extraction.
- Assessor owns source-level semantic triage.
- Evidence Store Builder owns entity-centric evidence construction and per-entity evidence scoring.
- Extractor consumes the evidence store and owns structured field extraction.
- Finalizer is a thin response shaper in the active flow.
- Prefer null over unsupported values.
- Keep all stage I/O typed and explicit.

---

## Active Pipeline Order

1. Planner
2. Searcher
3. Brave LLM Context Helper
4. ExtractorLight
5. Assessor
6. Evidence Store Builder
7. Extractor
8. Finalizer

---

## Active Downscope

The current implementation is intentionally narrower than the north-star design.

Out of scope in active behavior:

- verification-query sub-pass
- Jina selection/fetch orchestration
- repair diagnostics
- repair round execution
- MMR/diversity final selection
- evaluator-style final ranking

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
- shortlist construction

Important implementation stance:

- use soft rewrite-slot reservation so rewrites contribute
- use a small per-domain cap
- keep merge/tie-break logic deterministic

Does not own:

- semantic rewrite generation
- source semantics
- extraction

### Brave LLM Context Helper

Owns:

- shortlist-only Brave context calls
- exact-URL-only passage attachment
- snippet fallback when exact-URL context is missing
- deterministic passage cleanup

Does not own:

- deep fetch
- entity extraction
- source assessment

### ExtractorLight

Owns:

- candidate name extraction only
- `name_to_source_urls`
- mention counts

Why it matters:

- it creates the candidate entity prior for the rest of the pipeline
- it prevents direct uncontrolled field extraction from raw URL text

Does not own:

- field extraction
- ranking
- final row decisions

### Assessor

Owns:

- heuristic source signals
- batched source assessment
- `source_role`
- `source_quality`
- `officiality`
- rough aspect coverage
- evidence sufficiency

Does not own in active flow:

- verification-gap generation
- verification queries
- Jina selection
- repair decisions

### Evidence Store Builder

Owns:

- entity-centric evidence-store construction and merging
- evidence attribution using `name_to_source_urls` first
- conservative string-match fallback
- chunk provenance carry-through
- per-entity evidence score computation

Important attribution policy:

- do not drop ambiguous chunks too early
- use distinct source URLs for score calculation
- do not confuse chunk count with source breadth

Current score policy:

- high-quality source URL => `+1.0`
- medium-quality source URL => `+0.5`
- low-quality source URL => `+0.0`

### Extractor

Owns:

- structured extraction over entity evidence slices
- planner-schema field filling
- field-level evidence
- conservative null-default behavior
- pre-extraction top-10 gating

Active ranking before extraction:

1. higher entity score
2. more distinct supporting source URLs
3. more total supporting chunk text length
4. alphabetical entity name

Why this is important:

- extractor cost is dominated by per-entity LLM calls
- top-10 filtering is a latency and quality control mechanism

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
- no diagnostics
- no extra ranking logic

Does not own:

- retrieval
- source triage
- evidence-store construction
- evaluator-style scoring

---

## Practical Implementation Priorities

1. keep contracts stable
2. keep provenance traceable
3. keep stage ownership strict
4. keep deterministic policies explicit
5. use LLMs only where they provide real semantic value

---

## Anti-Goals

- no hidden coupling between stages
- no private payload shapes
- no speculative field extraction without evidence
- no uncontrolled query expansion
- no accidental reintroduction of verification/repair logic
- no user-facing leakage of internal pipeline diagnostics
