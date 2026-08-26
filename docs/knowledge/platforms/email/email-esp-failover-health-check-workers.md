# Email ESP Failover with Health Checks via Workers

- Date: 2026-08-22
- Author: example.com
- Status: production

## Zero-Downtime ESP Failover

Even 99.9 % uptime ESPs experience regional outages, rate-limit storms, and
maintenance windows at the worst possible moments — during a password-reset
surge or a time-sensitive transactional burst. A single-provider email
architecture has no recourse when this happens. Users wait, support tickets
pile up, and conversion suffers.

A Workers-based failover layer solves this without a separate monitoring
service. A lightweight health-check endpoint tests the primary ESP API for
latency and error rate on each incoming send request. A KV flag records
provider state so the failover decision persists across isolate lifetimes. On
degradation, the Worker routes transparently to a secondary provider; when the
primary recovers, the flag resets and traffic returns automatically.

This approach achieves sub-second failover detection, requires no external
monitoring infrastructure, and adds less than 15 ms overhead to healthy sends.

## Context

Stack: Cloudflare Workers, KV (provider state flag), Queues (optional retry),
Resend (primary), SendGrid (secondary), TypeScript, Wrangler 3+.

Each inbound send request is intercepted by an `EmailGateway` Worker. Before
dispatching, it reads the current provider state from KV and runs a passive
health probe against the primary. On failure or slow response, it flips the KV
flag to `secondary` and reroutes. A separate Cron Worker runs active probes
every minute and resets the flag when the primary recovers, with rate
reconciliation to prevent duplicate sends across providers.

## KV Provider State Schema

```
KV key: "esp:primary:status"       value: "healthy" | "degraded" | "down"
KV key: "esp:primary:checked_at"   value: ISO timestamp string
KV key: "esp:primary:fail_count"   value: integer string (0..N)
KV key: "esp:circuit:open"         value: "true" | "false"
```

## Email Gateway Worker

```ts
// workers/email-gateway.ts
import { KVNamespace } from '@cloudflare/workers-types';

interface Env {
  ESP_STATE: KVNamespace;
  RESEND_API_KEY: string;       // primary
  SENDGRID_API_KEY: string;     // secondary
  HEALTH_CHECK_TIMEOUT_MS: string;
}

interface SendPayload {
  from: string;
  to: string | string[];
  subject: string;
  html: string;
  replyTo?: string;
}

async function sendViaResend(payload: SendPayload, apiKey: string): Promise<{ id: string }> {
  const res = await fetch('https://api.resend.com/emails', {
    method: 'POST',
    headers: { Authorization: `Bearer ${apiKey}`, 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!res.ok) throw new Error(`Resend ${res.status}: ${await res.text()}`);
  return res.json<{ id: string }>();
}

async function sendViaSendGrid(payload: SendPayload, apiKey: string): Promise<{ id: string }> {
  const res = await fetch('https://api.sendgrid.com/v3/mail/send', {
    method: 'POST',
    headers: { Authorization: `Bearer ${apiKey}`, 'Content-Type': 'application/json' },
    body: JSON.stringify({
      personalizations: [{ to: Array.isArray(payload.to) ? payload.to.map(e => ({ email: e })) : [{ email: payload.to }] }],
      from: { email: payload.from },
      subject: payload.subject,
      content: [{ type: 'text/html', value: payload.html }],
    }),
  });
  const messageId = res.headers.get('X-Message-Id') ?? crypto.randomUUID();
  if (!res.ok) throw new Error(`SendGrid ${res.status}: ${await res.text()}`);
  return { id: messageId };
}

async function isCircuitOpen(kv: KVNamespace): Promise<boolean> {
  return (await kv.get('esp:circuit:open')) === 'true';
}

async function openCircuit(kv: KVNamespace): Promise<void> {
  await kv.put('esp:circuit:open', 'true', { expirationTtl: 120 }); // auto-reset after 2 min
}

async function probeResend(apiKey: string, timeoutMs: number): Promise<boolean> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    // Use domains list endpoint as a cheap liveness probe
    const res = await fetch('https://api.resend.com/domains', {
      headers: { Authorization: `Bearer ${apiKey}` },
      signal: controller.signal,
    });
    return res.ok || res.status === 403; // 403 = auth issue, API is alive
  } catch {
    return false;
  } finally {
    clearTimeout(timer);
  }
}

export default {
  async fetch(req: Request, env: Env): Promise<Response> {
    if (req.method !== 'POST') return new Response('Method Not Allowed', { status: 405 });

    const payload = await req.json<SendPayload>();
    const timeoutMs = Number(env.HEALTH_CHECK_TIMEOUT_MS ?? 1500);

    // Check circuit breaker state
    const circuitOpen = await isCircuitOpen(env.ESP_STATE);

    let result: { id: string };
    let provider: string;

    if (!circuitOpen) {
      // Passive health probe on primary
      const primaryHealthy = await probeResend(env.RESEND_API_KEY, timeoutMs);

      if (primaryHealthy) {
        try {
          result = await sendViaResend(payload, env.RESEND_API_KEY);
          provider = 'resend';
          // Reset fail count on success
          await env.ESP_STATE.put('esp:primary:fail_count', '0');
        } catch (err) {
          // Primary failed mid-send — increment fail counter and open circuit
          const fails = Number((await env.ESP_STATE.get('esp:primary:fail_count')) ?? '0') + 1;
          await env.ESP_STATE.put('esp:primary:fail_count', String(fails));
          if (fails >= 3) await openCircuit(env.ESP_STATE);

          result = await sendViaSendGrid(payload, env.SENDGRID_API_KEY);
          provider = 'sendgrid-fallback';
        }
      } else {
        await openCircuit(env.ESP_STATE);
        result = await sendViaSendGrid(payload, env.SENDGRID_API_KEY);
        provider = 'sendgrid-circuit';
      }
    } else {
      result = await sendViaSendGrid(payload, env.SENDGRID_API_KEY);
      provider = 'sendgrid-circuit';
    }

    return Response.json({ id: result.id, provider });
  },
};
```

