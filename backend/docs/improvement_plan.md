# Improvement Plan

## Purpose

This document is the forward-looking implementation plan for improving the current agentic search pipeline.

It has two goals:

- define the smallest set of changes needed to make the project demoable and credible on a CV
- capture the larger future migration path so later agents can continue work without re-deriving design decisions

This doc is intentionally more detailed than a TODO list, but it stops short of low-level implementation instructions that should be inferred from the codebase.

---

## Current State Summary

The current active pipeline is still centered around:

1. Planner
2. Searcher
3. Brave LLM Context retrieval
4. ExtractorLight
5. Assessor
6. Evidence Store Builder
7. Extractor
8. Finalizer

Recent improvements already made:

- extractor is now parallelized with bounded concurrency and is much faster
- assessor has a heuristic layer and assessor-stage SSE visibility
- assessor logic has been modularized under `backend/app/stages/assessor/`

Current observed issues:

- assessor still costs too much latency relative to the value it provides
- heuristics are currently too weak to form a meaningful funnel
- many final rows are sparse or fully empty
- some extracted candidate names are wrong for the target entity type
- the system likely over-optimizes breadth and under-serves evidence depth
- Brave LLM Context is expensive and is not a strong long-term retrieval layer

---

## Demo / CV Cut-Off

Everything above this line is required for a strong demo and a credible CV project.
Everything below this line is valuable future work, but not required before showing the system.

### Demo / CV Required

The following work is the minimum recommended scope before considering the project demo-ready:

1. Decide the assessor path for the demo:
   - either tighten it and make it heuristics-only
   - or remove/bypass it from the active demo path
2. Add deterministic final-row pruning.
3. Do a light candidate-quality pass in `ExtractorLight` to reduce obviously wrong candidates.
4. Keep extractor parallelism and current SSE observability.
5. Make sure a few representative demo queries produce coherent top results with acceptable latency.

In practice, the only meaningful remaining demo tasks are:

- assessor simplification or removal
- final row pruning
- a modest `ExtractorLight` precision improvement

Everything else in this document is future work unless one of those three tasks reveals a blocker.

### Demo / CV Not Required

The following can be deferred:

- Jina migration
- schema-specific retrieval depth passes
- Redis/global queue scaling
- large architecture changes for production traffic
- optional LLM source-scoring fallback after migration
- broad searcher redesign

If time is limited, prioritize the required section only.

---

## Phase 1: Demo / CV Priorities

### Practical Demo Scope

If the immediate goal is only to get the project to a demoable and CV-ready state, stop after completing these three work items:

1. assessor simplification or bypass
2. final row pruning
3. light `ExtractorLight` candidate-quality improvement

That is the intended demo cutoff.

Do not treat the Jina migration, schema-depth enrichment, or production scaling work as required before the project is showable.

### Agent Ownership For Demo Scope

Assign all demo-cutoff work to `Agent 0`.

`Agent 0` owns:

1. assessor simplification or bypass
2. final row pruning
3. light `ExtractorLight` candidate-quality improvement
4. final demo-query validation and sanity checks

Reasoning:

- these three tasks directly affect visible output quality and latency
- they are tightly coupled enough that one agent should own the demo bar end-to-end
- they determine whether the rest of the roadmap even matters for near-term presentation

### 1. Assessor Decision

#### Problem

The current assessor stage still takes too long and does not filter enough sources to justify its latency.

Observed pattern:

- many sources survive heuristics
- many sources are still sent to the LLM
- the LLM removes very few additional sources

#### Goal

Make the assessor cheap enough to keep, or remove it from the critical path for the demo path.

#### Recommended Direction

Short-term recommendation:

- prefer either:
  - heuristics-only assessor
  - or a much tighter heuristic funnel with little or no LLM fallback

Do not invest further in heavy LLM source triage before proving it materially improves output quality.

#### Candidate Tasks

