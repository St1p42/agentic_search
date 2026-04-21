# Agentic Search — Active System Flow

## Goal

Build a system that takes a topic query such as "AI startups in healthcare", "top pizza places in Brooklyn", or "open source database tools" and produces a structured table of discovered entities with relevant attributes, sourced from the web.

### Minimum Requirements

- Accept a topic query
- Search the web for relevant results
- Process search-result-linked page content
- Use LLMs where semantic extraction or judgment is useful
- Return a structured table or JSON response
- Keep each value traceable to supporting source evidence

### Evaluation Priorities

- output quality
- design quality and tradeoffs
- code structure
- documentation clarity
- implementation depth without unnecessary complexity

---

## 0. Core Architectural Stance

- The system uses a deterministic orchestrator in code, not an LLM orchestrator.
- The active pipeline is fixed and bounded.
- Provenance is part of the core data model, not optional metadata.
- LLMs are used only where semantic judgment materially helps.
- The active implementation is intentionally narrower than the north-star design.
- The active source of truth is the chunk-first Jina pipeline, not the older Brave-context flow.

Downscoped out of the active flow:

- no verification-query sub-pass
- no repair round
- no open-ended retrieval expansion loop
- no evaluator-style diagnostics in the final user response
- no production-scale retrieval scheduler

Implemented in the active flow:

- Jina-first retrieval by default
- provider-neutral `UrlSource` / chunk contracts
- source-bucket classification before deep fetch
- chunk ranking over fetched page text
- entity reranking before extractor construction
- passive eval-data collection for Jina chunks

---

## 1. Runtime Components

### 1.1 Deterministic Orchestrator

Owns:

- stage order
- request-scoped state
- request-scoped budgets
- evidence store construction and merging
- final response assembly

### 1.2 Active Stage Order

1. Planner
2. Searcher
3. Source classification / diversified shortlist
4. Retrieved source processing via Jina
5. Chunk ranking
6. ExtractorLight
7. Assessor
8. Evidence Store Builder
9. Entity reranking
10. Extractor
11. Finalizer

This order is sequential and fixed.

---

## 2. Request Initialization

At the start of a request, the orchestrator initializes:

- request ID
- original query
- normalized query placeholder
- empty evidence store
- empty extractor output placeholder
- request budgets

The active budgets are conservative and bounded. The important practical caps are:

- up to 4 initial search queries
- a bounded shortlist of Brave search results
- a bounded deep-fetch set for Jina
- a bounded selected chunk set for extraction
- top 10 final entities returned

---

## 3. Planner

**Purpose:** turn the user query into a bounded retrieval and extraction plan.

### Inputs

- raw user query

### Outputs

- `entity_type`
- `query_mode`
- `schema_columns`
- `core_aspects`
- `base_query`
- `initial_query_rewrites`
- `is_topic_query`
- `normalized_query`
- `normalization_note`
- `error`

### What the Planner owns

- deciding whether the query is already a topic-entity discovery query
- conservative query normalization when the user phrasing is slightly off but still clearly convertible to a topic query
- deciding the entity type
- deciding the user-facing schema columns
- deciding the main query aspects behind the user intent
- generating the base query and bounded rewrites

### Normalization and rejection policy

- if the input is already a topic query, keep it as-is
- if the input is slightly off but the intended topic query is obvious, normalize it conservatively and continue
- if the input is a non-topic query or would require strong reinterpretation, return `error = true` and stop the pipeline

### Query rewrites and user intent

The first semantic decision in the system is not retrieval. It is query framing.

The Planner infers likely intent slices and uses them in two ways:

- to define `core_aspects` for downstream extraction context
- to generate a small number of query rewrites that cover likely user intent slices

These rewrites are planner-owned because they are semantic, not mechanical.

### Constraints

- schema is usually 4 to 6 columns
- rewrites are usually 0 to 3
- Planner runs once
- if the query is non-topic or requires strong reinterpretation, the Planner should reject it instead of guessing

---

## 4. Searcher

**Purpose:** build a strong but bounded candidate URL pool from Brave Web Search.

### Inputs

- `normalized_query`
- `base_query`
- `initial_query_rewrites`

### What the Searcher owns

- executing planner-supplied queries
- collecting ranked results, titles, snippets, domains, and metadata
- mechanical pruning
- exact-URL deduplication
- weighted merge and shortlist scoring
- source-bucket classification over Brave metadata
- diversified shortlist construction

