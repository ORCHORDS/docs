# prompt-few-shot-examples

**Issue:** Using examples in prompts to improve output quality
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Zero-shot prompts produce inconsistent formats or reasoning errors.

## Pattern / Solution
```python
FEW_SHOT = """
Classify the sentiment of customer reviews.

Review: "The product broke after 2 days"
Sentiment: negative

Review: "Works exactly as described, fast shipping"
Sentiment: positive

Review: "It's okay, nothing special"
Sentiment: neutral

Review: "{review}"
Sentiment:"""

prompt = FEW_SHOT.format(review=user_review)
```

## Gotchas
- 3-5 examples is usually optimal; more rarely helps and wastes tokens
- Examples must cover edge cases, not just easy cases
- Order matters: put the most representative example last

## Related
- `prompt-engineering-fundamentals.md`
- `prompt-chain-of-thought.md`
