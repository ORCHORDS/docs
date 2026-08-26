# llm-shadow-deployment

**Issue:** Deploying a new LLM in production without first validating it on real traffic causes unexpected failures
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
A new model version is tested on benchmarks and looks great. After deployment to production, edge cases from real user inputs cause failures that were not in the test set. Rolling back is painful and slow.

## Pattern / Solution
Run shadow mode: route all production requests to both old and new model simultaneously. Serve the old model's response to the user; log both responses for comparison. Compare outputs offline: measure divergence rate, flag high-divergence cases for human review, track error rates. Only cut over when shadow metrics satisfy your thresholds.

Shadow deployment duration: at minimum 7 days to capture weekly traffic patterns before promoting the challenger.

## Gotchas
- Shadow mode doubles LLM cost during the validation period — budget for it
- High divergence does not always mean the new model is worse; the old model may be producing bad outputs you have normalized to
- Shadow mode must be transparent in logging but completely invisible to users

## Related
- llm-ab-testing
- model-versioning-strategy
- ai-feature-flag-patterns
- agent-observability-tracing