### Important design choices

The Searcher is deliberately not semantic in the sense of inventing new queries. It only executes the Planner’s base query plus rewrites.

The active shortlist path is:

1. run base query plus rewrites
2. prune weak results mechanically
3. merge duplicate URLs across queries
4. compute a weighted source score using:
   - Brave rank
   - query-coverage across executed queries
5. classify merged results into coarse source buckets
6. select a diversified shortlist using:
   - bucket-local sorting
   - bucket quality floors
   - per-bucket caps
   - round-robin bucket selection
   - global backfill if needed

### Mechanical pruning

Before any LLM call, the Searcher removes obviously weak or irrelevant URLs, including:

- duplicate URLs
- clearly low-value social/video URLs
- file-extension URLs such as PDF-like documents in the URL
- empty-snippet results
- clearly navigational/boilerplate results
- results with no lexical overlap with either the query or planner aspects

### Source-bucket classification

The current active buckets are:

- `official_entity`
- `profile_directory`
- `roundup_list`
- `editorial_reference`
- `transactional_listing`

The classifier uses:

- URL
- title
- snippet
- query provenance
- rank

It runs before deep fetch so Jina is used only on the diversified shortlist, not the full raw result pool.

---

## 5. Retrieved Source Processing

**Purpose:** fetch page text for shortlisted URLs and convert it into provider-neutral retrieved sources.

### Inputs

- `SearcherOutput.shortlisted_results`
- request-scoped retrieval mode

### Active behavior

The default runtime mode is Jina.

Jina fetches the shortlisted URLs, converts them into `UrlSource` objects, and chunks them with the hierarchical chunker.

The retrieval layer is now provider-neutral:

- `UrlSource`
- `RetrievedChunk`
- `RetrievedSourcesOutput`

This means downstream stages no longer depend on Brave-specific passage structures.

### Why this stage exists

This stage is the transition from:

- search-result metadata

to:

- source-linked chunked page text with provenance

It is the first stage that works over real retrieved page content rather than snippets.

---

## 6. Chunk Ranking

**Purpose:** select the most relevant passages from fetched sources before candidate discovery.

### Inputs

- `PlannerOutput`
- `RetrievedSourcesOutput`

### Outputs

- `ChunkRankingOutput`

### Active ranking signals

The active chunk ranker uses BM25 plus bounded lexical bonuses:

- base query score
- best rewrite score
- query-variant coverage
- max query span score
- anchor coverage score

Current weight split:

- base query: `0.45`
- best rewrite: `0.25`
- query-variant coverage: `0.10`
- max query span: `0.10`
- anchor coverage: `0.10`

### Why this stage exists

Full fetched pages are too broad to feed directly into `ExtractorLight`.

This stage narrows the evidence pool to the most relevant source passages while preserving:

- source provenance
- chunk identity
- request-local ranking diagnostics

---

## 7. ExtractorLight

**Purpose:** get candidate entity names before doing any full field extraction.

### Inputs

- `PlannerOutput`
- `ChunkRankingOutput`

### Outputs

- `candidate_names`
- `name_to_source_urls`
- `mention_counts`

### Why this stage exists

This stage is the entity-anchor for the rest of the pipeline.

It is needed because the system should not jump directly from ranked chunks to fully structured rows. The intermediate name-extraction step gives:

- a bounded candidate list
- name-to-URL mention mapping
- mention counts for rough prominence
- a cleaner boundary between “who are the entities?” and “what fields do they have?”

### What it does not do

- no field extraction
- no final row shaping
- no final eligibility decisions

---

## 8. Assessor

**Purpose:** attach source-level quality and role signals before evidence assembly.

### Inputs

- `PlannerOutput`
- `SearcherOutput`
- `ExtractorLightOutput`
- `RetrievedSourcesOutput`
- optional `EvidenceStore`

### Outputs

- `AssessorOutput`

### What it owns

- heuristic source signals
- source role
- source quality
- officiality
- rough aspect coverage
- evidence sufficiency

### Active stance

This is still a source-triage stage, but it now operates over the retrieved-source path instead of Brave-context passages.

It is no longer the main retrieval decision-maker. It enriches the source evidence that was already selected by:

- searcher shortlist logic
- chunk ranking

