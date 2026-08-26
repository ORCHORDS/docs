# Queues: Uncaught Consumer Exception Causes Infinite Retry Loop

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

A Cloudflare Queues consumer Worker threw an uncaught exception on every message in a batch. Because no dead-letter queue (DLQ) was configured and `max_retries` was left at the default, the same messages retried indefinitely. The queue depth grew unbounded, downstream processing stalled, and the consumer Worker ran at 100% error rate for over two hours before the issue was noticed.

## Context

- Cloudflare Workers + Cloudflare Queues
- TypeScript, Wrangler v3
- Consumer: email notification Worker (`notification-consumer`)
- Producer: main API Worker sending notification jobs
- Incident date: 2026-08-12; ~2 hours of missed email notifications
- Root trigger: a downstream email provider API changed its response format, causing a JSON parse error on every message

## Timeline

1. 08:00 UTC — Email provider silently changes API response format (breaking change, no notice)
2. 08:01 UTC — First batch of notification messages enters the queue
3. 08:01 UTC — Consumer attempts to parse provider response; throws `SyntaxError: Unexpected token`
4. 08:01 UTC — Cloudflare Queues retries the batch after backoff
5. 08:01–10:05 UTC — Retry loop continues; queue depth climbs to ~14,000 messages
6. 10:05 UTC — Monitoring alert fires on queue depth metric
7. 10:10 UTC — On-call identifies uncaught exception; pushes hotfix with try/catch + DLQ
8. 10:25 UTC — Backlog processed; DLQ contains failed messages for replay

## Root Cause

Cloudflare Queues treats any consumer Worker invocation that throws (or returns without calling `batch.ackAll()` or individually `msg.ack()`-ing messages) as a failed delivery. The queue retries the batch according to the configured retry policy. Without a `dead_letter_queue` binding and with `max_retries` unset (effectively unlimited in some configurations), a systematically failing consumer creates an infinite loop.

```typescript
// Broken consumer — no try/catch, no DLQ
export default {
  async queue(batch: MessageBatch<NotificationJob>, env: Env): Promise<void> {
    for (const msg of batch.messages) {
      // If sendEmail throws for ANY reason, the entire batch retries
      await sendEmail(msg.body, env);
      msg.ack();
    }
  },
};

async function sendEmail(job: NotificationJob, env: Env): Promise<void> {
  const resp = await fetch('https://api.email-provider.com/send', {
    method: 'POST',
    body: JSON.stringify(job),
    headers: { Authorization: `Bearer ${env.EMAIL_API_KEY}` },
  });
  // Provider changed response format; this now throws SyntaxError
  const result = await resp.json() as { messageId: string };
  console.log('Sent:', result.messageId);
}
```

## Fix

### Wrap handler in try/catch; route failures to DLQ

```typescript
// src/consumers/notification-consumer.ts

interface NotificationJob {
  userId: string;
  templateId: string;
  variables: Record<string, string>;
}

interface FailedJob {
  original: NotificationJob;
  error: string;
  failedAt: number;
  attemptNumber: number;
}

export default {
  async queue(
    batch: MessageBatch<NotificationJob>,
    env: Env
  ): Promise<void> {
    await Promise.allSettled(
      batch.messages.map((msg) => processMessage(msg, env))
    );
  },
};

async function processMessage(
  msg: Message<NotificationJob>,
  env: Env
): Promise<void> {
  try {
    await sendEmail(msg.body, env);
    msg.ack();
  } catch (err) {
    const error = err instanceof Error ? err.message : String(err);
    console.error(
      `[notification-consumer] Failed to process message id=${msg.id}:`,
      error
    );

    if (msg.attempts >= 3) {
      // Max retries reached — send to DLQ for manual replay
      console.error(
        `[notification-consumer] Message id=${msg.id} exceeded max attempts (${msg.attempts}), routing to DLQ`
      );

      // Write to DLQ queue (separate Cloudflare Queue)
      await env.NOTIFICATION_DLQ.send({
        original: msg.body,
        error,
        failedAt: Date.now(),
        attemptNumber: msg.attempts,
      } satisfies FailedJob);

      msg.ack(); // ACK the original so it stops retrying
    } else {
      msg.retry(); // Explicit retry with backoff
    }
  }
}

async function sendEmail(job: NotificationJob, env: Env): Promise<void> {
  const signal = AbortSignal.timeout(10_000);

  const resp = await fetch('https://api.email-provider.com/send', {
    method: 'POST',
    body: JSON.stringify(job),
    headers: {
      Authorization: `Bearer ${env.EMAIL_API_KEY}`,
      'Content-Type': 'application/json',
    },
    signal,
  });

  if (!resp.ok) {
    const text = await resp.text();
    throw new Error(`Email API error ${resp.status}: ${text}`);
  }

  // Defensive parse — don't assume response shape
  let result: unknown;
  try {
    result = await resp.json();
  } catch {
    // Provider returned non-JSON (e.g., plain text "OK") — treat as success
    console.warn('[sendEmail] Non-JSON response from provider; assuming success');
    return;
  }

  console.log('[sendEmail] Sent successfully:', JSON.stringify(result));
}
```

### wrangler.toml: configure max_retries and dead_letter_queue

```toml
# wrangler.toml

[[queues.consumers]]
queue            = "notifications"
max_batch_size   = 10
max_batch_timeout = 5
max_retries      = 3          # limit retry attempts
dead_letter_queue = "notifications-dlq"  # route exhausted messages here

[[queues.consumers]]
queue          = "notifications-dlq"
max_batch_size = 1   # process DLQ messages one at a time for careful inspection
max_retries    = 0   # do not retry DLQ consumer — fail fast and alert

[[queues.producers]]
queue   = "notifications"
binding = "NOTIFICATIONS_QUEUE"

[[queues.producers]]
queue   = "notifications-dlq"
binding = "NOTIFICATION_DLQ"
```

