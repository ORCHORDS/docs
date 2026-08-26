# llm-batch-processing

**Issue:** Processing thousands of LLM requests naively is slow, expensive, and hits rate limits
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
A pipeline needs to run LLM inference on 10k+ documents. Sequential calls take hours; naive parallelism triggers rate limits; prompt tokens are duplicated across every request.

## Pattern / Solution
Use provider batch APIs where available (Anthropic Batch API, OpenAI Batch endpoint) — they offer lower cost and higher throughput at the expense of latency. For real-time pipelines, use an async worker pool with backpressure. Share prompt prefix via caching. Group requests by similar prompt length to minimize padding waste.

```python
import anthropic

client = anthropic.Anthropic()
batch = client.messages.batches.create(requests=[
    {"custom_id": f"doc-{i}", "params": {"model": "...", "messages": [...]}}
    for i, doc in enumerate(documents)
])
# Poll until done, then retrieve results by custom_id
```

## Gotchas
- Batch APIs have latency SLAs of hours, not seconds — not suitable for interactive flows
- Batch jobs may partially fail; always check per-request status in results, not just overall job status
- Sort requests by estimated output length to pipeline GPU memory more efficiently when using self-hosted models

## Related
- llm-async-patterns
- llm-rate-limit-handling
- llm-cost-optimization
