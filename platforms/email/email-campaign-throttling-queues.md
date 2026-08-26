# Bulk Email Campaign Throttling with Cloudflare Queues

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

Sending a campaign blast to 500 000 subscribers in one go saturates ESP rate
limits, spikes IP reputation signals, and triggers abuse filters at receiving mail
servers. The desired behaviour is a smooth ramp: start at a low send rate,
increase if complaint and bounce rates stay healthy, and pause automatically if
thresholds are breached.

## Context

Cloudflare Queues provide the necessary flow-control primitives: `max_batch_size`,
`max_concurrency`, and per-message `delaySeconds`. A Campaign Controller Worker
splits the recipient list into waves, enqueues them with staggered delays, and
monitors a health KV key before each wave. A Queue Consumer Worker performs the
actual sends. A Cron Trigger re-evaluates health every minute and pauses or
resumes the queue consumer via the Cloudflare API.

## Architecture

```
Campaign Controller (fetch trigger)
  → splits recipients into waves
  → enqueues wave-0 immediately, wave-1 with delay, …
       ↓ Cloudflare Queue: campaign-outbox
Campaign Consumer (queue trigger)
  → checks health gate in KV
  → sends batch via MailChannels
  → writes per-batch metrics to Analytics Engine
       ↓
Health Monitor (cron: * * * * *)
  → reads AE complaint/bounce rates
  → sets KV health gate: "go" | "pause" | "stop"
```

## Queue & Cron Configuration (wrangler.jsonc)

```jsonc
{
  "name": "campaign-consumer",
  "main": "src/index.ts",
  "compatibility_date": "2025-01-01",

  "queues": {
    "producers": [
      { "queue": "campaign-outbox", "binding": "CAMPAIGN_QUEUE" }
    ],
    "consumers": [
      {
        "queue": "campaign-outbox",
        "max_batch_size": 50,
        "max_batch_timeout": 10,
        "max_retries": 3,
        "dead_letter_queue": "campaign-dlq",
        "max_concurrency": 2   // 2 invocations × 50 messages = 100 sends/tick
      }
    ]
  },

  "triggers": {
    "crons": ["* * * * *"]     // health monitor fires every minute
  },

  "kv_namespaces": [
    { "binding": "CAMPAIGN_KV", "id": "..." }
  ],

  "analytics_engine_datasets": [
    { "binding": "EMAIL_AE", "dataset": "email_deliverability" }
  ]
}
```

## Campaign Controller: Enqueuing Waves

```typescript
// controller/index.ts
export interface CampaignJob {
  campaignId: string;
  recipientEmail: string;
  wave: number;
  subject: string;
  templateId: string;
}

const WAVE_SIZE = 5_000;        // recipients per wave
const WAVE_DELAY_SECONDS = 300; // 5 min between waves

export async function launchCampaign(
  campaignId: string,
  recipients: string[],
  subject: string,
  templateId: string,
  env: Env,
): Promise<void> {
  // Mark campaign as active
  await env.CAMPAIGN_KV.put(
    `campaign:${campaignId}:gate`,
    'go',
    { expirationTtl: 86400 },
  );

  const waves = chunk(recipients, WAVE_SIZE);

  for (let waveIndex = 0; waveIndex < waves.length; waveIndex++) {
    const delaySeconds = waveIndex * WAVE_DELAY_SECONDS;

    const messages = waves[waveIndex].map(email => ({
      body: {
        campaignId,
        recipientEmail: email,
        wave: waveIndex,
        subject,
        templateId,
      } satisfies CampaignJob,
      delaySeconds,
    }));

    // sendBatch accepts up to 100 messages per call
    for (const batch of chunk(messages, 100)) {
      await env.CAMPAIGN_QUEUE.sendBatch(batch);
    }
  }
}

function chunk<T>(arr: T[], size: number): T[][] {
  const chunks: T[][] = [];
  for (let i = 0; i < arr.length; i += size) chunks.push(arr.slice(i, i + size));
  return chunks;
}
```

## Queue Consumer: Health-Gated Sends

