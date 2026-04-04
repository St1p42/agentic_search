# Stage Contracts

This document only records ownership and typed I/O boundaries. The business flow and challenge description remain the source of truth for behavior.

## Planner

Input:
- `PipelineRequest.query`

Output:
- `PlannerOutput`

Ownership:
- Infers `entity_type`, `schema_columns`, `core_aspects`, `base_query`, and `initial_query_rewrites`
- Performs only conservative query normalization
- Never asks the user for clarification at runtime
- May reject the query by setting `error=true`
- Typical shape: `schema_columns` has 4-6 entries and always includes `name`; `core_aspects` has 1-5 entries

## Searcher

Input:
- `PlannerOutput`
- Optional repair-time follow-up queries from the final stage

Output:
- `SearcherOutput`

Ownership:
- Executes supplied queries
- Applies mechanical URL pruning, exact-URL deduplication, multi-query rank merging, query-source tie-breaking, soft round-robin rewrite-slot reservation to avoid over-bias toward the base query first, and a small per-domain shortlist cap
- Returns Brave result metadata needed downstream, including domain, rank, query source, and provider metadata
- Does not generate new semantic queries

## ExtractorLight

Input:
- `PlannerOutput.entity_type`
- `BraveContextOutput`

Output:
- `ExtractorLightOutput`

Ownership:
- Extracts candidate names only
- Builds `name -> source URLs` mention mapping and coarse mention counts
- Does not extract fields, resolve aliases, score rows, or make eligibility decisions

## Assessor

Input:
- `PlannerOutput`
- `SearcherOutput`
- `BraveContextOutput`
- `ExtractorLightOutput`
- Optional existing `EvidenceStore`
- Remaining Jina fetch budget

Output:
- `AssessorOutput`

Ownership:
- Computes heuristic source signals
- Carries Brave LLM Context passages as shallow evidence
- Performs batched semantic source assessment
- Classifies `source_role`, `source_quality`, and `officiality`
- Flags entities needing verification queries
- Supports `FIRST_PASS`, `VERIFICATION_PASS`, and `JINA_SELECTION` pass types through one shared contract
- Selects Jina deep-fetch URLs from the evidence store

## Extractor

Input:
- `PlannerOutput`
- `ExtractorLightOutput`
- `EvidenceStore`
- Optional prior `ExtractorOutput` for repair-time enrichment

Output:
- `ExtractorOutput`

Ownership:
- Produces structured candidate entities from entity-centric evidence chunks
- Stores field-level provenance through `FieldValue.evidence`
- Resolves contradictions by source-role priority where possible
- Prefers null over unsupported values
- May add new entities if evidence reveals them

## Canonicalizer+Verifier+Evaluator

Input:
- `PlannerOutput`
- `ExtractorOutput`

Output:
- `CanonicalizerVerifierEvaluatorOutput`

Ownership:
- Merges duplicate candidates
- Resolves supported field values
- Applies eligibility filtering
- Ranks without weighted-sum scoring
- Selects final diversified rows
- Emits `RepairDiagnostics` and suggested follow-up queries

## Orchestrator

Input:
- `PipelineRequest`

Output:
- `PipelineResponse` with `inferred_schema` and `final_top_10_rows`

Ownership:
- Runs the fixed stage order
- Tracks search/fetch/repair budgets in `BudgetState`
- Owns entity-centric evidence store construction and merging
- Executes one bounded verification-query sub-pass inside the first retrieval pass
- Decides whether the single repair round is allowed
- Emits SSE lifecycle events using `SseEvent`

## Orchestrator Helpers

### Brave LLM Context

Input:
- `SearcherOutput.shortlisted_results`

Output:
- `BraveContextOutput`

Ownership:
- Fetches URL-linked Brave LLM Context passages for the bounded shortlist
- Provides shallow evidence and provisional source metadata only

### Evidence Store Builder

Input:
- `BraveContextOutput`
- `ExtractorLightOutput`
- `AssessorOutput`
- Optional `JinaFetcherOutput`
- Optional existing `EvidenceStore`

Output:
- `EvidenceStore`

Ownership:
- Deterministically builds/merges the orchestrator-owned entity-centric `entity_name -> evidence chunks` store
- Uses ExtractorLight name-to-URL mapping first, then string matching as fallback

### JinaFetcher

Input:
- `AssessorOutput.selected_jina_urls`
- Remaining Jina fetch budget

Output:
- `JinaFetcherOutput`

Ownership:
- Fetches selected full pages only
- Returns Jina text, in-memory chunks, and fetch failure markers
