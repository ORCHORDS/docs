# llm-webhook-patterns

**Issue:** Long-running LLM jobs need to notify callers on completion without holding HTTP connections open
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Batch inference jobs or async processing pipelines take minutes to complete. Clients cannot maintain open connections that long; polling creates unnecessary load; push notifications need a reliable delivery mechanism.

## Pattern / Solution
Accept a webhook URL at request time. Store the job in a queue with the webhook URL. On completion, POST results to the webhook with retry logic (exponential backoff, 3 attempts). Sign webhook payloads with HMAC-SHA256 so receivers can verify authenticity.

```python
import hmac, hashlib, httpx, json

def deliver_webhook(url: str, payload: dict, secret: str):
    body = json.dumps(payload).encode()
    sig = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    httpx.post(url, content=body, headers={
        "Content-Type": "application/json",
        "X-Signature-SHA256": f"sha256={sig}"
    }, timeout=10)
```

## Gotchas
- Webhook endpoints must respond with 2xx within a few seconds; offload processing to a background task
- Implement idempotency — retries can deliver the same webhook multiple times
- Store webhook delivery status and allow manual re-delivery from an admin panel

## Related
- llm-async-patterns
- llm-batch-processing
- agent-observability-tracing
