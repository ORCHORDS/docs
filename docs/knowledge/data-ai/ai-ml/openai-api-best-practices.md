# openai-api-best-practices

**Issue:** Best practices for using the OpenAI API reliably and cost-effectively
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
OpenAI API calls fail unpredictably or cost more than expected without proper configuration.

## Pattern / Solution
```python
from openai import AsyncOpenAI

client = AsyncOpenAI(timeout=30.0, max_retries=3)

response = await client.chat.completions.create(
    model="gpt-4o",
    messages=[{"role": "user", "content": prompt}],
    temperature=0.2,
    max_tokens=1024,
    seed=42,  # reproducibility
)
usage = response.usage  # prompt_tokens, completion_tokens, total_tokens
```

## Gotchas
- Use `seed` for reproducible outputs in evals
- `max_tokens` is completion tokens only, not total context
- Batch requests with the Batch API for >50% cost savings on async workloads

## Related
- `llm-token-counting.md`
- `llm-cost-optimization.md`
