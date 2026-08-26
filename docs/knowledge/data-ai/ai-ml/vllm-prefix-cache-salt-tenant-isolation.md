# vLLM Prefix-Cache Salt Tenant Isolation

**Issue:** Automatic prefix caching can reuse KV blocks for identical prefixes. Without an isolation design, a shared service may expose timing signals or unintended cross-tenant cache reuse.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** draft

## Controls

- Set an unpredictable per-tenant or per-trust-domain cache salt where supported.
- Keep cache identity aligned with model, tokenizer, adapter, template, and policy versions.
- Do not treat cached KV state as durable or authenticated output.
- Separate high-sensitivity tenants at the process or service boundary when timing isolation requirements exceed cache-salt guarantees.

## Verification

- Send identical prompts under different salts and confirm they do not share cache hits.
- Rotate model, adapter, or chat template and verify old cache entries are not reused incorrectly.
- Measure cold and warm timing distributions for cross-tenant leakage analysis.

## Gotchas

- Prefix caching improves prefill computation but does not change generated-token semantics.
- A predictable salt does not provide a meaningful isolation boundary.

## Official sources

- https://docs.vllm.ai/en/latest/features/automatic_prefix_caching/
