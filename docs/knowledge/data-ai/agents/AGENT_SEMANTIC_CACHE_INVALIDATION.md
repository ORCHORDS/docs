---
title: "Agent Semantic Cache Invalidation"
owner: "AI Platform"
status: "approved"
classification: "public"
last-reviewed: "2026-09-05"
review-cycle: "90 days"
next-review: "2026-12-04"
---

# Agent Semantic Cache Invalidation

## Scope

Defines how ORCHORDS agents invalidate semantic caches when prompts, models, grounding data, or policy decisions change, so cached answers remain trustworthy and reproducible.

## Identifier table

| Field | Value |
|---|---|
| Topic | Semantic cache invalidation strategy for agent answers |
| Inputs | Prompt version, model identifier, grounding snapshot, policy version |
| Outputs | Cache key namespace, invalidation events, freshness report |
| Audience | AI Platform, Search and Retrieval, Knowledge Engineering |
| Trigger | Any change in prompt, model, grounding, or policy revision |
| Companion | AGENT_CACHE_CORRECTNESS.md, AGENT_PROMPT_TEMPLATE_VERSION_LINEAGE.md |

## Plan

1. Compose the semantic cache key from prompt version, model identifier, grounding snapshot identifier, and policy version; never include user-provided content as the sole key.
2. Bind the cache to a per-tenant namespace so cross-tenant leakage is impossible by design.
3. Record every prompt, model, grounding, and policy revision and emit an invalidation event that names the affected cache key range.
4. On invalidation, mark stale entries as tombstoned rather than deleting them immediately; a sweeper process purges them after the documented grace period.
5. For high-stakes queries, require a freshness check before serving a cached answer; refuse cache hits older than the freshness window.
6. Periodically verify cache hit reproducibility by re-running a sample of cached queries and comparing answers within an allowed tolerance.
7. Surface cache invalidation events on the freshness dashboard so operators can correlate answer regressions with revisions.

## Inputs

- Revision identifiers for prompt, model, grounding, and policy
- Per-tenant namespace configuration
- Freshness window configuration

## ORCHORDS Profile

| Setting | Value |
|---|---|
| Default freshness window | 24 hours for high-stakes queries; 7 days for general queries |
| Tombstone grace period | 30 days |
| Reproducibility sample rate | 0.1 percent of cache hits, with at least 10 per day |
| Allowed answer tolerance | Cosine similarity at least 0.97 on embedding; exact match on critical fields |

## Implementation Notes

- Treat cache keys as security-sensitive; never log full keys in plain text.
- Apply rate limits to the sweeper so it cannot dominate the cache backend.
- Make invalidation idempotent so retries are safe.

## Companion Documents

- AGENT_CACHE_CORRECTNESS.md
- AGENT_PROMPT_TEMPLATE_VERSION_LINEAGE.md
- AGENT_MODEL_CHANGE_CONTROL_NIST_AI_RMF.md