---

## 9. Evidence Store Builder

**Purpose:** construct an entity-centric evidence store from assessed sources and ranked selected chunks.

### Inputs

- `ChunkRankingOutput`
- `ExtractorLightOutput`
- `AssessorOutput`
- optional existing `EvidenceStore`

### Outputs

- `EvidenceStore`

### What it owns

- entity-centric evidence-store construction
- evidence merging
- source/provenance carry-through on chunks
- attachment of:
  - `query_sources`
  - `selected_chunk_rank`
- coarse per-entity evidence summary signals

### Important active behavior

- primary attribution uses `name_to_source_urls`
- conservative string matching is fallback only
- ambiguous chunks may stay attached to multiple entities
- the selected chunk set is now the primary evidence input

---

## 10. Entity Reranking

**Purpose:** rerank and filter evidence-backed candidates before paying extraction cost.

### Inputs

- `PlannerOutput`
- `ExtractorLightOutput`
- `EvidenceStore`

### Outputs

- `EntityRankingResult`

### Active scoring

The active reranker computes:

1. support score from:
   - unique source count
   - deduped unique chunk count
   - query-variant coverage count
   - best source quality score
   - average selected chunk rank score
   - anti-concentration score
2. query alignment score from:
   - normalized-query BM25
   - max query span
   - anchor coverage
3. final entity score as a blend of support and query alignment

### Active selection

After scoring, the reranker applies an MMR-style diversity-aware ordering based on query-rewrite provenance:

- each entity carries:
  - `supporting_query_variants`
  - `dominant_query_variant`
- entities that come from the same dominant rewrite are penalized during final selection

This is intended to reduce cases where one rewrite dominates the final candidate set.

---

## 11. Extractor

**Purpose:** build structured entities from reranked evidence-backed candidates.

### Inputs

- `PlannerOutput`
- `ExtractorLightOutput`
- `EvidenceStore`
- optional precomputed `EntityRankingResult`

### Outputs

- `ExtractorOutput`

### What it owns

- planner-schema field extraction
- field-level provenance
- conservative contradiction handling
- null-default behavior for unsupported values

### Active behavior

- extraction is anchored to reranked candidate entities
- only the top 10 surviving candidates are extracted
- extractor no longer owns the main entity ranking logic

This matters because extractor latency is driven by per-entity LLM calls, so pre-extraction reranking is now the main practical latency lever.

---

## 12. Finalizer

**Purpose:** produce the final user-facing result rows.

### Inputs

- `PlannerOutput`
- `ExtractorOutput`

### Outputs

- `CanonicalizerVerifierEvaluatorOutput`

### Active output shape

- `final_rows`

### What it owns

- final user-facing row shaping
- mapping extracted entities into:
  - `name`
  - `fields`
  - `source_urls`

### Important active behavior

- the finalizer is still intentionally thin
- heavy ranking logic should not migrate into the finalizer
- it is not the place to solve retrieval or candidate-quality problems

---

## 13. SSE Observability

The frontend receives stage-oriented SSE updates for the active runtime path.

Recent user-visible steps now include:

- `Started search`
- `Planning`
- `Retrieving sources`
- `Classifying sources`
- `Processing sources`
- `Selecting source passages`
- `Identifying candidates`
- `Assessing source quality`
- `Retrieving evidence`
- `Ranking candidates`
- `Building entities`
- `Finalizing table`

Important newer metrics include:

- source-bucket breakdown on shortlisted sources
- passage scoring/selection counts
- candidate reranking counts:
  - core candidates kept
  - discovery candidates kept
  - core candidates filtered
  - discovery candidates filtered

---

## 14. Passive Evaluation and Logging

The active pipeline also passively accumulates debugging and eval artifacts.

### Jina chunk eval dataset

The system writes deduped `(query, source, chunk)` rows for later LLM judging and offline retrieval evaluation.

This dataset is intended for:

- chunk relevance labeling
- precision / recall / nDCG experiments
- future retrieval-model comparisons

### Source-bucket dataset

The searcher also logs source-bucket decisions over Brave metadata for potential future classifier training.

### Final debug summary

The final logger emits a compact per-request debug summary including:

- query bundle
- selected sources
- top candidates
- ranked entity debug output
- final entities

This summary is intended for backend debugging, not user-facing diagnostics.
