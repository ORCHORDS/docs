# ai-cost-monitoring

**Issue:** LLM costs grow unpredictably without real-time monitoring and per-feature attribution
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Monthly LLM spend doubles unexpectedly. The team cannot identify which feature, user segment, or code path is responsible. By the time the billing invoice arrives, the cost has already been incurred and cannot be recovered.

## Pattern / Solution
Instrument every LLM call with metadata: feature name, user tier, model, prompt tokens, completion tokens. Compute cost per call using a provider pricing table updated at deploy time. Aggregate in real-time (ClickHouse, Datadog custom metrics). Set per-feature budgets and alert at 70%/90% thresholds. Show cost per user in internal dashboards for pricing model validation.

```python
COST_PER_TOKEN = {"gpt-4o": {"input": 2.5e-6, "output": 10e-6}}

def log_call(model, prompt_tokens, completion_tokens, feature):
    cost = (prompt_tokens * COST_PER_TOKEN[model]["input"] +
            completion_tokens * COST_PER_TOKEN[model]["output"])
    metrics.record("llm_cost_usd", cost, tags={"feature": feature, "model": model})
```

## Gotchas
- Token counts from completion API responses are authoritative — do not estimate from character count
- Cached prompt tokens (where supported by the provider) cost less — track separately
- Set hard spend limits at the provider account level as a last-resort backstop independent of application logic

## Related
- llm-cost-optimization
- llm-token-counting
- ai-latency-optimization
