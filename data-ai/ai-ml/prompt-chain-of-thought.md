# prompt-chain-of-thought

**Issue:** Using chain-of-thought prompting to improve reasoning
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Models make arithmetic or multi-step logic errors without explicit reasoning steps.

## Pattern / Solution
```python
# Zero-shot CoT
prompt = f"{problem}\n\nLet's think step by step."

# Few-shot CoT
prompt = """
Q: Roger has 5 tennis balls. He buys 2 more cans of 3 balls each. How many does he have?
A: Roger starts with 5. 2 cans × 3 = 6 more. 5 + 6 = 11. The answer is 11.

Q: {question}
A: Let's work through this."""

# Extract final answer only
prompt += "\n\nFinal answer (number only):"
```

## Gotchas
- CoT increases output tokens significantly — factor into cost/latency
- For simple tasks, CoT can introduce unnecessary errors
- Extended thinking (Claude) moves reasoning into a separate hidden block

## Related
- `prompt-few-shot-examples.md`
- `llm-for-classification.md`