## Prevention

### DLQ consumer: alert and store for replay

```typescript
// src/consumers/notification-dlq-consumer.ts

export default {
  async queue(
    batch: MessageBatch<FailedJob>,
    env: Env
  ): Promise<void> {
    for (const msg of batch.messages) {
      const job = msg.body;

      console.error(
        '[notification-dlq] Dead-lettered message:',
        JSON.stringify(job)
      );

      // Store in KV for manual inspection and replay
      const key = `dlq:notification:${Date.now()}:${Math.random().toString(36).slice(2)}`;
      await env.DLQ_KV.put(key, JSON.stringify(job), {
        expirationTtl: 60 * 60 * 24 * 7, // keep for 7 days
      });

      // Send alert (e.g., to a Slack webhook or paging system)
      await fetch(env.ALERT_WEBHOOK_URL, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          text: `Dead-lettered notification job for userId=${job.original.userId}. Error: ${job.error}`,
        }),
        signal: AbortSignal.timeout(5_000),
      }).catch((e) => console.error('[notification-dlq] Alert webhook failed:', e));

      msg.ack();
    }
  },
};
```

### Replay script for DLQ messages

```typescript
// scripts/replay-dlq.ts
import { fetchWithTimeout } from './utils';

const CF_ACCOUNT_ID = process.env.CF_ACCOUNT_ID!;
const CF_API_TOKEN  = process.env.CF_API_TOKEN!;
const DLQ_KV_NS_ID = process.env.DLQ_KV_NS_ID!;
const NOTIFICATIONS_QUEUE_ID = process.env.NOTIFICATIONS_QUEUE_ID!;

async function replayDLQ(): Promise<void> {
  // List DLQ KV keys
  const resp = await fetch(
    `https://api.cloudflare.com/client/v4/accounts/${CF_ACCOUNT_ID}/storage/kv/namespaces/${DLQ_KV_NS_ID}/keys?prefix=dlq:notification:`,
    { headers: { Authorization: `Bearer ${CF_API_TOKEN}` } }
  );
  const { result: keys } = await resp.json() as { result: { name: string }[] };

  console.log(`Found ${keys.length} DLQ entries to replay`);

  for (const key of keys) {
    const valResp = await fetch(
      `https://api.cloudflare.com/client/v4/accounts/${CF_ACCOUNT_ID}/storage/kv/namespaces/${DLQ_KV_NS_ID}/values/${encodeURIComponent(key.name)}`,
      { headers: { Authorization: `Bearer ${CF_API_TOKEN}` } }
    );
    const failedJob = await valResp.json() as FailedJob;

    // Re-enqueue the original job
    await fetch(
      `https://api.cloudflare.com/client/v4/accounts/${CF_ACCOUNT_ID}/queues/${NOTIFICATIONS_QUEUE_ID}/messages`,
      {
        method: 'POST',
        headers: {
          Authorization: `Bearer ${CF_API_TOKEN}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ messages: [{ body: failedJob.original }] }),
      }
    );

    console.log(`Replayed: ${key.name}`);
  }
}

replayDLQ().catch(console.error);
```

## Anti-patterns

- Consumer handlers with no try/catch around business logic
- Not configuring `max_retries` in `wrangler.toml` (or leaving it at a very high value)
- Not configuring `dead_letter_queue` for production queues
- Calling `msg.ack()` only in the happy path — exceptions before ack cause silent retries
- Using `batch.ackAll()` before processing (data loss risk if processing fails)
- Using `batch.ackAll()` never — forgetting to ack causes infinite retry of successful messages
- Parsing external API responses without defensive error handling

## Gotchas

- If the consumer Worker itself throws and nothing is ack'd or retry'd, Cloudflare Queues retries the **entire batch**, not individual messages
- `msg.attempts` starts at 1 on the first attempt; plan your max-attempts check accordingly
- `dead_letter_queue` in `wrangler.toml` requires the DLQ queue to already exist in your Cloudflare account
- Messages in a DLQ are just another queue; they still expire according to the queue's message TTL
- `Promise.allSettled` is preferred over `Promise.all` in batch consumers — a single failure with `Promise.all` would abort processing of all remaining messages in the batch

## Verification

```bash
# Check current queue depth
npx wrangler queues message list notifications  # (if available in your wrangler version)
curl -s "https://api.cloudflare.com/client/v4/accounts/$CF_ACCOUNT_ID/queues" \
  -H "Authorization: Bearer $CF_API_TOKEN" | jq '.result[] | {name,messages_total}'

# Tail the consumer Worker to watch for errors
npx wrangler tail notification-consumer --format pretty 2>&1 | grep -E 'error|dlq|retry'

# Check DLQ KV for failed messages
npx wrangler kv key list --namespace-id $DLQ_KV_NS_ID --prefix 'dlq:notification:'

# Run unit tests
npx vitest run tests/unit/notification-consumer.test.ts

# Send a test message to trigger the consumer
npx wrangler queues message push notifications '{"userId":"test-123","templateId":"welcome","variables":{}}'
```

## Related

- `lessons-durable-objects-concurrent-fetch-deadlock.md` — Async queue pattern as DO deadlock fix
- `lessons-workers-fetch-no-abort-signal-hang.md` — AbortSignal.timeout() in consumer fetch calls
- `lessons-kv-namespace-wrong-binding-silent-fail.md` — KV binding issues in DLQ storage

## Sources

- https://developers.cloudflare.com/queues/
- https://developers.cloudflare.com/queues/configuration/configure-queues/
- https://developers.cloudflare.com/queues/reference/how-queues-works/
- https://developers.cloudflare.com/queues/examples/dead-letter-queues/
