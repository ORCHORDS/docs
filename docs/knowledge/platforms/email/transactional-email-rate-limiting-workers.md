# transactional-email-rate-limiting-workers

**Issue:** Per-user email quotas and burst protection for transactional
           email on anonymous platforms using Cloudflare Workers + KV
**Date:** 2026-08-22
**Author:** example.com
**Status:** published

## Symptom

Anonymous platforms (where users may not have verified identities)
are abused to send mass notifications or trigger unlimited transactional
emails via scripted account creation.  Without rate limiting, a single
actor can exhaust ESP sending reputation, trigger abuse complaints,
and spike costs in minutes.

## Context

Cloudflare Workers intercept every email dispatch call before it
reaches the ESP (Resend, Mailgun, SES, etc.).  KV provides a fast,
globally consistent counter store with TTL-based expiration.  The
combination enables per-user, per-action, and per-IP quotas enforced
at the edge without a separate rate-limit service.

## Quota model

Design quotas at three levels.  All three must pass for a send to
proceed.

```
┌───────────────────────┬──────────────────┬─────────────────┐
│ Level                 │ Key              │ Default limit   │
├───────────────────────┼──────────────────┼─────────────────┤
│ Per user/day          │ rl:u:<uid>:d     │ 20 emails/day   │
│ Per user/hour (burst) │ rl:u:<uid>:h     │  5 emails/hour  │
│ Per IP/hour           │ rl:ip:<ip>:h     │ 10 emails/hour  │
└───────────────────────┴──────────────────┴─────────────────┘
```

TTLs: day keys expire in 86 400 s; hour keys expire in 3 600 s.
Use atomic KV operations to avoid race conditions on concurrent
requests from the same user.

## Workers rate-limit implementation

```js
const QUOTAS = {
  userDay:  { prefix: 'rl:u:', suffix: ':d', limit: 20, ttl: 86400 },
  userHour: { prefix: 'rl:u:', suffix: ':h', limit:  5, ttl:  3600 },
  ipHour:   { prefix: 'rl:ip:', suffix: ':h', limit: 10, ttl:  3600 },
};

async function checkAndIncrement(kv, key, limit, ttl) {
  const raw = await kv.get(key);
  const count = raw ? parseInt(raw, 10) : 0;
  if (count >= limit) return { allowed: false, count };

  // Increment; reset TTL only on first write to avoid sliding window
  await kv.put(key, String(count + 1), {
    expirationTtl: raw ? undefined : ttl,
  });
  return { allowed: true, count: count + 1 };
}

export async function enforceQuotas(userId, ip, emailType, env) {
  const dayKey  = `rl:u:${userId}:d`;
  const hourKey = `rl:u:${userId}:h`;
  const ipKey   = `rl:ip:${ip}:h`;

  const [dayResult, hourResult, ipResult] = await Promise.all([
    checkAndIncrement(env.RATE_KV, dayKey,  20, 86400),
    checkAndIncrement(env.RATE_KV, hourKey,  5,  3600),
    checkAndIncrement(env.RATE_KV, ipKey,   10,  3600),
  ]);

  if (!dayResult.allowed)  return { blocked: true, reason: 'daily_quota' };
  if (!hourResult.allowed) return { blocked: true, reason: 'hourly_burst' };
  if (!ipResult.allowed)   return { blocked: true, reason: 'ip_burst' };

  return { blocked: false };
}
```

## Per-action email type quotas

Different email types warrant different limits.  Password resets and
OTPs carry abuse risk; newsletters and receipts are user-initiated.

```
┌──────────────────────────┬────────────┬──────────────────────┐
│ Email type               │ Limit      │ Window               │
├──────────────────────────┼────────────┼──────────────────────┤
│ OTP / magic link         │  5         │ per user per hour    │
│ Password reset           │  3         │ per user per 15 min  │
│ Notification (digest)    │ 24         │ per user per day     │
│ Receipt / invoice        │ 50         │ per user per day     │
│ Marketing (opted-in)     │  1         │ per campaign/user    │
└──────────────────────────┴────────────┴──────────────────────┘
```

Encode the email type in the KV key:

```js
const typeKey = `rl:u:${userId}:t:${emailType}`;
```