```typescript
// consumer/index.ts
import { MessageBatch } from 'cloudflare:workers';

export default {
  async queue(batch: MessageBatch<CampaignJob>, env: Env): Promise<void> {
    // Check health gate; if paused, requeue with delay
    const gate = await env.CAMPAIGN_KV.get('campaign:global:gate') ?? 'go';

    if (gate === 'stop') {
      // Permanent stop — move to DLQ by exhausting retries
      for (const msg of batch.messages) msg.retry();
      return;
    }

    if (gate === 'pause') {
      // Temporary pause — requeue with a 5-minute delay
      for (const msg of batch.messages) msg.retry({ delaySeconds: 300 });
      return;
    }

    // Campaign-specific gate overrides global gate
    const firstJob = batch.messages[0].body;
    const campaignGate = await env.CAMPAIGN_KV.get(
      `campaign:${firstJob.campaignId}:gate`,
    ) ?? 'go';

    if (campaignGate !== 'go') {
      for (const msg of batch.messages) msg.retry({ delaySeconds: 300 });
      return;
    }

    await Promise.allSettled(
      batch.messages.map(msg => sendOne(msg.body, env, msg)),
    );
  },

  async scheduled(_event: ScheduledEvent, env: Env): Promise<void> {
    await runHealthCheck(env);
  },
};

async function sendOne(
  job: CampaignJob,
  env: Env,
  msg: any,
): Promise<void> {
  try {
    const html = await renderTemplate(job.templateId, job.recipientEmail, env);

    const res = await fetch('https://api.mailchannels.net/tx/v1/send', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        personalizations: [{ to: [{ email: job.recipientEmail }] }],
        from: { email: `campaigns@${env.SENDING_DOMAIN}` },
        subject: job.subject,
        content: [{ type: 'text/html', value: html }],
        headers: { 'X-Campaign-ID': job.campaignId, 'X-Wave': String(job.wave) },
      }),
    });

    const eventType = res.ok ? 'send' : 'bounce_hard';
    env.EMAIL_AE.writeDataPoint({
      indexes: [env.SENDING_DOMAIN],
      blobs: [eventType, job.campaignId, 'mailchannels'],
      doubles: [1.0, res.ok ? 0 : -5],
    });

    msg.ack();
  } catch {
    msg.retry({ delaySeconds: 60 });
  }
}

async function renderTemplate(
  templateId: string,
  email: string,
  env: Env,
): Promise<string> {
  const tmpl = await env.CAMPAIGN_KV.get(`template:${templateId}`) ?? '<p>Hi</p>';
  return tmpl.replace('{{email}}', email);
}
```

## Health Monitor

```typescript
async function runHealthCheck(env: Env): Promise<void> {
  // Query Analytics Engine for last-60-minute complaint + bounce rates
  const sql = `
    SELECT
      SUM(CASE WHEN blob1='complaint'   THEN double1 ELSE 0 END) AS complaints,
      SUM(CASE WHEN blob1='bounce_hard' THEN double1 ELSE 0 END) AS hard_bounces,
      SUM(CASE WHEN blob1='send'        THEN double1 ELSE 0 END) AS sends
    FROM email_deliverability
    WHERE timestamp > NOW() - INTERVAL '1' HOUR
  `;

  const res = await fetch(
    `https://api.cloudflare.com/client/v4/accounts/${env.CF_ACCOUNT_ID}/analytics_engine/sql`,
    {
      method: 'POST',
      headers: { 'Authorization': `Bearer ${env.CF_API_TOKEN}`, 'Content-Type': 'application/json' },
      body: JSON.stringify({ query: sql }),
    },
  );
  const { data } = await res.json<{ data: { complaints: number; hard_bounces: number; sends: number }[] }>();
  const { complaints, hard_bounces, sends } = data[0] ?? { complaints: 0, hard_bounces: 0, sends: 1 };

  const complaintRate = complaints / (sends || 1);
  const bounceRate    = hard_bounces / (sends || 1);

  let gate: 'go' | 'pause' | 'stop' = 'go';

  if (complaintRate > 0.005 || bounceRate > 0.05) gate = 'stop';   // critical
  else if (complaintRate > 0.001 || bounceRate > 0.02) gate = 'pause'; // warning

  await env.CAMPAIGN_KV.put('campaign:global:gate', gate, { expirationTtl: 3600 });
}
```

## Anti-patterns

- **Enqueuing all 500 000 messages at once with no delay** — this overwhelms the
  consumer concurrency and creates a 500 000-message backlog instantly.
- **Skipping the health gate check in the consumer** — a paused gate is useless if
  the consumer ignores it and sends regardless.
- **Using a single global gate for multiple concurrent campaigns** — gate per
  campaign ID so one bad campaign does not halt another.
- **Relying solely on ESP 429 signals to detect throttling** — by the time ESPs
  rate-limit you, reputation damage is already accumulating.

## Gotchas

- `sendBatch()` accepts at most 100 messages per call; loop in chunks of 100 when
  enqueuing large waves.
- `delaySeconds` on producer `sendBatch()` is capped at 12 hours (43 200 s) per
  the Queues API — for campaigns spanning days, re-enqueue subsequent waves from a
  Cron Trigger rather than setting huge delays upfront.
- Analytics Engine write lag (~30 s) means the health monitor may act on data that
  is slightly stale; set conservative thresholds to account for this.
- Queue message TTL is 4 days; campaigns longer than 4 days need a persistence
  layer (D1) to track remaining recipients.

## Verification

```bash
# Tail consumer logs during a test blast
wrangler tail campaign-consumer

# Inspect the global gate
wrangler kv key get --namespace-id=<id> "campaign:global:gate"

# Check DLQ depth
wrangler queues consumer list campaign-dlq

# Force a health check
wrangler dev && curl http://localhost:8787/__scheduled
```

## Related

- `email-smtp-pipeline-workers-queues.md`
- `transactional-queue-cloudflare-queues.md`
- `email-queue-priority-lanes-workers.md`
- `email-deliverability-score-analytics-engine.md`
- `email-domain-warmup-ip-pool-rotation-workers.md`

## Sources

- Cloudflare Queues: https://developers.cloudflare.com/queues/
- Queue sendBatch() limits: https://developers.cloudflare.com/queues/platform/limits/
- Analytics Engine SQL API: https://developers.cloudflare.com/analytics/analytics-engine/sql-api/
- Google Bulk Sender Requirements: https://support.google.com/mail/answer/81126
