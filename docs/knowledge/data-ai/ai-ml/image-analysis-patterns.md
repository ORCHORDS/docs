# image-analysis-patterns

**Issue:** Image analysis tasks need consistent prompting strategies to extract reliable structured information
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
An e-commerce pipeline uses vision LLMs to extract product attributes from photos. Results are inconsistent — sometimes the model describes the image, other times it extracts attributes, and confidence varies widely across product categories.

## Pattern / Solution
Structure prompts as explicit extraction tasks with output schema. For defect detection, provide reference examples of defect categories. For classification tasks, list all possible classes. Chain steps for complex analysis: first describe, then classify based on description — this reduces hallucination compared to direct classification.

```
Analyze this product image and extract attributes as JSON:
{"color": str, "material": str, "condition": "new|used|damaged", "defects": [str]}
If a field cannot be determined from the image, use null.
```

## Gotchas
- Low-resolution or poorly-lit images yield unreliable results — implement image quality checks before API call
- Background objects influence attribute extraction — crop to subject where possible
- Models perform better on categories well-represented in training data; unusual products need few-shot examples

## Related
- multimodal-vision-patterns
- ocr-with-llm
- llm-output-validation
