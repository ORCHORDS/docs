# ESP Failover and Multi-Provider Email Resilience

- **Date**: 2026-08-22
- **Author**: example.com
- **Status**: production

## Symptom / Use-case

A single email service provider (ESP) outage — Resend, SendGrid, Postmark, AWS SES —
halts transactional email delivery entirely. Password resets, order confirmations, and
OTP codes queue up or fail silently. Teams discover the problem through support tickets,
not monitoring. A multi-provider failover strategy eliminates this single point of failure
by routing sends through a primary ESP and automatically retrying via a secondary when
the primary returns a non-retryable HTTP error or times out.

## Context

Major ESPs achieve 99.9 % uptime SLAs, but scheduled maintenance windows, regional
outages, and rate-limit storms can all interrupt delivery at critical moments.
Cloudflare Workers sit in an excellent position to implement transparent failover: they
run at the edge with sub-millisecond routing overhead, maintain no persistent process
state that could stall, and integrate natively with Queues for reliable retry semantics.
A Worker can attempt delivery against a primary provider and, on failure, immediately
retry against a secondary — all within a single request lifecycle or as a durable
Queue-backed job.

## Architecture Overview

```
[Application] ──POST /send──► [Email Gateway Worker]
                                      │
                          ┌───────────▼───────────┐
                          │  Try Primary (Resend)  │
                          └───────────┬───────────┘
                                      │ non-2xx / timeout
                          ┌───────────▼───────────┐
                          │  Try Secondary (SES)   │
                          └───────────┬───────────┘
                                      │ non-2xx / timeout
                          ┌───────────▼───────────┐
                          │  Enqueue to CF Queue   │  ← dead-letter for ops review
                          └───────────────────────┘
```

Both providers must be pre-configured with valid sending domains, DKIM keys, and
verified FROM addresses. Shared sending domains are simplest; per-provider subdomains
(e.g. `mail.example.com` via Resend, `txn.example.com` via SES) avoid DMARC alignment
issues if `From:` domain differs from the envelope sender.

## Worker Implementation

```typescript
// src/email-gateway.ts
interface Env {
  RESEND_API_KEY: string;
  SES_ACCESS_KEY: string;
  SES_SECRET_KEY: string;
  SES_REGION: string;
  EMAIL_DLQ: Queue;   // Cloudflare Queue for dead letters
}

interface SendRequest {
  from: string;
  to: string[];
  subject: string;
  html: string;
  text?: string;
  idempotency_key?: string; // callers must supply to avoid duplicates on retry
}

async function sendViaResend(req: SendRequest, apiKey: string): Promise<boolean> {
  const res = await fetch('https://api.resend.com/emails', {
    method: 'POST',
    headers: {
      'Authorization': `Bearer ${apiKey}`,
      'Content-Type': 'application/json',
      'Idempotency-Key': req.idempotency_key ?? crypto.randomUUID(),
    },
    body: JSON.stringify({
      from: req.from,
      to: req.to,
      subject: req.subject,
      html: req.html,
      text: req.text,
    }),
    signal: AbortSignal.timeout(8_000),
  });
  return res.ok;
}

async function sendViaSES(req: SendRequest, env: Env): Promise<boolean> {
  // AWS SES v2 SendEmail via REST — sign with AWS Signature v4
  const body = JSON.stringify({
    FromEmailAddress: req.from,
    Destination: { ToAddresses: req.to },
    Content: {
      Simple: {
        Subject: { Data: req.subject },
        Body: {
          Html: { Data: req.html },
          Text: { Data: req.text ?? '' },
        },
      },
    },
  });
  const url = `https://email.${env.SES_REGION}.amazonaws.com/v2/email/outbound-emails`;
  const signed = await signAWSRequest({ url, body, env });
  const res = await fetch(url, {
    method: 'POST',
    headers: signed.headers,
    body,
    signal: AbortSignal.timeout(8_000),
  });
  return res.ok;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    if (request.method !== 'POST') return new Response('Method Not Allowed', { status: 405 });
    const payload: SendRequest = await request.json();

    const primaryOk = await sendViaResend(payload, env.RESEND_API_KEY).catch(() => false);
    if (primaryOk) return new Response(JSON.stringify({ provider: 'resend' }), { status: 202 });

    const secondaryOk = await sendViaSES(payload, env).catch(() => false);
    if (secondaryOk) return new Response(JSON.stringify({ provider: 'ses' }), { status: 202 });

    // Both failed — push to dead-letter queue for operator review
    await env.EMAIL_DLQ.send(payload, { contentType: 'json' });
    return new Response(JSON.stringify({ queued: true }), { status: 202 });
  },
};
```

`AbortSignal.timeout(8_000)` keeps the Worker within Cloudflare's CPU time limits and
ensures the secondary provider attempt still fits inside a single request.

## Provider Health Circuit Breaker

A simple circuit breaker using KV prevents hammering a known-down provider on every
request:

```typescript
async function isProviderHealthy(kv: KVNamespace, provider: string): Promise<boolean> {
  const tripped = await kv.get(`circuit:${provider}`);
  return tripped === null; // null = healthy; any value = tripped
}

