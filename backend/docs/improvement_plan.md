# Improvement Plan

## Scope

This document tracks the main remaining improvements for the current pipeline.

Most of the earlier roadmap is now outdated because the retrieval stack, chunk ranking, source bucketing, SSE visibility, and entity reranking have already been implemented.

At this point, the main remaining work is:

1. reduce `Processing sources` latency
2. improve weak entity generation / source quality
3. evaluate schema-specific queries for sparse outputs
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

## 2. Weak Entities / Weak Sources

### Current Diagnosis

The current main quality issue is not primarily reranking.

The more important issue is weak candidate quality caused by weak source quality and weak corroboration.

Revised diagnosis:

1. primary issue: not enough good sources/candidates
2. secondary issue: some bad candidates should still be filtered
3. reranking is not the main bottleneck right now

Recent logs suggest:

- too many entities are supported by only one source
- too many entities come from only one rewrite
- too many selected sources are still generic listicles / roundup-style pages
- the reranker is often being asked to choose among mediocre single-source candidates

### What To Do Next

- get more representative sources, not just more sources
- specifically more:
  - `official_entity`
  - `profile_directory`
  - stronger local/editorial sources
- and fewer generic listicles dominating the selected pool

Concretely, the next useful step is probably:

- strengthen source selection so `roundup_list` does not dominate as much
- maybe increase preference/caps for:
  - `official_entity`
  - `profile_directory`
  - `editorial_reference`
- and/or do a second lightweight expansion pass from top candidates to fetch official/profile pages

### Secondary Cleanup

Even though reranking is not the main bottleneck, some bad candidates should still be filtered eventually.

Examples:

- agencies
- districts / neighborhoods when the query asks for venues or concrete places
- other obvious wrong-type entities

But this is secondary to improving the source pool itself.

### Success Criteria

- more candidates have support from multiple sources
- more candidates have support from multiple query variants
- final outputs rely less on generic roundup pages
- obviously wrong entities become rarer without relying on heavy cleanup

---

## 3. Schema-Specific Queries

### Problem

Some outputs are still sparse:

- not enough entities for the requested query
- too many missing columns

This is a different problem from weak entities.

### Goal

Improve coverage for sparse outputs without overcomplicating the default retrieval path.

### Recommended Direction

Investigate schema-specific or column-specific follow-up queries only as a targeted enrichment mechanism.

This should be treated as:

- a solution for sparse entities / sparse columns
- not the main solution for weak entity quality

### Open Question

This may or may not be the best next move after source-quality improvements.

It should be evaluated against simpler alternatives first.

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
2. weak entities / weak sources
3. planner latency
4. schema-specific queries

Reasoning:

- source latency and source quality are the main bottlenecks right now
- schema-specific queries are useful, but they are more relevant to sparsity than to weak entities
