# gemini-api-patterns

**Issue:** Patterns for using Google Gemini API in production
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Gemini has a different SDK structure and safety settings that trip up developers.

## Pattern / Solution
```python
import google.generativeai as genai

genai.configure(api_key="YOUR_KEY")
model = genai.GenerativeModel("gemini-2.0-flash")

response = model.generate_content(
    "Summarize this document",
    generation_config=genai.GenerationConfig(max_output_tokens=512, temperature=0.1),
    safety_settings={"HARASSMENT": "BLOCK_NONE"},
)
print(response.text)
```

## Gotchas
- Safety filters block output silently — check `response.prompt_feedback`
- Context caching via `CachedContent` saves cost on repeated large contexts
- Multimodal input uses `Part.from_bytes()` or `Part.from_uri()`

## Related
- `multimodal-vision-patterns.md`
- `llm-cost-optimization.md`
