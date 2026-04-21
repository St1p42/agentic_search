# Improvement Plan

## Scope

This document tracks the main remaining improvements for the current pipeline.

Most of the earlier roadmap is now outdated because the retrieval stack, chunk ranking, source bucketing, SSE visibility, and entity reranking have already been implemented.

At this point, the main remaining work is:

1. reduce `Processing sources` latency
2. improve breadth-v2 source quality and weak entity quality
3. evaluate whether breadth-v2 is enough for sparse outputs or needs further refinement
4. reduce planner latency if possible

---

## 1. Processing Sources Latency

### Problem

`Processing sources` is now one of the more noticeable latency contributors in the end-to-end flow.

Even after the search/source-classification improvements, this stage can feel too slow relative to the value it adds.

### Goal

Reduce wall-clock time for source processing without changing output quality.

### Recommended Direction

- review whether more of the source processing path can be parallelized safely
- check whether any serial work in Jina fetch / source preparation can be batched or overlapped
- keep concurrency bounded so we do not create unstable latency spikes

### Success Criteria

- `Processing sources` is materially faster on representative queries
- output quality does not regress
- the stage remains operationally stable

---

## 2. Breadth-V2 Source Quality / Weak Entities

### Current Diagnosis

The current main quality issue is now split across two layers:

- first-pass entity quality is still imperfect
- breadth-v2 enrichment still relies too heavily on generic roundup/listicle sources

Revised diagnosis:

1. primary issue: breadth-v2 still retrieves too many generic roundup pages
2. secondary issue: some wrong-type entities still survive into enrichment
3. reranking is not the main bottleneck right now

Recent logs suggest:

- breadth-v2 queries are now better formed, but the second-pass source pool is still weak
- hard columns such as `notable_portfolio_companies` still often miss obvious values
- breadth-v2 shortlisted chunks are still dominated by generic editorial/listicle pages rather than official or profile-style sources
- wrong entity types can still enter enrichment if they survive first-pass extraction/reranking

### What To Do Next

Prioritize better breadth-v2 source quality, not broader expansion.

Concretely, the next useful step is probably:

- add a light source preference in breadth v2 toward:
  - `official_entity`
  - `profile_directory`
  - stronger single-entity/profile pages
- downweight generic roundup/listicle pages during breadth-v2 retrieval/selection
- strengthen entity-type plausibility before breadth-v2 enrichment runs so obvious wrong-type entities do not get enriched
- keep the current breadth-v2 debug logging and use it to inspect:
  - generated facet terms
  - built follow-up queries
  - shortlisted enrichment sources/chunks

### Secondary Cleanup

Even though reranking is not the main bottleneck, some bad candidates should still be filtered eventually.

Examples:

- non-target entity types that survive first pass
- obvious companies/products showing up in firm/investor queries
- other clear wrong-type entities

But this is secondary to improving the source pool itself.

### Success Criteria

- breadth-v2 sources rely less on generic roundup pages
- hard columns fill more reliably on representative queries
- obviously wrong entities are enriched less often
- internal quality looks stable enough for broader testing

### Current Release Stance

Current status:

- good internal milestone
- acceptable for internal testing / limited beta
- not yet strong enough for confident broad deployment

Reason:

- the system is clearly improving
- but hard-column quality is still too dependent on weak second-pass sources
- current behavior is still query-dependent in a brittle way

---

## 3. Schema-Specific Queries / Breadth-V2 Follow-Up

### Problem

Some outputs are still sparse:

- not enough entities for the requested query
- too many missing columns

The active breadth-v2 sparse-field enrichment pass now exists, so the question is no longer whether schema-specific follow-up retrieval is useful in principle.

The current question is whether breadth-v2 needs further refinement, especially:

- better source quality
- better entity-type gating
- possible column-specific handling for especially hard fields

### Goal

Improve coverage for sparse outputs without overcomplicating the default retrieval path.

### Recommended Direction

Keep breadth-v2 as the active targeted enrichment mechanism and refine it rather than replacing it immediately.

This should be treated as:

- a solution for sparse entities / sparse columns
- not the main solution for weak entity quality

### Success Criteria

- more non-empty fields for valid entities
- better fill rate on sparse queries
- limited latency impact

---

## 4. Planner Latency

### Problem

Planner latency is still visible in the end-to-end experience.

### Goal

Reduce planner latency if possible without making rewrites and schema inference materially worse.

### Recommended Direction

- inspect whether the planner prompt can be shortened
- inspect whether planner output requirements can be simplified
- keep rewrite quality stable enough for discovery

### Success Criteria

- lower planner latency on representative runs
- no meaningful drop in rewrite quality or schema usefulness

---

## Priority Order

Recommended near-term order:

1. `Processing sources` latency
2. breadth-v2 source quality / weak entities
3. planner latency
4. breadth-v2 refinement for sparse outputs

Reasoning:

- source latency and second-pass source quality are the main bottlenecks right now
- breadth-v2 exists and is promising, but still needs refinement before broader deployment