- tighten obvious junk-source filtering
- review the treatment of Reddit, Quora, social, forums, weak directories, and fallback-only pages
- measure whether heuristics-only output quality is acceptable
- if quality holds, remove LLM assessor from the active demo path

#### Success Criteria

- assessor latency is no longer a dominant bottleneck
- obvious junk sources do not survive to evidence
- SSE metrics show a meaningful heuristic funnel if the stage remains

---

### 2. Final Row Pruning

#### Problem

Some final entities are clearly bad:

- fully empty rows
- rows with a name only and no grounded non-name fields
- rows supported by almost no meaningful evidence

These make the product look unfinished even if the underlying retrieval is reasonable.

#### Goal

Add a deterministic cleanup pass that removes obviously failed rows before final output.

#### Recommended Direction

Add row-pruning logic after extraction and before final user-facing output.

The cleanup should be deterministic and conservative.

#### Candidate Rules

- drop rows where all fields are null
- consider dropping rows where only `name` is present and all other fields are null
- consider requiring at least one grounded non-name field for final inclusion
- preserve provenance-aware rows even if sparse, but do not keep total failures

#### Success Criteria

- no fully empty rows reach the UI
- obviously broken rows are removed without hurting reasonable sparse rows

---

### 3. Candidate Precision in ExtractorLight

#### Problem

Some candidate names are not valid instances of the target entity type.

Examples of failure modes:

- dish names for restaurant queries
- category phrases instead of actual entities
- generic terms or variants that are not the intended entity class

This creates downstream waste and lowers extraction quality.

#### Goal

Make candidate extraction more entity-type-aware and reduce clearly invalid candidates.

#### Recommended Direction

Improve both:

- prompt-side entity-type guidance
- deterministic post-filtering of candidate names

`ExtractorLight` should not ask only "what names appear here?" It should ask "which names are plausible instances of the planner-defined entity type?"

#### Candidate Tasks

- strengthen prompt constraints around entity type
- add post-filters for generic phrases and obviously non-entity mentions
- add query-class-specific validation logic where cheap and reliable

#### Success Criteria

- fewer invalid candidates enter the evidence store
- fewer final rows are later pruned as empty or incorrect

---

### 4. Demo Query Curation and UX Visibility

#### Problem

Even a good system can look weak if shown on poor example queries or without enough pipeline visibility.

#### Goal

Make the demo stable and easy to explain.

#### Recommended Direction

- maintain a shortlist of representative demo queries that perform well
- use SSE breakdowns to explain pipeline behavior
- ensure sparse-result behavior is clear and graceful

#### Candidate Tasks

- choose 3-5 demo queries across different domains
- verify they return coherent outputs with acceptable latency
- optionally show assessor/extractor metrics in the UI more clearly

#### Success Criteria

- demo queries are stable enough for presentation
- a reviewer can understand what the system is doing and why

---

## Phase 2: Retrieval Migration (Future)

This phase is not required before demo/CV readiness, but it is the most important architectural next step after the demo bar is met.

### Migration Objective

Replace the Brave LLM Context-centered retrieval path with a:

- Brave search
- heuristic prefetch triage
- Jina full-page retrieval
- chunk-first evidence pipeline

### Desired End State

Brave should remain the web search layer.

Jina should become the bounded page-text retrieval layer.

Chunk-level heuristics should become the main evidence gate.

Source assessment should be heuristic and based on real retrieved text rather than expensive semantic source scoring over shallow context.

### Recommended Target Flow

1. Planner
2. Searcher
3. Pre-fetch source triage
4. Jina retrieval
5. Source chunking with provenance
6. Pre-entity chunk filtering/ranking
7. ExtractorLight over filtered chunks
8. Post-entity chunk filtering/ranking
9. Post-fetch source assessment
10. Evidence store construction from surviving chunks
11. Extractor
12. Finalizer

Important migration statement:

- after migration, candidate extraction should operate on filtered Jina-derived chunks, not on Brave LLM Context passages
- Brave remains the search layer only, not the candidate-extraction text source

