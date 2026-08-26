# anthropic-claude-api-patterns

**Issue:** Patterns specific to the Anthropic Claude API
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Claude API has unique message structure, system prompts, and tool-use conventions.

## Pattern / Solution
```python
import anthropic

client = anthropic.Anthropic()

message = client.messages.create(
    model="claude-opus-4-5",
    max_tokens=1024,
    system="You are a helpful assistant.",
    messages=[{"role": "user", "content": "Explain RAG in one paragraph."}],
)
print(message.content[0].text)
```
For streaming:
```python
with client.messages.stream(model="claude-opus-4-5", max_tokens=512, messages=[...]) as stream:
    for text in stream.text_stream:
        print(text, end="", flush=True)
```

## Gotchas
- System prompt is a top-level param, not a message role
- `content` is a list of blocks, not a plain string
- Extended thinking uses a separate `thinking` content block

## Related
- `llm-streaming-responses.md`
- `llm-tool-use-patterns.md`