## Mobile notification email patterns

Mobile push is unavailable for anonymous users who have not installed
the app.  Transactional email becomes the notification channel, which
creates distinct traffic shapes:

- **Burst on events**: A product action (e.g. 10 people react to a
  post) generates 10 emails in seconds.  Use a digest queue: batch
  events for up to 5 minutes before dispatching one email with a
  summary.  The KV counter still applies to the batched send, not
  each raw event.

- **Offline-spike re-delivery**: When a user's mobile device comes
  back online after hours offline, queued server events may flush
  simultaneously.  Rate limiting should apply per-batch-job, not per
  event; hold additional batches in a Queues job with exponential
  delay.

- **Unsubscribe from mobile**: Mobile email clients render the
  List-Unsubscribe one-click button (RFC 8058) differently across
  iOS Mail, Gmail app, and Samsung Mail.  Track unsubscribes via
  webhook rather than relying on header parsing by the client, and
  immediately set a KV flag that short-circuits the quota check:

```js
const unsub = await env.RATE_KV.get(`unsub:${userId}:${emailType}`);
if (unsub) return { blocked: true, reason: 'unsubscribed' };
```

## Abuse prevention for anonymous platforms

Anonymous accounts (no verified phone or payment) should have stricter
quotas applied automatically until they pass a trust signal:

```js
async function getQuotaMultiplier(userId, env) {
  const trust = await env.RATE_KV.get(`trust:${userId}`, {
    type: 'json'
  });
  if (!trust) return 0.25;           // anonymous: 25% of quota
  if (trust.emailVerified) return 0.5;
  if (trust.phoneVerified) return 1.0;
  if (trust.paymentVerified) return 2.0;
  return 0.25;
}
```

Log every blocked send attempt with the user ID, IP, email type, and
reason to a Logpush-compatible sink for downstream abuse review.

## Anti-patterns

- Using a single global counter per domain — lets one user deplete the
  quota for all users simultaneously.
- Resetting the TTL on every increment — creates a sliding window that
  never expires for active abusers; set TTL only on first write.
- Blocking without logging — makes abuse investigations impossible;
  always emit a structured log entry on each rejection.
- Raising quotas to silence complaints without investigating the
  traffic — the right fix is digest batching, not a higher cap.
- Checking the quota after queuing the send — the job executor must
  check before dispatching; checking after a queue pop wastes queue
  capacity and delays the error to the user.

## Gotchas

- KV is eventually consistent.  Under very high concurrency (>100
  req/s for a single key) the counter can over-count slightly because
  `get → put` is not atomic.  Use Durable Objects for strict
  atomicity when the quota is security-critical (e.g. OTP sends).
- Workers KV `put` with no `expirationTtl` creates a persistent key;
  forgetting the TTL on day keys means they never expire and the user
  is permanently blocked.
- `Promise.all` across three KV calls can allow all three to succeed
  even if you intend to short-circuit.  Roll back increments on
  downstream failure by tracking which keys were incremented and
  decrementing them in the error handler.

## Verification

```bash
# Simulate quota exhaustion
for i in $(seq 1 6); do
  curl -X POST https://api.example.com/email/send \
       -H "X-User-Id: u_test" \
       -d '{"type":"otp","to":"test@example.com"}'
done
# 6th request should return 429 with reason "hourly_burst"

# Check KV state
wrangler kv:key get --binding RATE_KV "rl:u:u_test:h"

# Verify TTL was set (non-null expiration in list output)
wrangler kv:key list --binding RATE_KV --prefix "rl:u:u_test"
```

## Related

- `documentation/docs/policies/email/cloudflare-email-routing-workers.md`
- `documentation/docs/policies/email/email-frequency-capping.md`
- `documentation/docs/policies/email/notification-email-patterns.md`
- `documentation/docs/policies/email/email-abuse-prevention.md`
- `documentation/docs/policies/email/email-queue-architecture.md`

## Source URLs

- https://developers.cloudflare.com/kv/api/write-key-value-pairs/
- https://developers.cloudflare.com/queues/
- https://developers.cloudflare.com/durable-objects/
- https://datatracker.ietf.org/doc/html/rfc8058  (List-Unsubscribe POST)
