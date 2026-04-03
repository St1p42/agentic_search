# Agent Context

Hey - I will send you some context now but don't take any actions yet, I will ask you to do things based on that after you process it. Basically, I am doing a challenge, the definition of which I will send below. And I already have a proposed solution. I don't ask you to evaluate the solution, but rather to implement it step-by-step ONLY when I ask you to. Unless I don't, either don't take any actions or just propose the solution of the requested part to me for approval.

Below is a compact set of prompts/context blocks you can share with Codex agents.

---

## Global Context for All Agents

You are implementing one stage of a bounded, deterministic multi-stage system. The challenge description and the business/design flow are provided separately; do not restate or reinterpret them. Follow them as the source of truth. This implementation plan is only about engineering boundaries, contracts, and ownership.

---

## Non-Negotiable Global Rules

- The system uses a deterministic controller in code, not an LLM orchestrator.
- There is at most one repair round.
- There is no open-ended loop, no recursive orchestration, and no free-form agent-to-agent calling.
- Provenance is part of the field model, not optional metadata.
- Do not implement a weighted-sum final ranker.
- Planner owns the initial semantic query generation including all initial rewrites.
- Searcher only executes queries and builds result pools — it does not generate semantic rewrites.
- Brave LLM Context is run only on the bounded pruned shortlist, not on all returned URLs.
- ExtractorLight produces candidate names and a name→URL mention map only — no fields, no provenance, no schema.
- Assessor owns source role classification, source quality assessment, per-entity verification gap detection, and Jina fetch decisions.
- Extractor consumes the evidence store — it does not decide what to fetch.
- Controller owns evidence store construction and merging.
- Canonicalizer+Verifier+Evaluator owns repair-time suggested follow-up queries.
- Controller decides whether repair is allowed.
- Query normalization is only a small guardrail, not a major subsystem.
- Prefer null over hallucinated values.
- Keep all stage I/O typed and explicit.

---

## Shared Engineering Expectations

- Build against the shared model package only. Do not invent ad hoc payloads.
- Preserve stage boundaries. Do not silently absorb neighboring-stage responsibilities.
- Keep functions modular and inspectable.
- Add lightweight tests for your stage.
- If you need to make a small assumption, document it in code comments or a short note.
- Do not rewrite shared schemas unless you are the contract owner or explicitly coordinating through one owner.

---

## Shared Contract Assumptions

All agents should assume there is a shared package containing:

- request/response models
- stage input/output models
- evidence/provenance models
- evidence store model
- SSE event models
- error models

If a needed field is missing from the shared contracts, do not invent a private alternative shape. Raise it explicitly or add it through the shared package.

---

## Practical Implementation Stance

- Optimize for reliability and debuggability over cleverness.
- Avoid overengineering.
- Keep prompt outputs structured and parseable.
- Keep side effects localized.
- Expect Agent 5 to be the bottleneck; do not create extra downstream dependency on it beyond the agreed contracts.

---

## Agent 1 — Contracts + Controller Skeleton + App Shell

### Your Job

Own the shared contracts and the app/controller skeleton that unblock all other agents.

### You Own

- shared typed models
- enums/constants
- stage I/O contracts
- SSE event schema
- error schema
- controller skeleton
- FastAPI shell
- minimal seed fixtures

### Deliverables

- shared model package
- short stage-contract doc
- controller skeleton with full stage order, repair gating, budget tracker, evidence store structure
- API shell
- SSE shell
- minimal seed fixtures sufficient to unblock others

### Important Constraints

- Your main goal is to freeze contracts early, not to finish the whole system.
- Do not block the whole team on rich fixtures.
- Provide only the minimal fixtures needed to align interfaces.
- Do not implement real stage logic beyond placeholders/interfaces.

### Must Define Clearly

- canonical `EvidenceItem`
- canonical `FieldValue`
- canonical `EvidenceStore` structure: `entity_name → List[EvidenceChunk]`
- `EvidenceChunk` with fields: `text`, `source_url`, `source_role`, `source_quality`, `officiality`, `from` (`brave_llm` | `jina`), `aspect_coverage`
- Evidence store attribution policy:
  - primary attribution: ExtractorLight name → URL mapping
  - fallback: conservative string name matching within chunk text
  - ambiguous chunks that match multiple entity names should remain attached to all matching entities until Extractor resolves them
  - do not drop ambiguous chunks during evidence store construction
  - over-eager attribution is worse than multi-attachment
- final response shape
- repair diagnostics shape
- SSE event names and payload structure
- typed failure/error structure
- `SourceRole` enum: `discovery` / `verification` / `corroboration`
- `SourceQuality` enum: `high` / `medium` / `low`
- `Officiality` enum: `official` / `near-official` / `third-party` / `low-quality`

