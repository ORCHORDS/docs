# ai-feature-flag-patterns

**Issue:** Rolling out new LLM models or prompts safely requires feature flag infrastructure tailored to AI workloads
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
A team wants to gradually roll out a new prompt version to 10% of users, then increase as confidence grows. Without feature flags, they redeploy code for every percentage change and cannot target specific user segments.

## Pattern / Solution
Use a feature flag system (LaunchDarkly, GrowthBook, Unleash) to control model version, prompt template, and inference parameters per request. Assign flags based on user ID for consistency — the same user always sees the same variant. Include flag state in request logging to enable cohort analysis. Support kill switches to instantly revert to stable configuration without a deploy.

```python
def get_model_config(user_id: str) -> dict:
    variant = flags.variation("llm-model-version", user_id, default="v1")
    return MODEL_CONFIGS[variant]
```

## Gotchas
- Flag evaluation must be fast (<1 ms) — do not make network calls in the hot path; use local SDK with background sync
- Log the flag variant with every LLM call so you can filter metrics by variant later
- Avoid too many simultaneous flag experiments on the same user population — they interact in unpredictable ways

## Related
- llm-ab-testing
- llm-shadow-deployment
- model-versioning-strategy