### Key Design Decisions

- Brave remains the search provider
- Brave LLM Context is removed from the active runtime path
- Jina is the page retrieval layer
- source scoring is heuristic-first and preferably heuristic-only
- retrieval quality is split into:
  - source promise before fetch
  - source usefulness after fetch
- chunk filtering is the primary quality gate

### Important Constraints

- keep fetches bounded
- keep provenance first-class
- keep downstream stages mostly intact where possible
- do not reintroduce vendor-specific naming deep into the contracts
- do not let provider-neutral contracts turn into a large abstraction exercise; keep them minimal and practical

---

## Assessor Redesign for the Future Retrieval Path

The current single assessor concept should eventually be split into two deterministic components.

### 1. PreFetchSourceAssessor

Purpose:

- decide which URLs are worth spending Jina budget on

Inputs:

- URL
- domain
- path
- title
- search snippet
- rank
- query overlap
- planner aspects

Outputs:

- fetch-priority score
- keep/drop for Jina fetch budget
- officiality/source-type hints

This is not final source quality.

Important warning:

- pre-fetch triage is for fetch priority and bounded retrieval selection only
- it must not be treated as the final source judgment for evidence quality

### 2. PostFetchSourceAssessor

Purpose:

- evaluate source usefulness after chunk filtering

Inputs:

- surviving chunks
- chunk counts
- chunk scores
- aspect coverage
- candidate/entity support
- officiality/source-type hints

Outputs:

- final keep/drop for evidence construction
- final officiality
- final source role
- source usefulness

This should be heuristic-only by default.

### Migration Principle

Do not carry the current LLM-heavy source assessment model into the Jina-based design by default.

If an LLM source-scoring fallback is ever reintroduced, it should only handle a narrow borderline subset after benchmarking proves it is necessary.

---

## Chunk-Centric Retrieval Plan

### Pre-Entity Chunk Filtering

Purpose:

- remove obvious garbage before candidate extraction

Signals should include:

- overlap with normalized query
- overlap with planner aspects
- overlap with rewrite intent if available
- title-to-chunk consistency
- official-domain boosts
- factual or descriptive density
- penalties for boilerplate, legal, nav, thin, or generic marketing text

Important constraint:

- this pass must remain recall-oriented
- it should reduce noise, not collapse discovery breadth
- it must not depend on candidate/entity mentions yet, because candidate extraction has not happened and doing so would create circular logic

### Post-Entity Chunk Filtering

Purpose:

- improve precision after candidate extraction exists

Signals should include:

- candidate-entity mentions
- local evidence density around candidate mentions
- support for planner aspects
- per-source and per-candidate diversity constraints

Important constraint:

- one verbose page must not crowd out all other evidence
- apply deterministic per-source caps after chunk ranking so one long page cannot dominate the evidence pool

### Evidence Store Construction

Only filtered surviving chunks should be eligible for evidence-store construction.

Snippet fallbacks for failed retrievals are acceptable for graceful degradation, but they should be treated as weak evidence and should not silently carry the same weight as full-page retrieved text.

---

## Schema Depth Problem

### Problem

Many cells remain empty, which suggests the system is discovering entities more broadly than it is gathering the depth needed to fill the schema.

### Important Decision

Do not solve this with naive per-entity, per-column retrieval by default.

That approach is likely too expensive and too slow.

### Recommended Direction

Use selective depth only later, and only for:

- top-ranked entities
- important missing columns
- cases where current evidence is clearly insufficient

This should be treated as a future enhancement, not a demo prerequisite.

---

## Evaluation Plan

For the current phase of the project, manual evaluation is sufficient.

Do not build a large benchmarking framework yet.

### Recommended Manual Evaluation Approach

Use a fixed set of representative demo queries and compare before/after behavior on each meaningful pipeline change.

Track:

- latency before/after
- row quality before/after
- chunk survival counts
- source survival counts
- obvious failure modes such as empty rows, wrong entity types, or weak provenance

