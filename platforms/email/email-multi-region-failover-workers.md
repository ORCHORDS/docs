# Email Multi-Region Failover with Cloudflare Workers

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

Transactional email must be delivered even when a primary ESP (MailChannels, SendGrid,
Resend) is experiencing an outage or elevated error rate. A single-provider setup
silently drops or defers critical emails (password resets, billing alerts, OTP codes)
during provider incidents. The example project platform needs a Workers-native failover layer
that automatically routes email through a secondary provider when the primary degrades,
with circuit-breaker state stored in KV so all edge PoPs share the same view.

---

## Context

Cloudflare Workers run at the edge globally. KV writes propagate to all PoPs within
~60 seconds, making it suitable for shared circuit-breaker state. Durable Objects
offer stronger consistency for the health-check loop but require a jurisdiction pin;
KV with a short TTL is sufficient for the use case and simpler to operate.

Provider options for failover:
- **Primary**: MailChannels (zero-egress within Cloudflare network)
- **Secondary**: Resend (REST API, generous free tier)
- **Tertiary**: SendGrid (SMTP or Web API)

The circuit breaker tracks consecutive failures per provider in KV and opens the
circuit (skipping that provider) when the threshold is exceeded.

---

## KV Schema (Circuit Breaker State)

```
Key:   cb:{provider}           e.g. "cb:mailchannels"
Value: JSON { state, failures, openedAt, halfOpenAfter }
TTL:   300 s (auto-resets the circuit if KV TTL expires and provider recovers)

Key:   cb:send_log:{requestId}
Value: JSON { provider, status, ts }
TTL:   3600 s (for deduplication)
```

---

## Circuit Breaker Implementation

```typescript
// src/failover/circuit-breaker.ts
import type { KVNamespace } from '@cloudflare/workers-types';

type CircuitState = 'closed' | 'open' | 'half-open';

interface CircuitData {
  state: CircuitState;
  failures: number;
  openedAt: string | null;
  halfOpenAfter: string | null;
}

const FAILURE_THRESHOLD = 3;
const HALF_OPEN_AFTER_MS = 60_000; // 1 minute

async function readCircuit(kv: KVNamespace, provider: string): Promise<CircuitData> {
  const raw = await kv.get(`cb:${provider}`);
  if (!raw) return { state: 'closed', failures: 0, openedAt: null, halfOpenAfter: null };
  return JSON.parse(raw) as CircuitData;
}

export async function isAvailable(kv: KVNamespace, provider: string): Promise<boolean> {
  const data = await readCircuit(kv, provider);
  if (data.state === 'closed') return true;
  if (data.state === 'open') {
    if (data.halfOpenAfter && new Date(data.halfOpenAfter) <= new Date()) {
      // Transition to half-open: allow one probe
      await kv.put(
        `cb:${provider}`,
        JSON.stringify({ ...data, state: 'half-open' }),
        { expirationTtl: 300 },
      );
      return true;
    }
    return false;
  }
  // half-open: allow through
  return true;
}

export async function recordSuccess(kv: KVNamespace, provider: string): Promise<void> {
  await kv.put(
    `cb:${provider}`,
    JSON.stringify({ state: 'closed', failures: 0, openedAt: null, halfOpenAfter: null }),
    { expirationTtl: 300 },
  );
}

export async function recordFailure(kv: KVNamespace, provider: string): Promise<void> {
  const data = await readCircuit(kv, provider);
  const failures = data.failures + 1;

  if (failures >= FAILURE_THRESHOLD) {
    const now = new Date();
    await kv.put(
      `cb:${provider}`,
      JSON.stringify({
        state:         'open',
        failures,
        openedAt:      now.toISOString(),
        halfOpenAfter: new Date(now.getTime() + HALF_OPEN_AFTER_MS).toISOString(),
      }),
      { expirationTtl: 300 },
    );
  } else {
    await kv.put(
      `cb:${provider}`,
      JSON.stringify({ ...data, failures }),
      { expirationTtl: 300 },
    );
  }
}
```

