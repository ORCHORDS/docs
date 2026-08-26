# llm-fallback-provider-rotation

**Issue:** Automatically rotating to fallback providers on failure or rate limits
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Single-provider dependencies cause outages during API incidents.

## Pattern / Solution
```python
PROVIDERS = [ClaudeProvider(), OpenAIProvider(), GeminiProvider()]

async def chat_with_fallback(messages: list) -> str:
    for provider in PROVIDERS:
        try:
            return await provider.chat(messages)
        except (RateLimitError, APIError) as e:
            logger.warning(f"Provider {provider} failed: {e}, trying next")
    raise Exception("All providers exhausted")
```
Use LiteLLM router for production:
```python
router = Router(model_list=[
    {"model_name": "primary", "litellm_params": {"model": "anthropic/claude-opus-4-5"}},
    {"model_name": "primary", "litellm_params": {"model": "openai/gpt-4o"}},
])
```

## Gotchas
- Fallback adds latency; use circuit breakers to fail fast on known-down providers
- Ensure prompt compatibility across models before enabling rotation

## Related
- `llm-provider-abstraction.md`
- `llm-rate-limit-handling.md`
