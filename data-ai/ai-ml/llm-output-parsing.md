# llm-output-parsing

**Issue:** Extracting structured data from free-form LLM text is brittle and breaks across model versions
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
LLM output parsing logic written for one model breaks when switching providers or after a model update. Regex-based parsers are fragile; JSON extraction fails when the model adds commentary around the JSON block.

## Pattern / Solution
Use a defensive extraction pipeline: (1) try native JSON parse, (2) extract JSON from markdown fences with regex, (3) use a lenient JSON parser (json5), (4) fall back to regex field extraction. Prefer asking the model for JSON from the start with explicit schema in the prompt.

```python
import re, json

def extract_json(text: str) -> dict:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', text, re.DOTALL)
    if match:
        return json.loads(match.group(1))
    match = re.search(r'\{.*\}', text, re.DOTALL)
    if match:
        return json.loads(match.group(0))
    raise ValueError("No JSON found in response")
```

## Gotchas
- Never trust that the model will output only JSON even when instructed
- Greedy regex on `{.*}` will grab the outermost braces; use non-greedy or a proper JSON bracket counter for nested objects
- json5 library accepts trailing commas and comments — useful for lenient parsing but adds a dependency

## Related
- llm-output-validation
- llm-structured-output
- llm-json-mode
