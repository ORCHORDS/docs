# llm-token-counting

**Issue:** Accurately counting tokens before sending to avoid context overflow
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Requests exceeding context limits throw errors; estimating cost requires accurate counts.

## Pattern / Solution
```python
import tiktoken

def count_tokens(text: str, model: str = "gpt-4o") -> int:
    enc = tiktoken.encoding_for_model(model)
    return len(enc.encode(text))

# Anthropic token counting API
response = client.messages.count_tokens(
    model="claude-opus-4-5",
    messages=[{"role": "user", "content": text}],
)
print(response.input_tokens)
```

## Gotchas
- Tiktoken is OpenAI-specific; use the Anthropic SDK count endpoint for Claude
- Message formatting overhead adds tokens beyond raw text (role labels, structure)
- Tool definitions consume significant tokens — count them too

## Related
- `llm-context-window-management.md`
- `llm-cost-optimization.md`
