# Agent Context

This is the active implementation context for the current reduced pipeline.

The `north_star_*` docs remain as the broader historical design reference. They are useful for future direction, but they are not the source of truth for current scope.

---

## Global Context for All Agents

You are implementing one stage of a bounded, deterministic multi-stage system. The challenge description and the active business/design flow are provided separately. Follow the active docs as the source of truth for current behavior, contracts, and ownership.

---

## Non-Negotiable Global Rules

- The system uses a deterministic orchestrator in code, not an LLM orchestrator.
- There is no open-ended loop, no recursive orchestration, and no free-form agent-to-agent calling.
- Provenance is part of the field model, not optional metadata.
- Do not implement a weighted-sum final ranker.
- Planner owns the initial semantic query generation including all initial rewrites.
- Searcher only executes queries and builds result pools; it does not generate semantic rewrites.
- Brave LLM Context is run only on the bounded pruned shortlist, not on all returned URLs.
- ExtractorLight produces candidate names and a name→URL mention map only; no fields, no schema decisions, no ranking.
- Assessor currently owns source triage only.
- Extractor consumes the evidence store; it does not decide what to fetch.
- Orchestrator owns evidence store construction and merging.
- Query normalization is only a small guardrail, not a major subsystem.
- Prefer null over hallucinated values.
- Keep all stage I/O typed and explicit.

---

## Active Pipeline Order

1. Planner
2. Searcher
3. Brave LLM Context on bounded shortlist
4. ExtractorLight
5. Assessor first pass
6. Evidence store build
7. Extractor
8. Final row selection / response

---

## Explicitly Out of Scope for the Active Flow

- no verification-query sub-pass
- no Brave second pass
- no Jina selection in the active orchestrated flow
- no repair round
- no post-extraction replanning

These ideas may remain in the north-star docs, but they are not current implementation scope.

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

- optimize for reliability and debuggability over cleverness
- avoid overengineering
- keep prompt outputs structured and parseable
- keep side effects localized
- prefer explicit bounded behavior over flexible but ambiguous architecture

---

## Active Stage Ownership

### Planner

Owns:

- topic-query check and conservative normalization
- entity type inference
- schema generation
- aspect generation
- base query generation
- initial rewrite generation

Does not own:

- retrieval execution
- source triage
- evidence merging
- extraction

### Searcher

Owns:

- Brave Web Search execution
- result collection with metadata
- mechanical URL pruning
- exact URL deduplication
- multi-query merge
- shortlist construction

Does not own:

- semantic rewrite generation
- deep-fetch decisions
- extraction
- final ranking

### Brave LLM Context Helper

Owns:

- shortlist-only Brave context calls
- exact-URL-only passage attachment
- snippet fallback when Brave does not return an exact-URL passage
- deterministic line-level cleanup of passage text

Does not own:

- full-page retrieval
- entity extraction
- source triage

### ExtractorLight

Owns:

- candidate name extraction only
- `name -> source URLs` mention mapping
- mention counts

Does not own:

- field extraction
- canonicalization
- row ranking
- final eligibility decisions

### Assessor

Owns:

- heuristic source signals
- batched semantic source assessment
- `source_role`
- `source_quality`
- `officiality`
- rough aspect coverage
- evidence sufficiency

Does not own in the active flow:

- verification-gap generation
- verification-query planning
- Jina fetch selection
- second-pass reassessment
- repair decisions

### Evidence Store Builder

Owns:

- entity-centric evidence-store construction and merging
- evidence attribution using name-to-URL mapping first
- conservative string-matching fallback
- provenance carry-through

Important attribution policy:

- primary attribution: ExtractorLight name → URL mapping
- fallback: conservative string matching within chunk text
- ambiguous chunks that match multiple entity names should remain attached to all matching entities until Extractor resolves them
- do not drop ambiguous chunks during evidence store construction
- over-eager attribution is worse than multi-attachment

### Extractor

Owns:

- structured candidate extraction from evidence
- field-level provenance
- conservative contradiction handling
- null-default behavior for unsupported values

Does not own:

- retrieval
- source triage
- evidence-store construction

### Final Row Selection / Response

Owns:

- candidate filtering
- row eligibility decisions
- final row selection
- response assembly

Does not own:

- retrieval
- source triage
- evidence-store building

---

## Implementation Priorities by Risk

1. keep contracts stable
2. keep source attribution traceable
3. keep stage boundaries strict
4. keep deterministic parts deterministic
5. use LLMs only where they materially improve semantic judgment

---

## Anti-Goals

- no hidden stage coupling
- no private payload shapes that bypass shared contracts
- no speculative extraction unsupported by evidence
- no uncontrolled query expansion
- no partial implementation of descoped verification or repair features inside active stages
