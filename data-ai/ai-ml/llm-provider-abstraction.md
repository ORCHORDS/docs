# llm-provider-abstraction

**Issue:** Abstracting over multiple LLM providers with a single interface
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Switching providers or running A/B tests requires touching many call sites.

## Pattern / Solution
```python
from abc import ABC, abstractmethod

class LLMProvider(ABC):
    @abstractmethod
    async def chat(self, messages: list[dict], **kwargs) -> str: ...

class OpenAIProvider(LLMProvider):
    async def chat(self, messages, **kwargs):
        r = await openai_client.chat.completions.create(model="gpt-4o", messages=messages, **kwargs)
        return r.choices[0].message.content

class ClaudeProvider(LLMProvider):
    async def chat(self, messages, **kwargs):
        r = await anthropic_client.messages.create(model="claude-opus-4-5", messages=messages, max_tokens=1024, **kwargs)
        return r.content[0].text
```
Use LiteLLM as a drop-in abstraction layer: `litellm.completion(model="anthropic/claude-opus-4-5", messages=[...])`

## Gotchas
- Normalize message roles — Gemini uses `model` not `assistant`
- Max tokens semantics differ per provider

## Related
- `llm-fallback-provider-rotation.md`
- `llm-api-integration-patterns.md`
