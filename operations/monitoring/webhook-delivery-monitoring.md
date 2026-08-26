# webhook-delivery-monitoring

**Issue:** Tracking webhook delivery success rates and retry behavior for outbound and inbound webhooks
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Events are silently dropped because webhook deliveries fail. No retry visibility.

## Pattern / Solution
For outbound webhooks: track delivery attempts, success (2xx), failure codes, and retry counts. Persist delivery log with event ID, target URL, timestamp, status, and response body. Alert when delivery failure rate exceeds 5% over 15min. For inbound webhooks: idempotency check on event ID, then track processing success/failure. Expose a /webhook/health endpoint.

## Gotchas
Webhook retry storms can overwhelm your endpoint — implement backoff matching sender's retry schedule. Store raw webhook payload before processing — replay is invaluable during outage recovery. HMAC signature validation prevents replay attacks — always verify. Large webhook payloads should be stored and referenced by ID, not processed inline.

## Related
third-party-api-monitoring, queue-depth-monitoring, cron-job-monitoring
