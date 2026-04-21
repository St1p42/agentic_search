# Stage Contracts

This document records the active ownership and typed I/O boundaries for the current chunk-first pipeline. The north-star design remains future-oriented reference only.

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
- weighted source scoring
- source-bucket classification over Brave metadata
- diversified shortlist construction

Important active behavior:
- merge ordering is deterministic
- the active source score combines:
  - Brave rank
  - query-source coverage
- shortlisted results now carry source-bucket metadata in provider metadata
- bucket-local sorting, floors, caps, and backfill are part of active shortlist behavior
- if source-bucket classification is unavailable, the searcher can still fall back to deterministic shortlist behavior

Does not own:
- semantic query generation
- deep fetch
- chunk ranking
- extraction

---

## Retrieved Source Processing

Input:
- `SearcherOutput.shortlisted_results`

Output:
- `RetrievedSourcesOutput`

Owns:
- Jina fetch of shortlisted URLs in the default runtime path
- converting fetched pages into `UrlSource`
- hierarchical chunking into `RetrievedChunk`

Important active behavior:
- the retrieved-source layer is provider-neutral
- downstream stages consume `UrlSource` and chunk references, not Brave-specific passage models
- only shortlisted URLs are deep-fetched

Does not own:
- semantic source assessment
- candidate extraction
- field extraction

---

## Chunk Ranker

Input:
- `PlannerOutput`
- `RetrievedSourcesOutput`

Output:
- `ChunkRankingOutput`

Owns:
- request-local chunk scoring
- ordered ranked chunk references
- selected top-k chunk ids for downstream stages

Important active behavior:
- BM25 is the main relevance engine
- the ranker also uses:
  - base-query score
  - best-rewrite score
  - query-variant coverage
  - max query span
  - anchor coverage
- `ChunkRankingOutput` is the main retrieval handoff to downstream stages

Does not own:
- candidate extraction
- source semantics
- field extraction

---

## ExtractorLight

Input:
- `PlannerOutput`
- `ChunkRankingOutput`

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
- final ranking
- final response shaping

---

## Assessor

Input:
- `PlannerOutput`
- `SearcherOutput`
- `ExtractorLightOutput`
- `RetrievedSourcesOutput`
- optional `EvidenceStore`

Output:
- `AssessorOutput`

Owns:
- heuristic source signals
- source role
- source quality
- officiality
- rough aspect coverage
- evidence sufficiency

Important active behavior:
- this is source triage only
- it operates over retrieved sources rather than Brave-context passages
- it enriches source evidence; it does not own the main retrieval path anymore

Does not own:
- semantic query generation
- chunk ranking
- candidate extraction
- field extraction

---

## Evidence Store Builder

Input:
- `ChunkRankingOutput`
- `ExtractorLightOutput`
- `AssessorOutput`
- optional existing `EvidenceStore`

Output:
- `EvidenceStore`

Owns:
- entity-centric evidence-store construction
- evidence merging
- source/provenance carry-through on chunks
- evidence attachment from ranked selected chunks

Important active behavior:
- primary attribution uses `name_to_source_urls`
- conservative string matching is fallback only
- ambiguous chunks may stay attached to multiple entities
- evidence chunks now carry:
  - `query_sources`
  - `selected_chunk_rank`

Does not own:
- structured field extraction
- final entity ranking
- row selection

---

## Entity Reranker

Input:
- `PlannerOutput`
- `ExtractorLightOutput`
- `EvidenceStore`

Output:
- `EntityRankingResult`

Owns:
- entity reranking before extraction
- low-score filtering before extractor top-10
- support-score computation
- query-alignment computation
- MMR-style rewrite-diversity ordering

Important active behavior:
- support score uses:
  - unique source count
  - deduped unique chunk count
  - query-variant coverage count
  - best source quality score
  - average selected chunk rank score
  - anti-concentration score
- query alignment uses:
  - normalized-query BM25
  - max query span
  - anchor coverage
- entities carry:
  - `supporting_query_variants`
  - `dominant_query_variant`
- final selection penalizes entities that are too similar by rewrite provenance

Does not own:
- candidate extraction
- structured field extraction
- final row shaping

---

## Extractor

Input:
- `PlannerOutput`
- `ExtractorLightOutput`
- `EvidenceStore`
- optional `EntityRankingResult`

Output:
- `ExtractorOutput`

Owns:
- planner-schema field extraction
- field-level provenance
- conservative contradiction handling
- null-default behavior for unsupported values

Important active behavior:
- entity extraction is anchored to reranked candidate entities
- only top 10 entities are extracted
- extractor no longer owns the main candidate ranking logic

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
- the finalizer is intentionally thin
- it should not become a substitute for retrieval, candidate generation, or reranking logic

Does not own:
- retrieval
- source triage
- evidence-store construction
- evaluator-style scoring
