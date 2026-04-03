# Agentic Search — Recommended System Flow

## Challenge

Build a system that takes a topic query (e.g., "AI startups in healthcare", "top pizza places in Brooklyn", "open source database tools") and produces a structured table of discovered entities with relevant attributes, sourced from the web.

### Minimum Requirements

- Accept a topic query
- Search the web for relevant results (use any search API, Brave, SerpAPI, etc.)
- Scrape and process web pages from search results
- Use LLMs to extract structured entity data from the scraped content
- Return a table of results in a structured format (JSON or rendered)
- Each cell value should be traceable to its source

### Guidelines

- Your solution can include a web API, a frontend, or both, up to you
- Any language or framework is fine
- Use any LLM API (OpenRouter, OpenAI, local models, etc.)
- You can use any AI coding tools for development

### How We'll Evaluate

Your submission will be compared against other candidates on:

- **Output quality:** do the results actually make sense? Are they accurate and useful for real queries? Are latency and cost reasonable for a real system?
- **Design choices:** what problems did you identify and how did you solve them? What trade-offs did you make?
- **Code structure:** is the codebase well-organized and readable?
- **Documentation:** clear setup instructions, explanation of your approach, and known limitations
- **Complexity of implementation:** how far did you push the solution beyond the basics?

---

## 0. Core Architectural Stance

- The system uses a **deterministic orchestration/controller module in code**, not an LLM orchestrator.
- The main pipeline is fixed.
- The system allows **one bounded feedback / repair round**.
- There is **no open-ended recursive agent loop**.
- LLM-backed reasoning is used only where semantic judgment is genuinely valuable.
- Query normalization exists only as a **small input guardrail**, not as a major subsystem.

---

## 1. Runtime Components

### 1.1 Controller Module

Owns:

- stage order
- state passing
- budgets
- stop conditions
- repair gating
- one-repair-only enforcement
- evidence store construction and merging

### 1.2 Mostly Deterministic / Code-Driven Components

- **Controller**
- **Searcher**
  - executes Brave Web Search queries
  - collects ranked results, titles, snippets, domains, metadata
  - applies mechanical URL pruning
  - dedupes exact duplicate URLs
  - merges multi-query result lists by rank
  - builds bounded shortlist

### 1.3 Hybrid Components

- **Assessor**
  - heuristic pre-signals computed in code
  - one batched LLM assessment over shortlisted URLs
  - source role classification
  - per-entity verification gap detection
- **ExtractorLight**
  - lightweight LLM call over Brave LLM Context output
  - candidate name extraction only
  - name → URL mention mapping

### 1.4 Mostly LLM-Backed Components

- **Planner**
- **Extractor**
- **Canonicalizer+Verifier+Evaluator**

---

## 2. Global Execution Policy

### 2.1 Deterministic Stage Order

The controller always runs stages in this order:

1. Planner
2. Searcher
3. Brave LLM Context on bounded shortlist
4. ExtractorLight
5. Assessor (first pass)
6. Targeted verification queries (bounded)
7. Brave LLM Context on verification URLs
8. Assessor (light second pass on new URLs)
9. Controller builds evidence store
10. Assessor decides Jina fetches
11. Extractor
12. Canonicalizer+Verifier+Evaluator
13. Optional single repair round
14. Return final result

### 2.2 Allowed "Return to Older Stages"

- Targeted verification queries between steps 5 and 6, bounded to max 5–7 queries total
- One repair round, where outputs from the final stage trigger another targeted Searcher → Brave LLM Context → ExtractorLight → Assessor → Extractor → Canonicalizer+Verifier+Evaluator cycle

### 2.3 Forbidden Behavior

- no open-ended self-looping
- no full replanning from scratch after extraction
- no unlimited query expansion
- no arbitrary agent-to-agent recursion

---

## 3. Request Initialization

The controller initializes:

- request ID
- raw query
- empty candidate name list
- empty evidence store: `entity_name → [evidence chunks]`
- empty candidate entity store
- `repair_used = false`

### Recommended Budgets

| Budget | Value |
|---|---|
| max total search rounds | 2 |
| max Brave Web Search queries (initial) | 4 |
| max verification queries | 5–7 |
| max shortlisted URLs for Brave LLM Context | 12–15 |
| max Jina deep fetches per request | 5–7 |
| max repair rounds | 1 |
| max final rows returned | 10 |

