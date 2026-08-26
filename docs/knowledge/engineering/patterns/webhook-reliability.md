# webhook-reliability

**Issue:** Webhook reliability — idempotency, retry, signature
**Date:** 2026-08-09
**Status:** documented

## Symptom
You send a webhook. The customer says "I got it
twice." You got double-charged. The signature is
invalid. The retry never arrived. You wish you had
the reliability stack.

## Root cause
**At-least-once delivery is universal. Build for
duplicates.** Use 4 layers.

**Source:** Digital Applied + DZone 2026.

## The "at-least-once" concept

For delivery:
- **At-least-once:** Universal (default)
- **Exactly-once:** Doesn't exist
- **Duplicate is normal:** Plan for it
- **Stripe:** "May receive same event > once"

The delivery is at-least-once.

## The "4 reliability layers" pattern

For webhooks:
1. **Signature verification** — Authenticate
2. **Idempotency** — Dedup on event ID
3. **Fast ack + async** — Return 200 fast
4. **DLQ + retry** — Handle failures

The 4 layers are sequential.

## The "signature verification" pattern

For HMAC-SHA256:
```python
import hmac, hashlib

def verify(raw_body, header, secret):
    # 1. Extract timestamp + signature
    # Stripe format: "t=12345,v1=abc..."
    parts = dict(p.split("=") for p in header.split(","))
    timestamp = parts["t"]
    sig = parts["v1"]

    # 2. Reconstruct signed payload
    signed_payload = f"{timestamp}.{raw_body}".encode()

    # 3. Compute expected
    expected = hmac.new(
        secret.encode(),
        signed_payload,
        hashlib.sha256
    ).hexdigest()

    # 4. Constant-time compare
    return hmac.compare_digest(expected, sig)
```

The signature is verified.

## The "raw body" rule

For verification:
- **Verify against raw bytes:** Before any parsing
- **Express:** `express.raw({ type: 'application/json' })`
- **Scope to route:** Not global body parser
- **Why:** JSON re-serialization breaks HMAC

The raw body is verified.

## The "constant-time compare" pattern

For comparison:
- **❌ Naive:** `if computed == received` (timing leak)
- **✅ Constant-time:**
  - Python: `hmac.compare_digest(a, b)`
  - Node: `crypto.timingSafeEqual(a, b)`
  - Go: `hmac.Equal(a, b)`

The compare is constant-time.

## The "idempotency" pattern

For dedup:
```sql
-- Atomic claim
INSERT INTO processed_webhooks (event_id, received_at)
VALUES ($1, NOW())
ON CONFLICT (event_id) DO NOTHING
RETURNING id;
```

If RETURNING is empty → already processed. Stop.

The claim is atomic.

## The "race-free claim" pattern

For race:
- **Issue:** Concurrent retries
- **Fix:** Unique constraint on event_id
- **Result:** DB enforces exactly-once claim

The race is prevented.

## The "TTL > retry window" pattern

For dedup TTL:
- **Stripe live:** 3 days → TTL 7 days
- **Svix:** ~1 day → TTL 2 days
- **Shopify:** ~4 hours (8 retries) → TTL 1 day
- **AWS SQS:** Until processed

The TTL outlives retry.

## The "fast ack + async" pattern

For latency:
```
1. Verify signature (raw body)
2. INSERT event_id (atomic claim)
3. Enqueue to durable queue
4. Return 200/202 immediately
5. Worker processes async
```

The ack is fast.

## The "queue" pattern

For async:
- **Amazon SQS:** Standard (at-least-once) or FIFO
- **Google Pub/Sub:** At-least-once
- **Apache Kafka:** Replay + ordering
- **PostgreSQL:** For low volume
- **Redis Streams:** Lightweight

The queue is durable.

## The "transaction" pattern

For business + claim:
```sql
BEGIN;
  -- 1. Claim event (already done in handler)
  -- 2. Execute business
  UPDATE accounts SET balance = balance - $amount WHERE id = $id;
  INSERT INTO charges (event_id, amount) VALUES ($1, $amount);
COMMIT;
```

Both commit together or rollback.

The transaction is atomic.

## The "retry policy" pattern

For exponential backoff:
- **Base:** 500ms - 1s
- **Factor:** 2x per attempt
- **Jitter:** ±250ms
- **Max attempts:** 3-5
- **Total window:** 1-3 days

The retry is backoff + jitter.

## The "DLQ" pattern

For dead-letter:
- **Trigger:** Max retries exceeded
- **Contents:** Original payload + error + retry count
- **Retention:** 14 days
- **Alert:** On first entry (for financial)
- **Replay:** Manual, via dashboard

The DLQ is the safety net.

## The "DLQ properties" pattern

| Property | Main | DLQ |
|---|---|---|
| Retention | 4 days | 14 days |
| Auto-retry | Yes | No (manual) |
| Alert | On repeat fail | On first entry |
| Stored | Payload | Payload + error + retry count |

The DLQ is rich.

## The "manual replay" pattern

For replay:
- **Trigger:** Operator clicks "Retry" in dashboard
- **Rate-limit:** With delays (avoid burst)
- **Monitor:** DLQ depth dropping
- **Verify:** Business state correct