### Minimum Evaluation Set

- a small fixed query set used repeatedly
- manually reviewed final rows
- manually reviewed latency changes
- simple pipeline metrics from SSE/logging

### Why This Is Enough For Now

- the project is still in a demo/CV-readiness phase
- manual evaluation with a fixed query set is fast enough to guide decisions
- formal large-scale benchmarking can wait until the retrieval architecture stabilizes

---

## Parallelizable Workstreams

The following workstreams are designed so multiple coding agents can work in parallel with limited overlap.

### Agent 0: Demo Path Cleanup

Scope:

- row pruning
- sparse-row removal
- finalizer/output cleanup
- assessor simplification or bypass
- light `ExtractorLight` candidate-quality improvement
- demo query validation

Dependencies:

- minimal

Priority:

- highest
- complete this first if the goal is to ship a demo

### Agent 1: Retrieval Contract Cleanup

Scope:

- provider-neutral retrieval contracts
- naming cleanup away from Brave-specific context models
- minimal interfaces that allow future Jina migration

Dependencies:

- should not disrupt the demo path

Can run in parallel with:

- Agent 2
- Agent 3
- Agent 4

### Agent 2: Jina Migration Prep and Fetch Path

Scope:

- Jina fetch integration
- bounded fetch orchestration
- snippet fallback rules
- migration of retrieval flow away from Brave LLM Context

Dependencies:

- Agent 1 preferred first for cleaner contracts, but not strictly required if carefully scoped

Can run in parallel with:

- Agent 3
- Agent 4

### Agent 3: Chunk Filtering and Post-Fetch Source Assessment

Scope:

- pre-entity chunk filtering/ranking
- post-entity chunk filtering/ranking
- post-fetch source assessment
- per-source caps and chunk diversity rules

Dependencies:

- can start from the migration design immediately
- integrates best once Agent 2 has a stable fetched-text shape

Can run in parallel with:

- Agent 1
- Agent 2
- Agent 4

### Agent 4: Selective Depth and Future Enrichment

Scope:

- selective depth for top entities only
- schema-fill improvement strategy
- future targeted enrichment design

Dependencies:

- should not alter the active demo path prematurely
- should happen after the demo cutoff is met

Can run in parallel with:

- Agent 1
- Agent 3

---

## Recommended Execution Order

If one agent is doing everything:

1. simplify or bypass assessor
2. add final row pruning
3. improve candidate precision
4. stabilize demo queries and latency
5. then revisit migration

If multiple agents are available:

1. Agent 0: complete the demo cutoff
2. Agent 1: retrieval-contract cleanup
3. Agent 2: Jina migration fetch path
4. Agent 3: chunk filtering and post-fetch source assessment
5. Agent 4: selective depth and future enrichment

Important coordination rule:

- Agent 0 should not be blocked by the migration agents
- Agents 1-4 should treat the demo path as stable unless `Agent 0` explicitly requests shared refactors

---

## What Not To Do Next

Do not spend the next round on:

- Redis/global queue/scaling architecture
- production traffic concerns
- SerpApi/Tavily integrations
- broad searcher redesign
- expensive schema-specific retrieval for every entity/column
- adding new LLM-heavy stages without strong evidence they help

These may become useful later, but they are not the highest-leverage next steps for demo quality.

---

## Completion Criteria by Horizon

### Demo / CV Ready

- latency is acceptable for a live demo
- obviously empty/bad rows are pruned
- wrong entity names are reduced
- the system can answer several representative demo queries coherently
- SSE/debug visibility is enough to explain what the pipeline is doing

### Next Architecture Milestone

- Brave LLM Context is removed from the active path
- retrieval contracts are provider-neutral
- Jina fetch plus chunk filtering becomes the main evidence path
- source assessment is heuristic and text-grounded

### Longer-Term Quality Milestone

- selective depth improves sparse fields for top entities
- evidence quality improves without exploding latency
- source usefulness is determined primarily from real retrieved content
