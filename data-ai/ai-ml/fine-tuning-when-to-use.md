# fine-tuning-when-to-use

**Issue:** Deciding when fine-tuning is appropriate versus prompt engineering
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Teams reach for fine-tuning prematurely when prompt engineering would suffice.

## Pattern / Solution
```
Fine-tuning is appropriate when:
✓ You have 500+ high-quality labeled examples
✓ Task requires consistent output style/format that prompts can't enforce
✓ Latency is critical (fine-tuned smaller model beats large model + long prompt)
✓ Cost reduction justifies fine-tuning investment (high volume, expensive model)
✓ Proprietary domain knowledge not in base model training data

Use prompt engineering when:
✓ <500 examples available
✓ Task is changing frequently
✓ Exploring the problem space
✓ Base model already handles task adequately
```

## Gotchas
- Fine-tuned models can lose general capability (catastrophic forgetting)
- Evals must be run against fine-tuned model, not just training loss
- Fine-tuning does not add factual knowledge — use RAG for that

## Related
- `fine-tuning-data-preparation.md`
- `fine-tuning-evaluation.md`