async function recordFailure(kv: KVNamespace, provider: string): Promise<void> {
  // Open circuit for 5 minutes on failure
  await kv.put(`circuit:${provider}`, '1', { expirationTtl: 300 });
}
```

After five minutes the KV TTL expires and the circuit auto-resets. A scheduled Worker
cron can probe provider health endpoints and call `kv.delete()` to close the circuit
early when they recover.

## Idempotency and Duplicate Prevention

When both providers appear healthy but the network drops the response, the Worker may
retry and send duplicate messages. Callers must supply a stable `idempotency_key`
derived from the triggering event (e.g. `sha256(userId + eventType + eventId)`).

- Resend accepts `Idempotency-Key` headers natively.
- SES uses `ClientRequestToken` in the request body.
- For providers without native idempotency, record the key in D1 before sending and
  check for it on receipt to suppress re-sends.

```sql
CREATE TABLE sent_emails (
  idempotency_key TEXT PRIMARY KEY,
  provider        TEXT NOT NULL,
  sent_at         INTEGER NOT NULL,  -- Unix ms
  to_address      TEXT NOT NULL
);
```

## Anti-patterns

- **Parallel scatter-gather**: sending to both providers simultaneously and ignoring the
  duplicate. Users receive two identical emails. Always try sequentially.
- **Infinite retry loop inside Worker**: Cloudflare Workers have a 30-second wall-clock
  CPU limit. Retry logic must be offloaded to Queues, not inlined.
- **Sharing the same FROM domain across providers without DMARC alignment**: if provider
  A rewrites the envelope sender to a subdomain, DMARC `From:` alignment fails.
  Verify each provider's envelope sender matches or aligns with your `From:` domain.
- **No dead-letter visibility**: silently dropping emails that both providers reject
  means lost transactional messages. Always enqueue to a DLQ and alert on it.

## Gotchas

- **SES sandbox mode**: new SES accounts only permit verified recipient addresses.
  Promote to production before using SES as a failover target in production.
- **Resend rate limits**: Resend enforces per-second and per-day rate limits by plan.
  A spike that trips the primary because of rate limiting will also exceed the secondary
  if both share the same volume.
- **DKIM selector propagation**: each provider issues its own DKIM keys. Both sets of
  DNS `TXT` records must be live before routing any volume through that provider.
- **Bounce/complaint callbacks diverge**: each provider has separate webhook URLs for
  bounce and complaint events. Normalize these into a single suppression list handler
  (see `suppression-list-management.md`) before routing to both providers.

## Verification

1. Force a Resend failure by temporarily setting `RESEND_API_KEY` to an invalid value.
   Confirm the Worker falls through to SES and returns `{ "provider": "ses" }`.
2. Force both to fail and confirm the DLQ receives the message via `wrangler tail`.
3. Check that duplicate idempotency keys are rejected by replaying the same request twice
   and observing that only one email arrives.
4. Validate DKIM signatures from both providers using `mail-tester.com` or
   `mxtoolbox.com/dkim` with selector-specific lookups.

## Related

- `suppression-list-management.md`
- `email-retry-exponential-backoff.md`
- `email-queue-architecture.md`
- `dkim-record-setup.md`
- `dmarc-policy-setup.md`

## Sources

- Resend API docs: https://resend.com/docs/api-reference/idempotency
- AWS SES v2 REST API: https://docs.aws.amazon.com/ses/latest/APIReference-V2/
- Cloudflare Queues docs: https://developers.cloudflare.com/queues/
- Cloudflare Workers CPU limits: https://developers.cloudflare.com/workers/platform/limits/