---

## 4. Stage 1 — Planner

**Purpose:** convert the raw query into a concrete extraction plan.

### Inputs

- raw user query

### Outputs

- `entity_type`
- `query_mode`
- `schema`
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
- define the final table columns
- define the main aspects that matter for quality and diversity
- generate the base query and any initial rewrites

### Query Normalization Policy

This is a **thin robustness layer**, not a major feature.

**If already a topic query:**
- `is_topic_query = true`
- `normalized_query = raw query`
- `normalization_note = null`

**If slightly non-topic but clearly convertible:**
- `is_topic_query = false`
- produce a conservative `normalized_query`
- set a short `normalization_note`
- continue with normalized query

**If conversion would require strong reinterpretation:**
- `error = true`
- stop the pipeline
- return a clear message

### Typical Constraints

- schema: **5–7 columns**
- aspects: **2–5**
- initial rewrites: **0–3**
- planner runs **once per request**

### Important Ownership Rule

- **Planner** owns the base query and initial rewrites
- **Searcher** only executes them
- **Canonicalizer+Verifier+Evaluator** may later propose repair-time follow-up queries

### If the Query is Ambiguous

- never ask the user
- choose a conservative interpretation if possible and use it
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

- execute base query and planner-provided rewrites against Brave Web Search
- collect ranked results, titles, snippets, domains, and metadata
- apply mechanical URL pruning
- dedupe exact duplicate URLs across query result lists
- merge multi-query result lists by rank
- build bounded shortlist for Brave LLM Context

### Nature of This Stage

- mostly deterministic / code-driven
- does not generate semantics itself
- only executes planner-provided queries or evaluator-provided repair queries

### Mechanical Pruning Rules

Applied in code before any LLM call. Drop URLs matching any of:

- exact duplicate URLs appearing across multiple query results (keep at best rank position)
- social media post URLs (`twitter.com/status/`, `facebook.com/posts/`, `instagram.com/p/`) — note: `linkedin.com/company/` pages are kept, post URLs are dropped
- video URLs (`youtube.com`, `vimeo.com`)
- file extension URLs (`.pdf`, `.ppt`, `.doc` in URL string)
- snippets that are clearly navigation/boilerplate ("sign in to continue", "page not found", "click here")
- results with empty snippets
- results with zero keyword overlap with query AND zero keyword overlap with any planner aspect

### Multi-Query Merge Policy

- dedupe across all query result lists
- if the same URL appears in multiple lists, keep it once at its best rank position
- apply hard cap after dedup: top N by Brave rank (target **12–15 URLs**)

### Search Policy

- always run the base query
- run planner rewrites only if within the global query budget
- use Brave search controls (freshness, pagination, result filtering) only when relevant to `query_mode`

### Output

- pruned, deduped shortlist of candidate URLs
- result metadata per URL: title, snippet, domain, rank position, query source

---

## 6. Brave LLM Context — First Pass

**Purpose:** acquire richer first-pass evidence on shortlisted URLs before semantic assessment.

### What It Is Used For

- provide richer content than raw Brave snippets
- feed ExtractorLight for candidate name discovery
- feed Assessor for source role classification and quality assessment
- provide provisional provenance signals

### What It Is Not Used For

- not the final truth source for field values
- not a replacement for Jina when deeper evidence is needed
- not run on all returned URLs — only on the pruned bounded shortlist

### Output

- URL-linked passages and content
- source metadata per URL

---

## 7. Stage 3 — ExtractorLight

**Purpose:** extract candidate entity names from Brave LLM Context output. Strictly lightweight.

### Inputs

- Brave LLM Context output for shortlisted URLs
- `entity_type` from Planner

### Responsibilities

- identify candidate entity names mentioned across all LLM Context passages
- record which URLs mention each entity name
- produce coarse mention counts per entity

### Output

- flat candidate name list
- `name → [source URLs]` mention map
- coarse mention count per name

### Strict Constraints

- outputs names only — no fields, no schema, no provenance
- does not resolve duplicates or aliases
- does not score entities
- does not make eligibility decisions
- one LLM call over aggregated LLM Context output

---

## 8. Stage 4 — Assessor (First Pass)

**Purpose:** classify sources, assess quality, and detect per-entity verification gaps.

### Inputs