---

## Provider Adapters

```typescript
// src/failover/providers.ts

export interface SendPayload {
  to: string;
  from: string;
  subject: string;
  html: string;
  text: string;
  requestId: string;
}

export async function sendViaMailChannels(p: SendPayload): Promise<void> {
  const res = await fetch('https://api.mailchannels.net/tx/v1/send', {
    method:  'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({
      personalizations: [{ to: [{ email: p.to }] }],
      from:    { email: p.from },
      subject: p.subject,
      content: [
        { type: 'text/plain', value: p.text },
        { type: 'text/html',  value: p.html  },
      ],
    }),
  });
  if (!res.ok) {
    const body = await res.text();
    throw new Error(`MailChannels ${res.status}: ${body}`);
  }
}

export async function sendViaResend(
  p: SendPayload,
  apiKey: string,
): Promise<void> {
  const res = await fetch('https://api.resend.com/emails', {
    method:  'POST',
    headers: {
      'content-type': 'application/json',
      authorization:  `Bearer ${apiKey}`,
    },
    body: JSON.stringify({
      to:      [p.to],
      from:    p.from,
      subject: p.subject,
      html:    p.html,
      text:    p.text,
    }),
  });
  if (!res.ok) {
    const body = await res.text();
    throw new Error(`Resend ${res.status}: ${body}`);
  }
}

export async function sendViaSendGrid(
  p: SendPayload,
  apiKey: string,
): Promise<void> {
  const res = await fetch('https://api.sendgrid.com/v3/mail/send', {
    method:  'POST',
    headers: {
      'content-type': 'application/json',
      authorization:  `Bearer ${apiKey}`,
    },
    body: JSON.stringify({
      personalizations: [{ to: [{ email: p.to }] }],
      from:    { email: p.from },
      subject: p.subject,
      content: [
        { type: 'text/plain', value: p.text },
        { type: 'text/html',  value: p.html  },
      ],
    }),
  });
  if (!res.ok) {
    const body = await res.text();
    throw new Error(`SendGrid ${res.status}: ${body}`);
  }
}
```

---

## Failover Orchestrator

```typescript
// src/failover/send.ts
import type { KVNamespace } from '@cloudflare/workers-types';
import {
  isAvailable, recordSuccess, recordFailure,
} from './circuit-breaker';
import {
  sendViaMailChannels, sendViaResend, sendViaSendGrid,
  type SendPayload,
} from './providers';

export interface Env {
  EMAIL_CB: KVNamespace;
  RESEND_API_KEY: string;
  SENDGRID_API_KEY: string;
}

type Provider = 'mailchannels' | 'resend' | 'sendgrid';

const PROVIDER_ORDER: Provider[] = ['mailchannels', 'resend', 'sendgrid'];

async function attempt(
  provider: Provider,
  payload: SendPayload,
  env: Env,
): Promise<void> {
  switch (provider) {
    case 'mailchannels': return sendViaMailChannels(payload);
    case 'resend':       return sendViaResend(payload, env.RESEND_API_KEY);
    case 'sendgrid':     return sendViaSendGrid(payload, env.SENDGRID_API_KEY);
  }
}

export async function sendWithFailover(
  payload: SendPayload,
  env: Env,
): Promise<{ provider: Provider; attempts: number }> {
  let lastError: unknown;

  for (const provider of PROVIDER_ORDER) {
    const ok = await isAvailable(env.EMAIL_CB, provider);
    if (!ok) {
      console.log(`[failover] ${provider} circuit open, skipping`);
      continue;
    }

    try {
      await attempt(provider, payload, env);
      await recordSuccess(env.EMAIL_CB, provider);
      return { provider, attempts: PROVIDER_ORDER.indexOf(provider) + 1 };
    } catch (err) {
      console.error(`[failover] ${provider} failed:`, err);
      await recordFailure(env.EMAIL_CB, provider);
      lastError = err;
    }
  }

  throw new Error(`All email providers failed. Last error: ${lastError}`);
}
```

---

## Worker Entry Point

