# ai-gateway-logging

**Issue:** Logging all LLM requests and responses through a gateway for audit and debugging
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Without centralized logging, debugging production LLM issues requires guesswork.

## Pattern / Solution
```python
import structlog, time

log = structlog.get_logger()

async def logged_llm_call(model: str, messages: list, user_id: str, **kwargs) -> dict:
    start = time.perf_counter()
    request_id = str(uuid.uuid4())

    try:
        response = await llm_client.chat(model=model, messages=messages, **kwargs)
        latency_ms = (time.perf_counter() - start) * 1000
        log.info("llm_call", request_id=request_id, model=model, user_id=user_id,
                 input_tokens=response.usage.input_tokens, output_tokens=response.usage.output_tokens,
                 latency_ms=round(latency_ms, 1), status="ok")
        return response
    except Exception as e:
        log.error("llm_call_failed", request_id=request_id, error=str(e))
        raise
```

## Gotchas
- Never log raw user messages without PII scrubbing
- Log token counts for cost attribution, not just request counts
- Use structured logs (JSON) for ingestion into observability platforms

## Related
- `ai-gateway-caching.md`
- `agent-observability-tracing.md`
- `pii-detection-redaction.md`
