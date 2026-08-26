# Email Queue Priority Lanes with Cloudflare Queues and Workers

Date: 2026-08-23 / Author: example.com / Status: production

## Symptom / Use-case

Transactional emails (password resets, order confirmations) queue behind a bulk
newsletter broadcast and arrive minutes late, degrading UX. You need strict
priority separation so critical messages are never starved by marketing volume.

## Context

Cloudflare Queues are FIFO per binding. The solution is multiple Queue bindings—
one per priority tier—with a dispatcher Worker that routes incoming send requests
to the correct queue. Consumers are identical in code but bound to separate
queues, enabling per-tier throughput and retry budgets without a third-party
broker.

## Queue Binding Layout

`wrangler.toml`:

```toml
[[queues.producers]]
queue = "email-transactional"
binding = "Q_TRANSACTIONAL"

[[queues.producers]]
queue = "email-bulk"
binding = "Q_BULK"

[[queues.consumers]]
queue = "email-transactional"
max_batch_size = 10
max_batch_timeout = 1      # flush every 1 s for speed

[[queues.consumers]]
queue = "email-bulk"
max_batch_size = 100
max_batch_timeout = 30     # tolerate latency for bulk
max_retries = 5
```

## Dispatcher Worker (inbound routing)

```typescript
// src/dispatcher.ts
export interface EmailJob {
  to: string;
  subject: string;
  html: string;
  priority: "transactional" | "bulk";
}

interface Env {
  Q_TRANSACTIONAL: Queue<EmailJob>;
  Q_BULK: Queue<EmailJob>;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const job = await request.json<EmailJob>();
    if (!job.priority || !job.to) {
      return new Response("bad request", { status: 400 });
    }
    if (job.priority === "transactional") {
      await env.Q_TRANSACTIONAL.send(job);
    } else {
      await env.Q_BULK.send(job);
    }
    return new Response(JSON.stringify({ queued: job.priority }), {
      headers: { "Content-Type": "application/json" },
    });
  },
};
```

## Consumer Worker (shared logic, two bindings)

```typescript
// src/consumer.ts
import type { EmailJob } from "./dispatcher";

interface Env {
  RESEND_API_KEY: string;
}

async function sendViaResend(job: EmailJob, apiKey: string): Promise<void> {
  const res = await fetch("https://api.resend.com/emails", {
    method: "POST",
    headers: {
      Authorization: `Bearer ${apiKey}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ from: "no-reply@example.com", to: job.to,
                           subject: job.subject, html: job.html }),
  });
  if (!res.ok) throw new Error(`Resend ${res.status}`);
}

export default {
  async queue(batch: MessageBatch<EmailJob>, env: Env): Promise<void> {
    for (const msg of batch.messages) {
      try {
        await sendViaResend(msg.body, env.RESEND_API_KEY);
        msg.ack();
      } catch (err) {
        msg.retry({ delaySeconds: 30 });
      }
    }
  },
};
```

Deploy two Worker instances referencing the same `src/consumer.ts` but bound to
different queue consumers via separate `wrangler.toml` entries or `--config`
flags.

## Priority Classification Helper

```typescript
// src/classify.ts
type Priority = "transactional" | "bulk";

const TRANSACTIONAL_TRIGGERS = [
  "password-reset", "email-verification", "order-confirmation",
  "invoice", "security-alert", "magic-link",
];

export function classifyEmail(templateId: string): Priority {
  return TRANSACTIONAL_TRIGGERS.some((t) => templateId.includes(t))
    ? "transactional"
    : "bulk";
}
```

## Back-pressure Guard

```typescript
// src/dispatcher.ts (extended)
// Reject bulk sends if bulk queue depth > threshold via Analytics Engine
async function bulkBackpressureCheck(env: Env & { AE: AnalyticsEngineDataset }): Promise<boolean> {
  // Write a heartbeat; real depth requires Queues REST API or D1 counter
  // Simple approach: use a KV counter incremented on enqueue, decremented on ack
  return false; // placeholder – wire to your KV depth counter
}
```

## Anti-patterns

- **Single queue for all priorities** – transactional messages are starved during
  broadcast sends; set distinct `max_batch_size` and `max_batch_timeout` per tier.
- **Priority field ignored at consumer** – routing must happen at dispatch time,
  not inside the consumer; consumers cannot reorder messages once queued.
- **Same retry budget for transactional and bulk** – transactional should retry
  aggressively (short delay, high count); bulk can afford exponential backoff.

## Gotchas

- Cloudflare Queues do not support native message priority ordering within a
  single queue (2026-08). Tier separation via multiple bindings is the only
  supported approach.
- `max_retries` on the consumer binding is global per queue; per-message retry
  control requires catching errors inside the consumer and calling `msg.retry()`.
- Bulk queue consumers with large `max_batch_timeout` will hold messages in flight
  if the Worker is not responding; set a sensible `max_concurrency`.

## Verification

```bash
# Enqueue a transactional job
curl -X POST https://dispatcher.example.com/email \
  -H "Content-Type: application/json" \
  -d '{"to":"user@example.com","subject":"Reset","html":"<p>link</p>","priority":"transactional"}'

# Confirm delivery < 5 s via Resend dashboard or Analytics Engine custom event
wrangler tail --env production --format pretty
```

## Related

- `transactional-queue-cloudflare-queues.md`
- `email-retry-exponential-backoff.md`
- `email-batch-sending.md`
- `email-esp-failover-health-check-workers.md`

## Sources

- Cloudflare Queues docs: https://developers.cloudflare.com/queues/
- Queues consumer settings: https://developers.cloudflare.com/queues/reference/configuration/
- Resend API reference: https://resend.com/docs/api-reference/emails/send-email
