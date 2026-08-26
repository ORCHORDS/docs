# prompt-output-format-control

**Issue:** Controlling output format (Markdown, JSON, tables, plain text)
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Models switch formats unpredictably, breaking downstream parsers.

## Pattern / Solution
```python
# Explicit format instruction
system = """Always respond in this exact JSON format, no other text:
{
  "answer": "string",
  "confidence": 0.0-1.0,
  "sources": ["url1", "url2"]
}"""

# Prefill to force format (Anthropic)
messages = [
    {"role": "user", "content": "List 3 items"},
    {"role": "assistant", "content": "["},  # prefill starts JSON array
]
```

## Gotchas
- Prefilling is Anthropic-only; OpenAI uses `response_format`
- Validate output schema even when format control is used
- Markdown in API responses is rarely needed — disable unless rendering

## Related
- `llm-json-mode.md`
- `llm-structured-output.md`
