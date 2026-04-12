# Agentic Search — Active System Flow

## Challenge

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
- The active implementation is intentionally downscoped from the north-star design.
- The north-star design remains future reference, but it is not the source of truth for current behavior.

Downscoped out of the active flow:

- no verification-query sub-pass
- no Jina fetch decision pass in the active orchestrated flow
- no repair round
- no MMR/diversity final selector
- no evaluator-style diagnostics in the final user response

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
3. Brave LLM Context helper
4. ExtractorLight
5. Assessor
6. Evidence Store Builder
7. Extractor
8. Finalizer

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
- a bounded shortlist for Brave LLM Context
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

The Planner infers the likely aspects behind the request and uses them in two ways:

- to define `core_aspects` for downstream extraction context
- to generate a small number of query rewrites that cover likely user intent slices

Example intent slices:

- quality or “best overall”
- price sensitivity
- camera or photography emphasis
- portability, foldable form factor, or premium flagship focus

These rewrites are not searcher-generated. They are planner-owned because they are semantic, not mechanical.

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
- bounded shortlist construction

### Important design choices

The Searcher is deliberately not semantic. It does not invent new queries. It only executes the Planner’s base query plus rewrites.

To avoid over-bias toward the base query, the Searcher uses a bounded merge strategy:

- exact duplicate URLs are removed
- multi-query results are merged deterministically
- the best rank wins first
- multi-query support helps as a tie-break
- soft reserved slots let rewrite results contribute to the shortlist
- a small per-domain cap prevents shortlist collapse into one site

### Mechanical pruning

Before any LLM call, the Searcher removes obviously weak or irrelevant URLs, including:

- duplicate URLs
- clearly low-value social/video URLs
- file-extension URLs such as PDF-like documents in the URL
- empty-snippet results
- clearly navigational/boilerplate results
- results with no lexical overlap with either the query or planner aspects

This keeps the expensive semantic stages working over a better pool.

---

## 5. Brave LLM Context Helper

**Purpose:** enrich shortlisted URLs with shallow URL-linked text before extraction.

### Inputs

- `SearcherOutput.shortlisted_results`

### What it owns

- running Brave LLM Context only on the bounded shortlist
- keeping only passages that match the exact shortlisted URL
- falling back to the original Brave search snippet when no exact-URL passage survives
- light cleanup of returned passage text

### Why this stage exists

Brave search snippets are often too thin, but full-page retrieval is too expensive for the active downscoped pipeline.

This helper gives the system a middle layer:

- richer than raw snippets
- cheaper than deep fetch
- still URL-linked for provenance

This is shallow evidence, not full-page retrieval.

---

## 6. ExtractorLight

**Purpose:** get candidate entity names before doing any full field extraction.

### Inputs

- `PlannerOutput`
- `BraveContextOutput`

### Outputs

- `candidate_names`
- `name_to_source_urls`
- `mention_counts`

### Why this stage exists

This stage is the entity-anchor for the rest of the pipeline.

It is needed because the system should not jump directly from URL passages to fully structured rows. The intermediate name-extraction step gives:

- a bounded candidate list
- name-to-URL mention mapping
- mention counts for rough prominence
- a cleaner boundary between “who are the entities?” and “what fields do they have?”

### What it does not do

- no field extraction
- no ranking
- no alias resolution beyond pragmatic name extraction
- no final eligibility decisions

---

## 7. Assessor

**Purpose:** classify shortlisted sources before they become evidence.

### Inputs

- `PlannerOutput`
- `SearcherOutput`
- `BraveContextOutput`
- `ExtractorLightOutput`

### Outputs

- per-URL assessed source records

### What it owns

- heuristic pre-signals in code
- heuristic-first source routing before any LLM source judgment
- immediate filtering of obviously weak sources
- a narrower LLM fallback only for sources that survive heuristic filtering
- classification of:
  - `source_role`
  - `source_quality`
  - `officiality`
  - `estimated_aspect_coverage`
  - `evidence_sufficiency`

### Why it exists

Not all URLs should contribute equally to extraction. The Assessor provides the source-level semantics the deterministic pipeline needs later:

- official vs third-party vs low-quality
- high vs medium vs low source quality
- whether a URL is discovery-like, verification-like, or corroborative

This stage is where source semantics enter the pipeline.

### Active implementation notes

The current active Assessor is no longer a single monolithic LLM triage step.

Instead it works in two layers:

1. heuristic source assessment
2. narrower LLM fallback for non-filtered survivors

The heuristic layer currently evaluates:

- obvious low-quality/junk-source patterns
- weak snippet/context signals
- officiality hints from domain/name/path overlap
- broad third-party/editorial patterns

Sources can be marked `filtered_out` by the heuristic layer. Those sources remain in the assessed-source output for transparency, but they are not supposed to contribute evidence downstream.

Only non-filtered sources are sent to the LLM fallback.

The active LLM fallback is intentionally smaller in scope than the original design. It uses the heuristic outputs as hints and then assigns the final per-source labels for surviving URLs.

