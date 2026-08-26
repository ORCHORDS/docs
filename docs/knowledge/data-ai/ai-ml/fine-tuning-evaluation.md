# fine-tuning-evaluation

**Issue:** Evaluating fine-tuned models to confirm improvement over baseline
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Training loss decreasing doesn't mean the model improved on the actual task.

## Pattern / Solution
```python
# Task-specific eval after fine-tuning
class FineTuneEvaluator:
    def __init__(self, base_model: str, ft_model: str):
        self.models = {"base": base_model, "ft": ft_model}

    async def compare(self, test_set: list[dict]) -> dict:
        results = {"base": [], "ft": []}
        for model_name, model_id in self.models.items():
            for example in test_set:
                pred = await llm(example["input"], model=model_id)
                score = await judge(pred, example["expected"])
                results[model_name].append(score)
        return {k: sum(v)/len(v) for k, v in results.items()}
```

## Gotchas
- Always compare fine-tuned to base model on the same eval set
- Check for capability regression on general tasks (MMLU, etc.)
- Human eval on 50-100 examples is required before production deployment

## Related
- `fine-tuning-when-to-use.md`
- `agent-evaluation-patterns.md`
