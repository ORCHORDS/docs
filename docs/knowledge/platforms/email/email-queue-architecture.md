# email-queue-architecture

**Issue:** Designing reliable email send queues to handle volume, retries, and failures
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Direct synchronous email sending fails under load and loses emails when ESP is unavailable.

## Pattern / Solution
Architecture:
1. API endpoint enqueues email job (BullMQ, SQS, RabbitMQ) and returns immediately.
2. Worker pool dequeues and sends via ESP API.
3. On ESP failure: retry with exponential backoff (see email-retry-exponential-backoff).
4. On exhausted retries: move to dead-letter queue, alert, log.
5. Track send status in DB: `queued -> sending -> sent | failed`.

BullMQ example:
```js
const emailQueue = new Queue('email');
await emailQueue.add('send', { to, subject, html }, {
  attempts: 5,
  backoff: { type: 'exponential', delay: 1000 }
});
```

## Gotchas
- Deduplication: use idempotency keys at ESP level to prevent double-send on retry.
- Worker concurrency should not exceed ESP rate limits.
- Monitor queue depth; growing depth indicates worker lag.
- Dead-letter queue must be monitored and actioned; emails there are never sent otherwise.

## Related
- email-retry-exponential-backoff, email-batch-sending, email-scheduling-patterns, ses-bounce-complaint-webhooks