---

## 8. Evidence Store Builder

**Purpose:** build an entity-centric evidence store from shallow evidence plus source assessments.

### Inputs

- `BraveContextOutput`
- `ExtractorLightOutput`
- `AssessorOutput`
- optional existing `EvidenceStore`

### Outputs

- `EvidenceStore`

### Evidence attachment policy

Evidence is attached to entities using:

1. ExtractorLight name-to-URL mapping first
2. conservative fallback string matching second

The builder is intentionally conservative:

- ambiguous evidence can remain attached to more than one entity
- unsupported evidence is not converted into structured fields here
- provenance is preserved on every chunk
- sources marked `filtered_out` by the Assessor are excluded from evidence attachment

### Interesting design decisions

The builder does more than just store text. It also computes per-entity evidence strength signals used for extraction-time filtering.

Per entity, it stores a deterministic `entity_score`:

- each distinct high-quality source URL contributes `+1.0`
- each distinct medium-quality source URL contributes `+0.5`
- low-quality sources contribute `+0.0`

Important detail:

- scoring is by distinct source URL, not chunk count

This avoids over-rewarding one source that happens to produce many chunks.

### Chunk construction

The builder uses anchored sentence-window extraction around entity mentions:

- it expands from an anchor sentence
- respects paragraph boundaries
- stops at configured length bounds
- avoids over-expanding into other-entity material

This gives cleaner entity-specific evidence slices than whole-passage attachment.

---

## 9. Extractor

**Purpose:** convert entity-centric evidence into structured rows with field-level provenance.

### Inputs

- `PlannerOutput`
- `ExtractorLightOutput`
- `EvidenceStore`

### Outputs

- `ExtractorOutput`

### What it owns

- field extraction for planner-defined schema columns
- conservative null-default behavior
- field-level evidence carry-through
- per-entity structured output

### Important active design decisions

The Extractor is intentionally anchored and bounded.

It does not extract over every candidate entity blindly. Before any LLM calls, it ranks entities and keeps only the top 10.

Entity ordering is deterministic:

1. higher `entity_score`
2. more distinct supporting source URLs
3. more total supporting chunk text length
4. alphabetical entity name

This is one of the main latency-control choices in the active system.

### Why top-10 happens here

The expensive part is per-entity extraction. Filtering before extraction saves cost and latency more than filtering after extraction.

### Extraction behavior

For each retained entity:

- consume its evidence-store slice
- extract planner-schema fields only
- prefer null to unsupported values
- attach evidence to every non-null field

The active Extractor is one LLM call per retained entity and uses minimal reasoning effort because this task is bounded extraction, not open-ended reasoning.

### What is intentionally not in the active Extractor

- no new-entity discovery beyond the ExtractorLight candidate set
- no repair-time enrichment
- no global reranking logic
- no MMR/diversity pass

---

## 10. Finalizer

**Purpose:** shape the extracted rows into the final user-facing response.

### Inputs

- `PlannerOutput`
- `ExtractorOutput`

### Outputs

- `final_rows`

### Active behavior

The Finalizer is intentionally thin in the current implementation.

It does not do evaluator-style ranking or diagnostics anymore. It simply converts extracted entities into the user-facing row shape:

- `name`
- `fields`
- `source_urls`

This is a deliberate downscope. The real value now is already in the Extractor output; the Finalizer is a response shaper, not an evaluation engine.

### Why this downscope was chosen

- the product only needs top 10 rows
- extractor already performs the meaningful gating
- evaluator-style diagnostics were not user-facing
- repair logic and richer final ranking were not justified for the current scope

---

## 11. Final Response Shape

The active user-facing response is intentionally simple:

- one row per final entity
- planner-driven fields
- field-level evidence
- row-level `source_urls`

Internal scoring and diagnostics are not returned.

---

## 12. What Was Left Out

The active implementation is intentionally smaller than the north-star system.

Not implemented in the active flow:

- verification-query generation and a verification sub-pass
- Jina deep-fetch selection over the evidence store
- second evidence merge from deep fetches
- evaluator-style final ranking with evidence-strength scoring
- MMR/diversification in final selection
- repair diagnostics and a single repair round
- more ambitious canonicalization / duplicate merge logic

These are valid future extensions, but they were excluded to keep the current system:

- inspectable
- bounded
- fast enough to iterate
- aligned to the minimum challenge requirements

---

## 13. Summary

The active system is a bounded deterministic pipeline where:

- the Planner turns a raw query into entity type, schema, aspects, and intent-covering rewrites
- the Searcher turns those rewrites into a bounded URL pool
- Brave LLM Context provides shallow URL-linked evidence
- ExtractorLight establishes entity anchors early
- the Assessor adds source semantics
- the Evidence Store Builder converts URL evidence into an entity-centric store and computes entity scores
- the Extractor performs the real top-10 gating and field extraction with provenance
- the Finalizer returns only the user-facing rows

That is the source of truth for the current implementation.