- `normalized_query`
- `schema`
- `core_aspects`
- shortlisted URLs with metadata
- Brave LLM Context passages
- heuristic pre-signals (computed in code)
- candidate name list and `name → URL` map from ExtractorLight

### 8.1 Heuristic Pre-Signals (computed in code)

- `relevance_hint` — keyword overlap between query/aspects and title/snippet
- `domain_match_hint` — whether domain roughly matches a likely entity name
- `official_path_hint` — whether URL path contains `/about`, `/company`, `/contact`, `/team`
- `snippet_thinness_hint` — whether snippet is too short or vague
- `rank_hint` — original Brave search rank position
- `source_metadata` — hostname, title, snippet length, result type

### 8.2 Batched LLM Assessment

One batched LLM call over all shortlisted URLs producing per URL:

- `source_role` — discovery / verification / corroboration
- `source_quality` — high / medium / low
- `officiality` — official / near-official / third-party / low-quality
- `estimated_aspect_coverage` — which planner aspects this URL likely covers
- `evidence_sufficiency` — whether Brave LLM Context alone is enough

### 8.3 Per-Entity Verification Gap Detection

Using the candidate name list from ExtractorLight and source role classifications:

- for each candidate entity name, check: is there at least one verification-role URL mentioning this entity?
- if not, flag that entity as needing a targeted verification query

### Output

- per-URL assessment: source role, quality, officiality, aspect coverage, evidence sufficiency
- list of flagged entities needing verification queries
- suggested verification query per flagged entity

---

## 9. Targeted Verification Queries (Bounded)

**Purpose:** ensure each candidate entity has at least one verification-role source before full extraction.

### Policy

- run targeted Brave Web Search queries for flagged entities
- batching multiple flagged entities into a single query is allowed and preferred
- hard cap: **5–7 verification queries maximum** regardless of how many entities are flagged
- if more entities are flagged than the cap allows, prioritize by mention count from ExtractorLight
- do not implement a one-query-per-entity loop

### Output

- new Brave Web Search results for flagged entities
- passed to Brave LLM Context (second pass) and Assessor (light second pass)

---

## 10. Brave LLM Context — Second Pass

**Purpose:** acquire LLM Context passages for new verification URLs only.

- run only on URLs returned by targeted verification queries
- same output format as first pass
- output merged into evidence store alongside first-pass results

---

## 11. Assessor — Light Second Pass

**Purpose:** classify and quality-check new verification URLs only.

- same batched LLM assessment as first pass
- runs only on new verification URLs
- output merged into overall source assessment map

---

## 12. Controller Builds Evidence Store

**Purpose:** construct the entity-centric in-memory evidence store before full extraction.

This is **deterministic controller logic**, not a separate agent.

### Evidence Store Structure
```python
evidence_store = {
    "Entity Name": [
        {
            "text": "...",
            "source_url": "...",
            "source_role": "verification",
            "source_quality": "high",
            "officiality": "official",
            "from": "brave_llm | jina",
            "aspect_coverage": ["funding", "geography"]
        }
    ]
}
```

### How It Is Populated

- ExtractorLight `name → URL` mapping: establishes which URLs mention which entities
- Assessor source role + quality tags: attached to each evidence chunk
- Brave LLM Context passages: attributed to entities via name matching against ExtractorLight mapping
- Jina chunks (added later by Extractor): attributed via name matching + ExtractorLight mapping

### Attribution Policy

- **primary:** use ExtractorLight `name → URL` mapping
- **fallback:** conservative string name matching within chunk text
- **ambiguous chunks:** attribute to all matching entities — do not drop ambiguous chunks; over-eager attribution is worse than multi-attachment

---

## 13. Assessor Decides Jina Fetches

**Purpose:** given the full evidence store, decide which URLs deserve Jina deep fetch.

### Inputs

- full evidence store
- per-URL assessments from both Assessor passes
- remaining Jina fetch budget

### Decision Criteria

**Set `should_deep_fetch = true` if at least one is true:**

- page is official or near-official
- page likely contains a core missing field for a strong candidate entity
- page may resolve an important field conflict
- Brave LLM Context evidence for this URL is too thin for reliable extraction
- page covers an under-covered planner aspect
- page is the only verification-role source for a candidate entity

**Set `should_deep_fetch = false` if:**

