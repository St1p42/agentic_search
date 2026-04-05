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
- The main pipeline is fixed.
- There is no second-pass verification loop in the active flow.
- There is no repair loop in the active flow.
- There is no open-ended recursive agent loop.
- LLM-backed reasoning is used only where semantic judgment is worth the cost.
- Query normalization is a thin guardrail, not a major subsystem.
- Provenance is part of the core data model, not optional metadata.

---

## 1. Runtime Components

### 1.1 Orchestrator Module

Owns:

- stage order
- state passing
- request-scoped budgets
- evidence store construction and merging
- final response assembly

### 1.2 Mostly Deterministic / Code-Driven Components

- **Orchestrator**
- **Searcher**
  - executes Brave Web Search queries
  - collects ranked results, titles, snippets, domains, and provider metadata
  - applies mechanical pruning
  - dedupes exact duplicate URLs
  - merges multi-query result lists
  - builds the bounded shortlist
- **Brave LLM Context helper**
  - fetches shallow URL-linked context for the bounded shortlist
  - filters passages to exact URL matches only
  - falls back to the original Searcher snippet when needed
  - performs deterministic line-level cleanup
- **Evidence Store Builder**
  - merges shallow evidence chunks into an entity-centric evidence store

### 1.3 Hybrid Components

- **Assessor**
  - computes heuristic pre-signals in code
  - runs one batched LLM source assessment over shortlisted sources
  - classifies source role, source quality, officiality, rough aspect coverage, and evidence sufficiency
- **ExtractorLight**
  - lightweight LLM call over Brave LLM Context output
  - candidate-name extraction only
  - name → URL mention mapping
  - mention counts

### 1.4 Mostly LLM-Backed Components

- **Planner**
- **Extractor**
- **Final row selection / response shaping**
  - may still contain deterministic filtering around the final extractor output

---

## 2. Global Execution Policy

### 2.1 Deterministic Stage Order

The orchestrator always runs stages in this order:

1. Planner
2. Searcher
3. Brave LLM Context on bounded shortlist
4. ExtractorLight
5. Assessor (first pass only)
6. Orchestrator builds evidence store
7. Extractor
8. Final row selection / response

### 2.2 Forbidden Behavior

- no open-ended self-looping
- no verification-query sub-pass in the active pipeline
- no Jina deep-fetch orchestration in the active pipeline
- no repair round in the active pipeline
- no full replanning after extraction
- no unlimited query expansion
- no arbitrary agent-to-agent recursion

---

## 3. Request Initialization

The orchestrator initializes:

- request ID
- raw query
- empty candidate name list
- empty evidence store: `entity_name -> [evidence chunks]`
- empty candidate entity store

### Recommended Budgets

| Budget | Value |
|---|---|
| max Brave Web Search queries (initial) | 4 |
| max shortlisted URLs for Brave LLM Context | 12–15 |
| max Brave context passages per URL kept downstream | 2–3 |
| max final rows returned | 10 |

These are operating targets, not hard-coded universal constants.

---

## 4. Stage 1 — Planner

**Purpose:** convert the raw query into a concrete retrieval and extraction plan.

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

### Responsibilities

- assess whether the input is already a topic query suitable for entity discovery
- if slightly non-topic but clearly convertible, normalize it conservatively
- if no reasonable topic interpretation exists, return `error = true` and stop the pipeline
- infer what kind of entities the user wants
- define the table columns
- define the main aspects that matter for downstream extraction and comparison
- generate the base query and any initial rewrites

### Query Normalization Policy

This is a thin robustness layer, not a major feature.

**If already a topic query:**
- `is_topic_query = true`
- `normalized_query = raw query`
- `normalization_note = null`

**If slightly non-topic but clearly convertible:**
- `is_topic_query = false`
- produce a conservative `normalized_query`
- set a short `normalization_note`
- continue with the normalized query

**If conversion would require strong reinterpretation:**
- `error = true`
- stop the pipeline
- return a clear message

### Typical Constraints

- schema: **4–6 columns**
- aspects: **1–5**
- initial rewrites: **0–3**
- planner runs **once per request**

### Important Ownership Rule

- **Planner** owns the base query and initial rewrites
- **Searcher** only executes them

### If the Query is Ambiguous

- never ask the user
- choose a conservative interpretation if possible
- if not, stop and return a structured error

---

## 5. Stage 2 — Searcher

**Purpose:** produce a strong but bounded candidate URL pool using Brave Web Search.

### Inputs

- `normalized_query`
- `base_query`
- `initial_query_rewrites`
- `query_mode`

### Responsibilities

- execute the base query and planner-provided rewrites against Brave Web Search
- collect ranked results, titles, snippets, domains, and metadata
- apply mechanical URL pruning
- dedupe exact duplicate URLs across query result lists
- merge multi-query result lists by best rank, with multi-query support as a deterministic tie-breaker
- use soft round-robin reserved slots so planner rewrites can contribute to the shortlist without over-bias toward the base query
- keep a small per-domain shortlist cap without doing domain-level deduplication
- build the bounded shortlist for Brave LLM Context

