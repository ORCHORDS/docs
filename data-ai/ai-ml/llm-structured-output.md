# llm-structured-output

**Issue:** Getting LLMs to reliably return structured data (JSON, typed objects)
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Free-form LLM output is hard to parse programmatically.

## Pattern / Solution
```python
from pydantic import BaseModel
from openai import OpenAI

class ExtractedEntity(BaseModel):
    name: str
    type: str
    confidence: float

client = OpenAI()
response = client.beta.chat.completions.parse(
    model="gpt-4o",
    messages=[{"role": "user", "content": f"Extract entities from: {text}"}],
    response_format=ExtractedEntity,
)
entity = response.choices[0].message.parsed
```

## Gotchas
- JSON mode still requires validation; model can produce invalid JSON rarely
- Nested schemas increase failure rates — flatten where possible
- Anthropic uses `tool_choice: {type: "tool", name: "..."}` for structured output

## Related
- `llm-json-mode.md`
- `llm-output-validation.md`
