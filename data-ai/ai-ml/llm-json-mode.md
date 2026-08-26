# llm-json-mode

**Issue:** Forcing LLM output to be valid JSON
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
LLMs add markdown fences or prose around JSON, breaking parsers.

## Pattern / Solution
```python
# OpenAI JSON mode
response = client.chat.completions.create(
    model="gpt-4o",
    response_format={"type": "json_object"},
    messages=[{"role": "user", "content": "Return a JSON object with keys: name, score"}],
)
data = json.loads(response.choices[0].message.content)

# Fallback: strip markdown fences
import re
def extract_json(text: str) -> dict:
    match = re.search(r"```json\s*(.*?)\s*```", text, re.DOTALL)
    return json.loads(match.group(1) if match else text)
```

## Gotchas
- JSON mode does NOT guarantee schema correctness, only valid JSON syntax
- Must instruct the model to return JSON in the prompt when using JSON mode
- Use structured output (Pydantic) for schema validation on top of JSON mode

## Related
- `llm-structured-output.md`
- `llm-output-parsing.md`