### Nature of This Stage

- mostly deterministic / code-driven
- does not generate semantics itself
- only executes planner-provided queries

### Mechanical Pruning Rules

Applied in code before any LLM call. Drop URLs matching any of:

- exact duplicate URLs appearing across multiple query results
- social media post URLs such as `twitter.com/status/`, `facebook.com/posts/`, `instagram.com/p/`
- video URLs such as `youtube.com`, `vimeo.com`
- file-extension URLs such as `.pdf`, `.ppt`, `.doc` in the URL string
- clearly navigational/boilerplate snippets
- results with empty snippets
- results with zero keyword overlap with the query and zero keyword overlap with planner aspects

### Important Ownership Rule

- Searcher must not generate semantic rewrites on its own
- Searcher must not decide deep fetch
- Searcher must not rank final entities

---

## 6. Stage 3 — Brave LLM Context on Shortlist

**Purpose:** enrich the bounded shortlist with shallow, URL-linked textual evidence before extraction.

### Inputs

- `SearcherOutput.shortlisted_results`

### Outputs

- `BraveContextOutput`

### Responsibilities

- call Brave LLM Context only for the shortlisted URLs
- run a narrow query per shortlisted result using title, snippet prefix, and `site:<hostname>`
- retain only passages whose `source_url` exactly matches the shortlisted URL
- fall back to the original Searcher snippet when no exact-URL Brave passage survives
- clean passage text deterministically before returning it downstream

### Important Constraints

- this is shallow evidence, not full-page retrieval
- exact-URL attachment is strict
- cleanup must remain deterministic and conservative

---

## 7. Stage 4 — ExtractorLight

**Purpose:** discover candidate entity names from shallow context without attempting full extraction.

### Inputs

- `PlannerOutput`
- `BraveContextOutput`

### Outputs

- `candidate_names`
- `name_to_source_urls`
- `mention_counts`

### Responsibilities

- extract likely candidate names only
- build a name → source URL mention map
- count coarse mentions

### Important Constraints

- no schema field extraction
- no provenance synthesis beyond the name-to-URL mapping
- no canonicalization
- no row ranking
- no eligibility decisions

---

## 8. Stage 5 — Assessor (First Pass Only)

**Purpose:** classify shortlisted sources for downstream evidence use.

### Inputs

- `PlannerOutput`
- `SearcherOutput`
- `BraveContextOutput`
- `ExtractorLightOutput`

### Outputs

- `AssessorOutput`

### Responsibilities

- compute heuristic source signals in code
- perform one batched semantic source assessment
- classify:
  - `source_role`
  - `source_quality`
  - `officiality`
  - `estimated_aspect_coverage`
  - `evidence_sufficiency`

### Nature of This Stage

- hybrid: code-generated heuristics plus one LLM judgment pass
- source triage only

### Important Constraints

- no verification-gap generation in the active flow
- no second-pass reassessment
- no Jina URL selection
- no repair-time decisions

---

## 9. Stage 6 — Evidence Store Build

**Purpose:** build the orchestrator-owned entity-centric evidence store.

### Inputs

- `BraveContextOutput`
- `ExtractorLightOutput`
- `AssessorOutput`
- optional existing `EvidenceStore`

### Outputs

- `EvidenceStore`

### Responsibilities

- merge evidence chunks into `entity_name -> [evidence chunks]`
- attach chunks using ExtractorLight name-to-URL mapping first
- use conservative string matching as fallback
- preserve source URL, source labels, origin, and aspect coverage
- allow ambiguous chunks to remain attached to multiple candidate entities until later resolution

### Important Constraint

- over-eager attribution is worse than multi-attachment

---

## 10. Stage 7 — Extractor

**Purpose:** convert entity-centric evidence into structured candidate rows.

### Inputs

- `PlannerOutput`
- `ExtractorLightOutput`
- `EvidenceStore`

### Outputs

- `ExtractorOutput`

### Responsibilities

- produce structured candidate entities
- attach field-level provenance
- resolve straightforward contradictions where evidence allows it
- prefer null over unsupported values

### Important Constraint

- Extractor consumes the evidence store; it does not decide what to fetch

---

## 11. Stage 8 — Final Row Selection / Response

**Purpose:** turn extracted candidates into the final response.

### Inputs

- `PlannerOutput`
- `ExtractorOutput`

### Outputs

- final response object with inferred schema and selected rows

### Responsibilities

- filter weak candidates
- resolve remaining duplication or row-eligibility issues
- choose the final row set
- preserve source traceability in the returned structure

### Important Constraint

- do not rely on a weighted-sum final ranker

---

## 12. Why This Reduced Flow

This flow is intentionally narrower than the original north-star design.

It keeps:

- deterministic orchestration
- bounded retrieval
- shallow evidence enrichment
- lightweight candidate discovery
- source-quality triage
- entity-centric evidence merging
- structured extraction

It removes, for now:

- verification-query sub-passes
- Jina-based deep-fetch orchestration
- repair loops

That makes the system easier to finish cleanly and easier to test end-to-end without carrying partially implemented complexity.