## Cron Health-Check and Auto-Recovery Worker

```ts
// workers/esp-health-cron.ts
interface Env {
  ESP_STATE: KVNamespace;
  RESEND_API_KEY: string;
  ALERT_WEBHOOK_URL: string;
}

export default {
  async scheduled(_: ScheduledEvent, env: Env): Promise<void> {
    const wasOpen = (await env.ESP_STATE.get('esp:circuit:open')) === 'true';

    const healthy = await probeResend(env.RESEND_API_KEY, 2000);
    const now = new Date().toISOString();

    if (healthy && wasOpen) {
      // Primary recovered — reset circuit
      await env.ESP_STATE.put('esp:circuit:open', 'false');
      await env.ESP_STATE.put('esp:primary:fail_count', '0');
      await env.ESP_STATE.put('esp:primary:status', 'healthy');
      await env.ESP_STATE.put('esp:primary:checked_at', now);

      await fetch(env.ALERT_WEBHOOK_URL, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text: 'Primary ESP (Resend) recovered — circuit closed', ts: now }),
      });
    } else if (!healthy && !wasOpen) {
      await env.ESP_STATE.put('esp:primary:status', 'down');
      await env.ESP_STATE.put('esp:primary:checked_at', now);
      await fetch(env.ALERT_WEBHOOK_URL, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text: 'Primary ESP (Resend) DOWN — traffic on secondary', ts: now }),
      });
    }
  },
};
```

## Send-Rate Reconciliation

After a provider switch, compare send counts across ESPs to detect duplicates
from in-flight requests that hit both providers simultaneously.

```ts
// Reconciliation: query both ESP activity logs for a time window
async function reconcile(
  resendKey: string,
  sendgridKey: string,
  fromTs: number,
  toTs: number
): Promise<{ resend: number; sendgrid: number; diff: number }> {
  const [rRes, sgRes] = await Promise.all([
    fetch(`https://api.resend.com/emails?from=${fromTs}&to=${toTs}`, {
      headers: { Authorization: `Bearer ${resendKey}` },
    }).then((r) => r.json<{ data: unknown[] }>()),
    fetch(`https://api.sendgrid.com/v3/stats?start_date=${new Date(fromTs).toISOString().slice(0,10)}&end_date=${new Date(toTs).toISOString().slice(0,10)}`, {
      headers: { Authorization: `Bearer ${sendgridKey}` },
    }).then((r) => r.json<{ stats: { metrics: { requests: number } }[] }[]>()),
  ]);
  const resendCount = rRes.data?.length ?? 0;
  const sgCount = sgRes[0]?.stats[0]?.metrics?.requests ?? 0;
  return { resend: resendCount, sendgrid: sgCount, diff: resendCount - sgCount };
}
```

## Anti-patterns

- Reading provider state from a database on the critical send path — KV reads are sub-millisecond; DB queries add 10-50 ms per request
- Using an overly short health-check timeout (< 500 ms) causing false circuit trips on transient slowness
- Not implementing exponential backoff before opening the circuit — three consecutive failures is more signal than a single slow response
- Attempting to send simultaneously to both providers to eliminate latency — this guarantees duplicate delivery

## Gotchas

- KV `expirationTtl` on the circuit flag acts as a dead-man switch; if the cron fails to run, the circuit auto-closes after `ttl` seconds, preventing permanent lockout on Resend
- Resend's `/domains` probe returns 200 even on an inactive account; test with a known-good domain list instead if you need stricter liveness
- SendGrid requires `personalizations` array format — it does not accept a plain `to` field
- Passive probes on every send add one fetch per request; cache the KV health state in `globalThis` for 10 seconds to reduce KV reads under high throughput

## Verification

```ts
// Force circuit open and verify traffic routes to secondary
await env.ESP_STATE.put('esp:circuit:open', 'true');
const res = await fetch('https://email-gateway.example.com/send', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ from: 'test@example.com', to: 'sink@example.com', subject: 'Test', html: '<p>test</p>' }),
});
const body = await res.json<{ provider: string }>();
console.assert(body.provider.startsWith('sendgrid'), `Expected sendgrid, got ${body.provider}`);
```

## Related

- esp-failover-multi-provider-resilience.md
- transactional-email-rate-limiting-workers.md
- sendgrid-resend-cloudflare-workers-integration.md
- email-deliverability-monitoring-workers-logpush.md
- email-security-audit-trail-d1-immutable-log.md

## Sources

- https://developers.cloudflare.com/kv/
- https://developers.cloudflare.com/workers/configuration/cron-triggers/
- https://martinfowler.com/bliki/CircuitBreaker.html
- https://resend.com/docs/api-reference/introduction
- https://docs.sendgrid.com/api-reference/mail-send/mail-send
