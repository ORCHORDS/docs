# llm-streaming-responses

**Issue:** Streaming LLM output to clients for better perceived performance
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Waiting for full LLM responses creates poor UX; streaming shows output as it generates.

## Pattern / Solution
```python
# FastAPI SSE streaming endpoint
from fastapi.responses import StreamingResponse

async def stream_llm(prompt: str):
    async def generate():
        async with anthropic_client.messages.stream(
            model="claude-opus-4-5", max_tokens=1024,
            messages=[{"role": "user", "content": prompt}]
        ) as stream:
            async for text in stream.text_stream:
                yield f"data: {text}\n\n"
        yield "data: [DONE]\n\n"
    return StreamingResponse(generate(), media_type="text/event-stream")
```

## Gotchas
- Set `X-Accel-Buffering: no` in nginx to disable response buffering
- Handle client disconnects to cancel upstream stream
- Token counting for billing must happen via usage events, not character count

## Related
- `anthropic-claude-api-patterns.md`
- `llm-webhook-patterns.md`
