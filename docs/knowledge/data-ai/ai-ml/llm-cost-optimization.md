# llm-cost-optimization

**Issue:** Reducing LLM API costs without sacrificing quality
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
LLM costs scale with token usage and can grow unexpectedly.

## Pattern / Solution
```python
# 1. Use smaller models for simple tasks
router = {
    "classify": "gpt-4o-mini",
    "summarize": "claude-haiku-3-5",
    "reason": "claude-opus-4-5",
}

# 2. Prompt caching (Anthropic)
messages = [{"role": "user", "content": [
    {"type": "text", "text": long_system_doc, "cache_control": {"type": "ephemeral"}},
    {"type": "text", "text": user_query},
]}]

# 3. Batch API for async workloads (50% discount)
batch = client.batches.create(requests=[...])
```

## Gotchas
- Prompt caching requires min 1024 tokens to activate
- Output tokens cost 3-5x input tokens — keep outputs tight
- Log and alert on cost per request, not just total monthly

## Related
- `llm-token-counting.md`
- `semantic-caching-patterns.md`