- page is redundant and low quality
- adds no new aspect coverage
- Brave LLM Context evidence is already sufficient
- remaining fetch budget is better spent on higher-value pages

### Fetch Policy

- fetch at most **5–7 pages total**
- prioritize by: officiality > source quality > aspect gap > missing field impact
- do not fetch based on rank alone

### Fetch Failure Handling

- mark URL as failed
- continue if enough evidence remains
- replace only if page was critical and budget remains

### In-Memory Chunking for Large Pages

- chunk only after successful Jina fetch
- split by headings, paragraphs, sections
- keep only most relevant chunks
- no persistent index or vector DB

---

## 14. Stage 5 — Extractor

**Purpose:** convert the evidence store into fully structured candidate entities with field-level provenance.

### Inputs

- evidence store (Brave LLM Context chunks + Jina chunks, role/quality tagged)
- candidate name list from ExtractorLight (used as prior)
- schema and core aspects from Planner

### Responsibilities

- for each candidate entity, consume all evidence store chunks attributed to it
- extract field values from combined evidence
- attach field-level provenance from day one
- resolve field contradictions using source role priority
- attach confidence per field
- add new entities freely if evidence reveals ones not in candidate name list
- only remove or contradict existing candidates if evidence is strongly contradicting

### Required Data Model

Each field stored as:
```
value
confidence
evidence[]
```

Each evidence item includes:
```
source_url
source_title
supporting_snippet
source_role
source_quality
officiality
```

### Extraction Rules

- do not hallucinate unsupported values
- if support is weak, leave field null
- if multiple values compete, use source role priority to resolve:
  1. verification source
  2. independent corroboration
  3. discovery source
- if unresolvable, preserve conflict for Canonicalizer

### Minimum Candidate Requirement

A candidate row must have:

- entity name
- at least one supporting source
- at least one additional core field with evidence

Otherwise keep provisional only, exclude from final selection.

---

## 15. Stage 6 — Canonicalizer+Verifier+Evaluator

**Purpose:** turn extracted candidate entities into final ranked rows and diagnose whether a repair round is needed.

Five tightly related functions:

1. canonicalization
2. verification
3. eligibility filtering
4. ranking + diversified top-10 selection
5. repair diagnostics

### 15.1 Canonicalization

**Goal:** merge any remaining duplicate entity mentions.

**Merge signals (cheap first):**

- normalized entity name
- website/domain match
- official-domain alignment
- same address/location for local entities

Use semantic similarity only if cheap signals are inconclusive.

**Ambiguous merge handling:**

- do not merge aggressively
- keep candidates separate unless evidence is strong
- if needed, use a targeted inline LLM call inside this stage only

### 15.2 Verification

**Goal:** resolve field values and remove weak support.

**Field resolution rules (in priority order):**

1. verification-role source support
2. independent multi-source corroboration
3. higher source quality
4. stronger snippet evidence

If conflict remains unresolved:

- keep best-supported value with lower confidence, or
- set field to null if uncertainty is too high

### 15.3 Eligibility Filtering

**Goal:** prevent weak rows from entering final ranking.

An entity is eligible if at least one is true:

- one verification-role source supports identity plus at least one more core field
- two independent non-verification sources support the entity with strong evidence
- completeness and evidence quality exceed defined threshold

Verification-role source is a **strong positive signal** but absence is not an automatic hard fail — it reduces evidence strength score instead.

If ineligible:

- exclude from final ranking
- retain internally as low-confidence candidate

### 15.4 Ranking Policy

**Step A — hard quality floor:**
Eligibility filter is the hard gate.

**Step B — two ordering signals:**

`evidence_strength`:

- `3` = verification source + at least 2 supported core fields
- `2` = at least 2 independent non-verification supports + at least 2 supported core fields
- `1` = minimum acceptable support
- `0` = ineligible

`aspect_coverage`:

- count of planner aspects covered with actual evidence
- optionally normalized by total aspect count

**Ordering:**

1. higher `evidence_strength`
2. break ties with `aspect_coverage`

### 15.5 Diversified Top-10 Selection

Greedy MMR-style selector:

1. order eligible entities by ranking policy
2. iteratively pick entity maximizing row quality minus redundancy with already selected entities

**Redundancy signals:**

- near-duplicate name
- same website/domain family
- same subtype/category
- same geography
- same aspect pattern
- highly similar evidence profile

### 15.6 Repair Diagnostics