```typescript
// src/index.ts
import { sendWithFailover } from './failover/send';
import type { Env } from './failover/send';

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    if (request.method !== 'POST') return new Response('Method Not Allowed', { status: 405 });

    const payload = await request.json<{
      to: string; from: string; subject: string;
      html: string; text: string;
    }>();

    const requestId = crypto.randomUUID();

    const result = await sendWithFailover({ ...payload, requestId }, env);

    return Response.json({
      ok: true,
      requestId,
      provider:   result.provider,
      attempts:   result.attempts,
    });
  },
};
```

---

## Health Dashboard Query

```typescript
// src/failover/status.ts
import type { KVNamespace } from '@cloudflare/workers-types';

const PROVIDERS = ['mailchannels', 'resend', 'sendgrid'] as const;

export async function getHealthStatus(kv: KVNamespace) {
  return Object.fromEntries(
    await Promise.all(
      PROVIDERS.map(async (p) => {
        const raw = await kv.get(`cb:${p}`);
        return [p, raw ? JSON.parse(raw) : { state: 'closed', failures: 0 }];
      }),
    ),
  );
}
```

---

## Anti-patterns

- **Retrying the same provider on transient 429 / 503** — this burns the circuit-breaker
  threshold on rate-limit errors rather than true failures. Check the response status
  before calling `recordFailure`; only record on 5xx or network errors.
- **Using D1 for circuit-breaker state** — D1 writes go to a primary region and
  replicate asynchronously; under high load the breaker state may be stale. KV with
  a short TTL is faster for this pattern.
- **Sending to all providers simultaneously** — defeats the purpose of a circuit breaker
  and risks duplicate delivery. Always try providers in order, stopping at first success.
- **Not logging which provider delivered** — without this, support cannot investigate
  delivery failures by correlating with provider dashboards.

---

## Gotchas

- MailChannels is bound to the Cloudflare network and has no API key; it can only be
  called from within a Cloudflare Worker. Resend and SendGrid require API keys stored
  as Worker secrets.
- KV `expirationTtl` resets on every write; a closed circuit that is constantly
  re-closed never expires. The 300 s TTL is only relevant when a write stops occurring
  (e.g. no traffic), acting as a passive circuit reset.
- Cloudflare's `subrequest` limit is 1,000 per Worker invocation; the failover chain
  consumes 1–3 subrequests per send depending on the path taken.
- If MailChannels returns 202 (accepted) but later bounces, the circuit breaker won't
  see that failure at send time. Wire up the MailChannels webhook to call
  `recordFailure` asynchronously.

---

## Verification

```bash
# Force MailChannels circuit open by setting KV directly
wrangler kv key put --binding=EMAIL_CB cb:mailchannels \
  '{"state":"open","failures":3,"openedAt":"2026-08-23T00:00:00Z","halfOpenAfter":"2099-01-01T00:00:00Z"}'

# Send a test email — should route via Resend
curl -X POST https://your-worker.workers.dev/ \
  -H "content-type: application/json" \
  -d '{"to":"test@example.com","from":"hello@example project.com","subject":"Test","html":"<p>Hi</p>","text":"Hi"}'

# Confirm the provider field in the response is "resend"
# Restore normal state
wrangler kv key delete --binding=EMAIL_CB cb:mailchannels
```

---

## Related

- `email-esp-failover-health-check-workers.md`
- `esp-failover-multi-provider-resilience.md`
- `email-retry-exponential-backoff.md`
- `email-transactional-idempotency-workers-d1.md`
- `transactional-email-dead-letter-queue-workers.md`

---

## Sources

- Martin Fowler — Circuit Breaker pattern: https://martinfowler.com/bliki/CircuitBreaker.html
- Cloudflare KV docs — https://developers.cloudflare.com/kv/
- MailChannels Send API — https://api.mailchannels.net/tx/v1/documentation
- Resend API — https://resend.com/docs/api-reference/emails/send-email
- SendGrid Mail Send — https://docs.sendgrid.com/api-reference/mail-send/mail-send
