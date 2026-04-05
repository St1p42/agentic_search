# Stage Contracts

This document records the active ownership and typed I/O boundaries for the current downscoped pipeline. The north-star design remains future-oriented reference only.

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

## Planner

Input:
- `PipelineRequest.query`

Output:
- `PlannerOutput`

Owns:
- conservative query normalization
- `entity_type`
- `query_mode`
- `schema_columns`
- `core_aspects`
- `base_query`
- `initial_query_rewrites`
- topic-query acceptance vs rejection

Important active behavior:
- query rewrites are planner-owned and reflect likely user-intent slices
- typical shape is 4 to 6 schema columns and 0 to 3 rewrites
- Planner runs once
- if the input is slightly off but clearly convertible to a topic query, Planner normalizes it conservatively
- if the input is non-topic or requires strong reinterpretation, Planner returns `error=true`

Does not own:
- retrieval execution
- source assessment
- evidence construction
- extraction

---

## Searcher

Input:
- `PlannerOutput`

Output:
- `SearcherOutput`

Owns:
- executing planner-provided queries
- collecting Brave result metadata
- mechanical URL pruning
- exact URL deduplication
- multi-query merge
- bounded shortlist construction

Important active behavior:
- merge ordering is deterministic
- best rank wins first
- multi-query support acts as a tie-break
- soft rewrite-slot reservation prevents collapse into only base-query results
- a small per-domain cap improves shortlist variety

Does not own:
- semantic query generation
- source semantics
- deep-fetch decisions
- extraction

---

## Brave LLM Context Helper

Input:
- `SearcherOutput.shortlisted_results`

Output:
- `BraveContextOutput`

Owns:
- shortlist-only Brave LLM Context retrieval
- exact-URL passage filtering
- snippet fallback when no exact-URL passage survives
- deterministic passage cleanup

Important active behavior:
- provides shallow URL-linked evidence only
- does not do full-page retrieval

Does not own:
- source assessment
- candidate extraction
- field extraction

---

## ExtractorLight

Input:
- `PlannerOutput`
- `BraveContextOutput`

Output:
- `ExtractorLightOutput`

Owns:
- candidate-name extraction only
- `name_to_source_urls`
- `mention_counts`

Why it exists:
- separates entity discovery from field extraction
- gives the pipeline a stable candidate list and URL attachment prior

Does not own:
- field extraction
- row ranking
- eligibility filtering
- final response shaping

---

## Assessor

Input:
- `PlannerOutput`
- `SearcherOutput`
- `BraveContextOutput`
- `ExtractorLightOutput`
- optional `EvidenceStore`

Output:
- `AssessorOutput`

Owns:
- heuristic source signals
- one batched semantic source assessment
- classification of:
  - `source_role`
  - `source_quality`
  - `officiality`
  - `estimated_aspect_coverage`
  - `evidence_sufficiency`

Important active behavior:
- this is source triage only
- source semantics are decided here, not in the Searcher or Extractor

Does not own in the active flow:
- verification-gap planning
- verification-query generation
- Jina selection
- repair decisions

---

## Evidence Store Builder

Input:
- `BraveContextOutput`
- `ExtractorLightOutput`
- `AssessorOutput`
- optional existing `EvidenceStore`

Output:
- `EvidenceStore`

Owns:
- entity-centric evidence-store construction
- evidence merging
- source/provenance carry-through on chunks
- per-entity scoring for extraction-time filtering

Important active behavior:
- primary attribution uses `name_to_source_urls`
- conservative string matching is fallback only
- ambiguous chunks may stay attached to multiple entities
- chunk construction uses anchored sentence windows

Entity score policy:
- distinct high-quality source URL => `+1.0`
- distinct medium-quality source URL => `+0.5`
- low-quality source URL => `+0.0`
- score is based on distinct source URLs, not chunk count

Does not own:
- structured field extraction
- row selection

---

## Extractor

Input:
- `PlannerOutput`
- `ExtractorLightOutput`
- `EvidenceStore`

Output:
- `ExtractorOutput`

Owns:
- planner-schema field extraction
- field-level provenance
- conservative contradiction handling
- null-default behavior for unsupported values

Important active behavior:
- entity extraction is anchored to `ExtractorLightOutput.candidate_names`
- pre-extraction gating happens here
- only top 10 entities are extracted

Active extraction ordering:
1. higher `entity_score`
2. more distinct supporting source URLs
3. more total supporting chunk text length
4. alphabetical entity name

Why this matters:
- extractor latency is driven by per-entity LLM calls
- filtering before extraction is the main practical latency lever

Does not own:
- retrieval
- source assessment
- evidence construction
- final response shaping

---

## Finalizer

Input:
- `PlannerOutput`
- `ExtractorOutput`

Output:
- `CanonicalizerVerifierEvaluatorOutput`

Active output shape:
- `final_rows`

Owns:
- final user-facing row shaping
- mapping extracted entities into:
  - `name`
  - `fields`
  - `source_urls`

Important active behavior:
- the Finalizer is intentionally thin
- it does not emit diagnostics
- it does not do repair suggestions
- it does not do extra ranking beyond what Extractor already decided

Does not own:
- retrieval
- source triage
- evidence construction
- additional ranking logic

---

## Orchestrator

Input:
- `PipelineRequest`

Output:
- `PipelineResponse`

Owns:
- the fixed stage order
- request-scoped state and budgets
- evidence-store construction and merging
- final response assembly
- SSE lifecycle event emission when using the streaming shell

Important active behavior:
- the active flow is single-pass
- there is no repair gating in current behavior
- there is no diagnostics-dependent second retrieval pass

Does not own:
- stage-local semantic decisions that already belong to Planner, Assessor, or Extractor

---

## Explicitly Out of Scope in Current Contracts

- repair diagnostics
- repair follow-up queries
- verification-query sub-pass ownership
- Jina selection/fetch ownership in the active flow
- MMR/diversity selection in Finalizer
- evaluator-style final ranking

Those belong to the north-star design, not the current active contract set.