**Output fields:**

- `num_strong_entities`
- `aspect_coverage_by_aspect`
- `missing_key_fields_rate`
- `redundancy_score`
- `verification_source_coverage`
- `repair_recommended`
- `repair_reason`
- `missing_aspects`
- `weak_fields`
- `suggested_followup_queries`

**Boundary ownership:**

- **Canonicalizer+Verifier+Evaluator** generates `suggested_followup_queries`
- **Controller** decides whether repair is allowed and executed

**Repair triggers:**

- fewer than ~8 strong eligible entities
- one or more core aspects under-covered
- too many important fields missing across top rows
- redundancy in selected set too high
- evidence concentrated in one source type
- verification source coverage weak
- visible topic drift

---

## 16. Controller-Level Repair Gating

Repair happens only if **all** are true:

- `repair_recommended = true`
- `repair_used = false`
- global search/fetch budgets still allow it
- expected value of repair is non-trivial

**If repair not allowed:** stop and return current best result.

**If repair allowed:** set `repair_used = true`, launch one targeted repair round.

---

## 17. Single Bounded Repair Round

### Repair Behavior

Controller runs:

1. **Searcher** — 1–2 targeted follow-up queries from `suggested_followup_queries`
2. **Brave LLM Context** on new URLs
3. **ExtractorLight** on new LLM Context output (name extraction + URL mapping on new results only)
4. **Assessor** — classify + quality check new URLs
5. **Controller** merges new evidence into existing evidence store
6. **Assessor** decides Jina fetches for new URLs
7. **Extractor** enriches existing entities + adds new ones from augmented evidence store
8. **Canonicalizer+Verifier+Evaluator** runs again on full augmented candidate pool

### Important Repair Properties

- repair is targeted, not a full restart
- schema and core aspects stay fixed
- repair happens **once at most**

### Repair Budgets

- extra search queries: **1–2**
- extra Jina fetches: **up to 3**
- repair loops: **1 max**

---

## 18. Stop Conditions

Controller stops when any of these are true:

- first-pass result is good enough and repair not triggered
- repair round already used
- search/fetch budgets exhausted
- no remaining action likely to materially improve quality

---

## 19. Final Output

Return:

- `original_query`
- `normalized_query` (if different from original)
- `normalization_note` (if query was lightly converted)
- `inferred_schema`
- `final_top_10_rows` with field-level provenance
- `row_level_confidence`
- optional diagnostics metadata:
  - total queries used
  - total URLs considered
  - total Jina fetches
  - whether repair was used
  - aspect coverage summary

---

## 20. Final One-Paragraph System Summary

The system is a **deterministically orchestrated, bounded multi-stage pipeline**. The **Planner** infers entity type, schema, and aspects from the query, lightly normalizing slightly non-topic inputs only when a conservative topic interpretation is obvious. The **Searcher** executes Planner-provided queries against Brave Web Search, applies mechanical URL pruning, dedupes exact duplicates, merges multi-query result lists by rank, and builds a bounded shortlist. **Brave LLM Context** is run on this bounded shortlist to acquire richer first-pass evidence. **ExtractorLight** makes one lightweight LLM call over the LLM Context output to produce a flat candidate name list and a name-to-URL mention map — no fields, no provenance. The **Assessor** uses heuristic pre-signals plus one batched LLM assessment to classify source roles, assess quality, and detect per-entity verification gaps; targeted verification queries are then run for flagged entities, bounded to 5–7 maximum, with batching preferred over one-query-per-entity. The **Controller** builds an entity-centric in-memory evidence store from all accumulated Brave LLM Context chunks tagged with source role and quality, with ambiguous chunks attached to all matching entities rather than dropped; the **Assessor** then makes Jina deep-fetch decisions over the full evidence store. The **Extractor** consumes the evidence store per entity, resolves field contradictions using source role priority, and produces fully structured candidate rows with field-level provenance from day one. **Canonicalizer+Verifier+Evaluator** merges remaining duplicates, resolves fields, applies eligibility filtering, ranks entities by evidence strength and aspect coverage, selects a diversified top-10 via MMR, and emits structured repair diagnostics including suggested follow-up queries. The **Controller** enforces all budgets and may launch **one targeted repair round** if diagnostics show insufficient coverage, weak evidence, or poor diversity. No open-ended agentic loop is allowed.