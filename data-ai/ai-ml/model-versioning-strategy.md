# model-versioning-strategy

**Issue:** LLM provider model updates silently change behavior, breaking applications that rely on specific model behavior
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
An application uses `gpt-4` (an alias) and behavior changes overnight after the provider updates the underlying model. Prompt tuning done for the old version no longer works. There is no rollback option available.

## Pattern / Solution
Always pin to specific model version strings (e.g., `gpt-4o-2024-08-06`, `claude-3-5-sonnet-20241022`) not aliases. Maintain a model registry mapping logical names to pinned versions. Define a model upgrade checklist: run eval suite on new version, compare outputs on golden test set, update prompts if needed, shadow deploy, then flip. Track model versions in all logs and traces.

## Gotchas
- Providers deprecate old versions with 3-6 months notice — monitor deprecation announcements and plan upgrades proactively
- Same prompt with a different model version can require different few-shot examples or system prompts
- Pricing changes with model versions — update cost budgets and alerts when upgrading

## Related
- llm-ab-testing
- llm-shadow-deployment
- ai-feature-flag-patterns
- prompt-versioning