The replay is controlled.

## The "response code" pattern

For status codes:
| Response | Retry? | Action |
|---|---|---|
| 2xx | No | Ack; process async |
| 3xx | No | Register final URL |
| 400/401/403/404/410 | No | Fix endpoint; alert |
| 408 | Yes | Transient; backoff |
| 429 | Yes | Honor Retry-After |
| 5xx | Yes | Backoff + jitter |
| Connection | Yes | Trip circuit breaker |

The codes are interpreted.

## The "circuit breaker" pattern

For backpressure:
- **Trip:** N consecutive failures
- **Cool-down:** 60s
- **Half-open:** 1 request
- **Close:** On success

The breaker is the guard.

## The "rate limit outbound" pattern

For send rate:
- **Token bucket:** Per destination
- **Sliding window:** Per endpoint
- **Use same as inbound:** For consistency

The rate is controlled.

## The "timestamp + nonce" pattern

For replay:
- **Timestamp:** In signed payload
- **Tolerance:** 5 minutes (Stripe)
- **Nonce:** Random, track in cache
- **Reject:** If too old

The replay is blocked.

## The "secret rotation" pattern

For secret:
- **Store:** In secrets manager
- **Rotate:** Periodically (30-90 days)
- **Multiple active:** During rollout
- **Old secret:** Validate too

The secret rotates.

## The "PII in payload" pattern

For PII:
- **Avoid:** Don't log full payload
- **Store:** In encrypted S3 (security access only)
- **Log:** Reference ID only
- **Redact:** In any logs

The PII is minimized.

## The "per-provider config" pattern

For matrix:
- **Stripe:** 3-day retry, 5-min tolerance
- **Shopify:** 4-hour, 8 retries
- **Svix:** ~1 day, ~8 attempts
- **AWS SQS:** Until deleted

The config is per provider.

## The "observability" pattern

For metrics:
- **Delivery latency:** P50, P95
- **Retry count:** Distribution
- **DLQ depth:** Per queue
- **Failure rate:** Per event type
- **% processed in 30s:** SLI

The metrics are tracked.

## The "chaos test" pattern

For testing:
- **Tool:** `wrk`, `k6`
- **Inject:** Same event ID burst
- **Inject:** Network latency
- **Inject:** Receiver down
- **Verify:** No double processing

The chaos is tested.

## The "polling fallback" pattern

For delivery failure:
- **Treat:** Webhook as best-effort
- **Add:** Periodic API poll
- **Reconcile:** State via API
- **Cadence:** Every few minutes

The poll is the backup.

## The "no idempotency" anti-pattern

For no dedup:
- **Issue:** Double processing
- **Fix:** Atomic INSERT claim

The dedup is required.

## The "no signature" anti-pattern

For no signature:
- **Issue:** Anyone can send
- **Fix:** HMAC verify

The signature is required.

## The "synchronous process" anti-pattern

For sync:
- **Issue:** Timeout = double process
- **Fix:** Ack fast + async

The async is required.

## The "no DLQ" anti-pattern

For no DLQ:
- **Issue:** Lost events
- **Fix:** DLQ + replay

The DLQ is required.

## The "naive `==`" anti-pattern

For naive compare:
- **Issue:** Timing attack
- **Fix:** Constant-time

The compare is constant-time.

## The "JSON parse before verify" anti-pattern

For early parse:
- **Issue:** HMAC broken
- **Fix:** Verify raw body

The order is verify-first.

## The "webhook checklist" pattern

For checklist:
- [ ] Signature verified (raw body)
- [ ] Constant-time compare
- [ ] Timestamp tolerance (5 min)
- [ ] Secret in secrets manager
- [ ] Atomic INSERT claim
- [ ] Dedup TTL > retry window
- [ ] Fast 200/202 ack
- [ ] Async worker
- [ ] Transaction for business + claim
- [ ] Exponential backoff + jitter
- [ ] DLQ (14d retention)
- [ ] Manual replay UI
- [ ] Per-provider config
- [ ] No PII in logs
- [ ] Polling fallback

The checklist is 15.

## Verification
- **Test:** Same event_id → processed once
- **Test:** Signature fails → 400
- **Test:** Timeout → no double process
- **Test:** Max retries → DLQ
- **Audit:** Quarterly

## Gotchas
- **The "no idempotency" anti-pattern.** Atomic claim.
- **The "naive compare" anti-pattern.** Constant-time.
- **The "sync process" anti-pattern.** Fast ack + async.

## Related
- `patterns/api-gateway-comparison-2026.md`
- `patterns/idempotency-keys.md`
- `patterns/safe-deploy-checklist.md`
- `patterns/incident-response.md`
- `security/owasp-api-top-10-2023.md`
- Digital Applied: https://www.digitalapplied.com/blog/webhook-reliability-idempotency-retries-engineering-reference-2026
- Duskolicanin: https://www.duskolicanin.com/blog/webhook-reliability-idempotency-dlq-saas-2026
- Hyvo: https://hyvo.in/blog/webhook-architecture-best-practices-retries-idempotency-and-security-in-2026