### Full Pipeline Stage Order the Controller Must Implement

1. Planner
2. Searcher
3. Brave LLM Context — first pass (on bounded shortlist)
4. ExtractorLight
5. Assessor — first pass
6. Targeted verification queries (bounded, max 5–7)
7. Brave LLM Context — second pass (verification URLs only)
8. Assessor — light second pass (verification URLs only)
9. Controller builds/merges evidence store
10. Assessor decides Jina fetches
11. Extractor
12. Canonicalizer+Verifier+Evaluator
13. Optional single repair round
14. Return final result

### Minimal Fixture Requirement

Provide:

- one representative seed query fixture
- one example planner output
- one example evidence store snapshot
- one example final response shape
- one example SSE lifecycle

### Anti-Goals

- no real planner/search/extractor logic
- no frontend implementation
- no rich end-to-end simulation

---

## Agent 2 — Planner + Searcher

### Your Job

Implement the planning stage and the deterministic retrieval execution stage.

### You Own

**Planner:**

- topic-query check and conservative normalization
- entity type inference
- schema generation (5–7 columns)
- aspect generation (2–5 aspects)
- base query generation
- initial rewrite generation (0–3 rewrites)

**Searcher:**

- Brave Web Search execution
- result collection with metadata (title, snippet, domain, rank, query source)
- mechanical URL pruning (see rules below)
- exact URL deduplication across query result lists
- multi-query result merge by rank (simple: keep URL at best rank position across lists)
- hard cap at top 12–15 URLs after pruning and dedup
- early retry fallback if result pool is clearly weak

### Inputs You Consume

From shared contracts:

- raw request
- normalization-related models
- planner output models
- search result models

### Outputs You Produce

- `PlannerOutput`
- `SearchResultItem[]`
- `ShortlistedUrl[]` (pruned, deduped, rank-merged, capped at 12–15)

### Mechanical Pruning Rules (implemented in code, no LLM)

Drop URLs matching any of:

- exact duplicate URLs across query results (keep at best rank position)
- social media post URLs (`twitter.com/status/`, `facebook.com/posts/`, `instagram.com/p/`) — note: `linkedin.com/company/` pages are kept
- video URLs (`youtube.com`, `vimeo.com`)
- file extension URLs (`.pdf`, `.ppt`, `.doc` in URL string)
- snippets that are clearly navigation/boilerplate ("sign in to continue", "page not found", "click here")
- results with empty snippets
- results with zero keyword overlap with query AND zero keyword overlap with any planner aspect

### Hard Rules

- Planner owns all semantic initial rewrites.
- Searcher must not generate semantic rewrites on its own.
- Searcher must not decide deep fetch.
- Normalization must be conservative.
- If the query requires strong reinterpretation, return planner error rather than guessing aggressively.
- Domain-level deduplication is forbidden — different pages on the same domain (Wikipedia, Arxiv, Crunchbase) are distinct and must not be collapsed.

### Implementation Priorities

1. Planner structured output
2. Brave integration
3. mechanical pruning
4. dedupe and rank-merge logic
5. shortlist builder with hard cap
6. early retry fallback
7. tests

### Anti-Goals

- no deep fetch decisions
- no extraction
- no ranking
- no repair-time query generation
- no domain-level deduplication

---

## Agent 3 — Assessor + Brave LLM Context + Jina Fetcher

### Your Job

Implement the hybrid assessment stage: Brave LLM Context acquisition, heuristic pre-signals, batched semantic assessment, per-entity verification gap detection, and selective Jina deep fetch.

### You Own

- Brave LLM Context calls (first pass on shortlist, second pass on verification URLs)
- heuristic pre-signals (computed in code)
- batched LLM assessment prompt and parser
- source role classification (`discovery` / `verification` / `corroboration`)
- source quality and officiality assessment
- per-entity verification gap detection using ExtractorLight name→URL map
- verification query suggestions for flagged entities, bounded to 5–7 queries total across the entire request — batching multiple flagged entities into a single query is allowed and preferred over issuing one query per entity; prioritize by mention count from ExtractorLight when the cap forces selection
- Jina fetch decisions over full evidence store
- Jina Reader integration
- in-memory chunking for large fetched pages
- fetch failure handling

### Inputs You Consume

- `ShortlistedUrl[]` from Searcher
- titles, snippets, ranks, source metadata
- planner aspects, schema, query context
- candidate name list and name→URL map from ExtractorLight
- evidence store (for Jina fetch decision pass)

### Outputs You Produce

- Brave LLM Context passages per URL (first and second pass)
- `UrlHeuristicSignals` per URL
- `UrlAssessment` per URL (source role, quality, officiality, aspect coverage, evidence sufficiency)
- list of flagged entities needing verification queries + suggested query per entity
- `FetchedDocument[]` from Jina
- `DocumentChunk[]` for large pages

