# email-batch-sending

**Issue:** Sending large volumes of email efficiently and within ESP rate limits
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Sending to 100k+ recipients requires batching, rate limiting, and progress tracking to avoid failures.

## Pattern / Solution
1. Chunk recipients into batches of 500-1000:
```js
async function sendBatch(recipients) {
  const chunks = chunk(recipients, 500);
  for (const batch of chunks) {
    await Promise.all(batch.map(r => emailQueue.add('send', r)));
    await sleep(1000); // respect rate limits
  }
}
```
2. Track progress: `sent`, `failed`, `pending` counts in campaign record.
3. Pause/resume capability for large campaigns.
4. Monitor bounce/complaint rates during send; pause if thresholds exceeded.
5. Use ESP bulk API endpoints where available (SendGrid `/v3/mail/send` with `personalizations`).

## Gotchas
- Sending too fast from a new IP triggers spam filters; respect warming schedule.
- ESPs have both per-second and per-day rate limits; check both.
- Failed sends should requeue individually, not re-send the whole batch.
- Never send the same campaign twice to the same list; check campaign status before starting.

## Related
- email-queue-architecture, ip-warming-strategy, email-scheduling-patterns, email-retry-exponential-backoff
