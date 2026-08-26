# fine-tuning-data-preparation

**Issue:** Preparing high-quality training data for LLM fine-tuning
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Poor training data quality produces worse outputs than the base model.

## Pattern / Solution
```python
# OpenAI fine-tuning JSONL format
import json

def format_example(instruction: str, response: str) -> dict:
    return {
        "messages": [
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": instruction},
            {"role": "assistant", "content": response},
        ]
    }

# Validate dataset
with open("train.jsonl") as f:
    examples = [json.loads(line) for line in f]

# Check format, length, diversity
token_counts = [count_tokens(json.dumps(ex)) for ex in examples]
print(f"Examples: {len(examples)}, Avg tokens: {sum(token_counts)/len(token_counts):.0f}")
assert len(examples) >= 50, "Minimum 50 examples for meaningful fine-tuning"
```

## Gotchas
- Deduplicate training examples — duplicates cause overfitting
- Balance positive and negative examples for classification tasks
- Reserve 10-20% as validation set; monitor validation loss, not training loss

## Related
- `fine-tuning-when-to-use.md`
- `fine-tuning-evaluation.md`