### Hard Rules

- This stage is hybrid: heuristics in code, one batched LLM assessment per pass.
- Brave LLM Context is run only on the bounded shortlist, not on all Brave results.
- Source role classification happens here, not in ExtractorLight or Extractor.
- Verification gap detection requires the candidate name list from ExtractorLight — do not run this before ExtractorLight has produced output.
- Verification queries are bounded to max 5–7 regardless of how many entities are flagged — prioritize by mention count from ExtractorLight.
- Jina fetch decisions are made over the full evidence store after it is built by the Controller — not per-URL in isolation.
- Do not extract entities here.
- Do not rank final rows here.
- No persistent index or vector DB.
- Do not implement a one-query-per-entity loop for verification queries. Batch flagged entities into as few queries as possible while staying within the 5–7 cap.

### Implementation Priorities

1. Brave LLM Context integration
2. heuristic pre-signals
3. batched assessment prompt and parser
4. source role classification
5. per-entity verification gap detection
6. verification query suggestion (bounded)
7. Jina fetch decision logic
8. Jina integration
9. in-memory chunking
10. tests with mocked shortlisted URLs

### Anti-Goals

- no entity extraction
- no canonicalization
- no repair gating
- no evidence store construction (that belongs to Controller)

---

## Agent 4 — ExtractorLight + Extractor

### Your Job

Implement two distinct extraction components: a lightweight name extractor and a full structured extractor.

### You Own

**ExtractorLight (`extractors/light.py`):**

- one LLM call over aggregated Brave LLM Context output
- candidate entity name extraction
- name → source URL mention mapping
- coarse mention count per name

**Extractor (`extractors/full.py`):**

- full structured extraction over evidence store slices
- dynamic schema handling
- provenance-first field building
- field contradiction resolution using source role priority
- provisional candidate generation
- minimum provisional candidate filtering

### Inputs You Consume

**ExtractorLight:**

- Brave LLM Context passages (aggregated across all shortlisted URLs)
- `entity_type` from Planner

**Extractor:**

- evidence store slice per entity (Brave LLM Context chunks + Jina chunks, role/quality tagged)
- candidate name list from ExtractorLight (used as prior)
- schema and core aspects from Planner

### Outputs You Produce

**ExtractorLight:**

- flat candidate name list
- `name → [source_urls]` mention map
- coarse mention count per name

**Extractor:**

- `ProvisionalEntityCandidate[]` with full field-level provenance

### Hard Rules

**ExtractorLight:**

- outputs names only — no fields, no schema, no provenance
- does not resolve duplicates or aliases
- does not score or filter entities
- one LLM call over aggregated input, not per-URL

**Extractor:**

- every meaningful field must be a structured `FieldValue` object, not a plain string
- provenance must be attached from day one
- unsupported values become null
- preserve conflicting values for Canonicalizer resolution
- use source role priority for contradiction resolution: `verification` > `corroboration` > `discovery`
- treat candidate name list as a prior: add new entities freely, only remove/contradict existing names if evidence is strongly contradicting
- support planner-provided dynamic schema

### Field Contradiction Resolution Priority

1. verification-role source
2. independent corroboration
3. discovery source

### Implementation Priorities

1. ExtractorLight: name extraction + URL mapping
2. Extractor: field/evidence model handling
3. Extractor: extraction over evidence store slices
4. Extractor: provisional filtering
5. tests against dynamic schema cases
6. tests for contradiction resolution

### Anti-Goals

- no source role classification (that belongs to Assessor)
- no Jina fetch decisions (that belongs to Assessor)
- no deduplication (that belongs to Canonicalizer)
- no final field resolution (that belongs to Canonicalizer+Verifier)
- no final ranking
- no repair logic
- ExtractorLight must not become a semi-extraction stage

---

## Agent 5 — Canonicalizer + Verifier + Evaluator

### Your Job

Implement the heaviest stage: merge, resolve, filter, rank, diversify, and emit repair diagnostics.

### You Own

- duplicate merging
- alias handling
- field verification and resolution
- eligibility filtering
- evidence strength scoring (0/1/2/3 rubric)
- aspect coverage calculation
- MMR diversified top-10 selection
- repair diagnostics
- suggested follow-up queries

### Inputs You Consume

- `ProvisionalEntityCandidate[]` from Extractor with full field-level evidence
- planner aspects and schema
- source role and quality metadata already attached to evidence items

### Outputs You Produce

- canonical final entity rows
- ranking and selection results
- `RepairDiagnostics` with `suggested_followup_queries`

### Internal Structure

**5A — Canonicalization + Verification:**

