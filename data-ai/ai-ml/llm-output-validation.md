# llm-output-validation

**Issue:** LLM responses fail silently when they don't match expected schema or business rules
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
You call an LLM and get back a response that looks correct but contains wrong types, missing fields, or values outside acceptable ranges. Downstream code crashes or silently corrupts data.

## Pattern / Solution
Validate at two layers: structural (JSON schema / Pydantic model) and semantic (business rules). Use a retry loop — on validation failure, inject the error message back into the prompt and retry up to 3 times before raising. Keep a strict/lenient mode toggle: strict for critical paths, lenient for exploratory generation.

```python
from pydantic import BaseModel, ValidationError

class ExtractedData(BaseModel):
    name: str
    confidence: float  # 0.0-1.0

def validated_call(prompt: str, model, retries=3):
    for attempt in range(retries):
        raw = model.complete(prompt)
        try:
            return ExtractedData.model_validate_json(raw)
        except ValidationError as e:
            if attempt == retries - 1:
                raise
            prompt += f"\n\nPrevious attempt failed validation: {e}. Fix and retry."
```

## Gotchas
- LLMs sometimes wrap JSON in markdown fences — strip before parsing
- Validation error messages fed back into the prompt can teach the model to hack around constraints rather than fix real issues
- Float ranges like confidence scores often come back as strings ("0.9" vs 0.9)

## Related
- llm-structured-output
- llm-output-parsing
- llm-retry-patterns
