# Stage Contracts

This document records the active ownership and typed I/O boundaries for the reduced pipeline. The `north_star_*` docs remain historical reference only.

## Planner

Input:
- `PipelineRequest.query`

Output:
- `PlannerOutput`

Ownership:
- infers `entity_type`, `schema_columns`, `core_aspects`, `base_query`, and `initial_query_rewrites`
- performs only conservative query normalization
- never asks the user for clarification at runtime
- may reject the query by setting `error=true`
- typical shape: `schema_columns` has 4–6 entries and always includes `name`; `core_aspects` has 1–5 entries

Does not own:
- retrieval execution
- evidence merging
- extraction

## Searcher

Input:
- `PlannerOutput`

Output:
- `SearcherOutput`

Ownership:
- executes supplied queries
- applies mechanical URL pruning
- performs exact-URL deduplication
- merges multi-query results
- applies query-source tie-breaking
- uses soft round-robin rewrite-slot reservation to avoid over-bias toward the base query first
- applies a small per-domain shortlist cap without doing domain-level deduplication
- returns Brave result metadata needed downstream, including domain, rank, query source, and provider metadata

Does not own:
- semantic query generation
- deep-fetch decisions
- extraction

## Brave LLM Context Helper

Input:
- `SearcherOutput.shortlisted_results`

Output:
- `BraveContextOutput`

Ownership:
- fetches URL-linked Brave LLM Context passages for the bounded shortlist
- runs one narrow context query per shortlisted result using title + snippet prefix + `site:<hostname>`
- retains only passages whose `source_url` exactly matches the shortlisted URL
- falls back to the original Searcher snippet when no exact-URL Brave Context passage survives
- applies deterministic passage cleanup before returning text
- provides shallow evidence only

Does not own:
- full-page retrieval
- source triage
- extraction

## ExtractorLight

Input:
- `PlannerOutput`
- `BraveContextOutput`

Output:
- `ExtractorLightOutput`

Ownership:
- extracts candidate names only
- builds `name -> source URLs` mention mapping
- records coarse mention counts

Does not own:
- field extraction
- alias resolution
- row scoring
- eligibility decisions

## Assessor

Input:
- `PlannerOutput`
- `SearcherOutput`
- `BraveContextOutput`
- `ExtractorLightOutput`
- optional existing `EvidenceStore`
- remaining fetch budget field may still exist in the request contract but is currently unused in active behavior

Output:
- `AssessorOutput`

Ownership:
- computes heuristic source signals
- carries Brave LLM Context passages as shallow evidence context
- performs one batched semantic source assessment
- classifies:
  - `source_role`
  - `source_quality`
  - `officiality`
  - `estimated_aspect_coverage`
  - `evidence_sufficiency`

Current scope:
- first-pass source triage only

Current non-ownership:
- verification-gap generation
- verification-query planning
- Jina URL selection
- second-pass reassessment

## Evidence Store Builder

Input:
- `BraveContextOutput`
- `ExtractorLightOutput`
- `AssessorOutput`
- optional existing `EvidenceStore`

Output:
- `EvidenceStore`

Ownership:
- deterministically builds and merges the orchestrator-owned entity-centric `entity_name -> evidence chunks` store
- uses ExtractorLight name-to-URL mapping first, then conservative string matching as fallback
- preserves source URL, source labels, origin, and aspect coverage on evidence chunks
- permits ambiguous chunks to remain attached to multiple entity names until later resolution

## Extractor

Input:
- `PlannerOutput`
- `ExtractorLightOutput`
- `EvidenceStore`

Output:
- `ExtractorOutput`

Ownership:
- produces structured candidate entities from entity-centric evidence chunks
- stores field-level provenance through `FieldValue.evidence`
- resolves contradictions conservatively where possible
- prefers null over unsupported values

Does not own:
- retrieval
- source triage
- evidence-store construction

## Final Row Selection / Response

Input:
- `PlannerOutput`
- `ExtractorOutput`

Output:
- `PipelineResponse`

Ownership:
- merges or drops weak duplicates if needed
- applies final row eligibility logic
- selects the final rows
- returns the user-facing structured response with inferred schema and traceable support

Does not own:
- retrieval
- evidence-store construction
- source triage

## Orchestrator

Input:
- `PipelineRequest`

Output:
- `PipelineResponse`

Ownership:
- runs the fixed active stage order
- tracks request-scoped budgets and state
- owns entity-centric evidence-store construction and merging
- assembles the final response
- emits lifecycle events if SSE is present in the app shell

Active stage order:
1. Planner
2. Searcher
3. Brave LLM Context on shortlist
4. ExtractorLight
5. Assessor first pass
6. Evidence store build
7. Extractor
8. Final row selection / response