- merge duplicates using cheap signals first (normalized name, domain match, official-domain alignment, local address match)
- resolve aliases
- use inline targeted LLM only for hard ambiguous merges — not as a default step
- choose field values using agreed priority: `verification source` > `independent corroboration` > `discovery source`
- reduce confidence or null out unresolved fields

**5B — Eligibility + Ranking + Repair Diagnostics:**

- enforce eligibility gate before ranking
- compute `evidence_strength`:
  - `3` = verification source + at least 2 supported core fields
  - `2` = at least 2 independent non-verification supports + at least 2 supported core fields
  - `1` = minimum acceptable support
  - `0` = ineligible
- compute `aspect_coverage`: count of planner aspects covered with actual evidence
- order by `evidence_strength`, break ties with `aspect_coverage`
- apply greedy MMR diversified selection for final top-10
- emit structured `RepairDiagnostics` including `suggested_followup_queries`

### Eligibility Rules

An entity is eligible if at least one is true:

- one verification-role source supports identity plus at least one more core field
- two independent non-verification sources support the entity with strong evidence
- completeness and evidence quality exceed defined threshold

Absence of a verification-role source is not an automatic hard fail — it reduces `evidence_strength` score instead.

### Repair Diagnostic Output Fields

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

### Hard Rules

- Do not use a weighted-sum ranker.
- Use the staged ranking policy above.
- This stage proposes repair follow-up queries — it does not decide whether repair runs.
- Keep outputs typed and explicit.
- Do not merge aggressively on low-confidence signals — keep candidates separate if uncertain.

### Implementation Priorities

1. canonicalization (cheap signals first)
2. verification and field resolution
3. eligibility filtering
4. evidence strength scoring
5. MMR selection
6. repair diagnostics
7. tests

### Anti-Goals

- no controller budget management
- no actual repair execution
- no SSE handling
- no Jina fetch decisions

---

## Agent 6 — Frontend

### Your Job

Build the UI against frozen response shapes and SSE event schemas.

### You Own

- search form
- SSE client integration
- loading and progress states
- final results table
- provenance rendering per cell
- evidence inspector drawer (shown on cell click)
- normalization banner (shown when query was lightly converted)
- clean error states (including planner hard error)

### Inputs You Consume

- final response schema
- SSE event schema
- error schema

### Outputs You Produce

- working frontend pages and components wired to agreed API and SSE contracts

### Hard Rules

- Do not infer undocumented backend fields.
- Do not reconstruct provenance shape client-side.
- Do not implement business logic already owned by backend stages.
- Render normalization notes and planner errors cleanly.
- SSE progress events should map to named pipeline stages from the controller stage order.

### Implementation Priorities

1. UI shell
2. SSE wiring and progress display
3. table rendering with provenance
4. evidence inspector drawer
5. normalization banner
6. error and loading polish

### Anti-Goals

- no ranking logic
- no query rewriting
- no provenance schema invention

---

## Agent 7 — Integration + E2E Testing

### Your Job

Wire the stage implementations together, validate handoffs, expand fixtures where useful, and run end-to-end tests.

### You Own

- controller-stage wiring for full 14-step pipeline
- evidence store construction and merging validation
- interface validation at every stage boundary
- richer fixtures built incrementally
- end-to-end request lifecycle tests
- repair-path tests
- normalization-path tests
- failure-path tests
- smoke tests on real queries

### Inputs You Consume

- all stage implementations
- shared contracts
- seed fixtures
- frontend/backend API contracts

### Outputs You Produce

- integrated working pipeline
- fixture-backed tests
- end-to-end smoke test results
- identified contract mismatches and fixes

### Hard Rules

- Do not patch incompatible outputs with ad hoc transforms unless absolutely necessary.
- Prefer fixing contract mismatches at the owning stage.
- Repair must be exercised at least once in testing.
- Normalization must be exercised at least once in testing.
- Failure path must be exercised at least once in testing.
- Verification gap detection and targeted verification query path must be exercised at least once.
- Evidence store construction must be validated before Extractor tests run.

### Implementation Priorities

1. stage wiring in correct controller order
2. evidence store construction validation
3. happy-path run
4. repair-path run
5. normalization-path run
6. verification-gap-path run
7. failure-path run
8. frontend/backend flow validation

### Anti-Goals

- no redesign of stage ownership
- no silent schema drift
- no changing search/rewrite ownership boundaries
- no domain-level URL deduplication

---

## Short Note to Prepend to Every Local Agent Prompt

You are implementing only your assigned stage/module. The challenge description and the business/design flow are provided separately. Follow the shared contracts exactly. Do not absorb neighboring-stage responsibilities. If something is missing from the contracts, raise it explicitly instead of inventing a private format.