# Cloudflare Queues Consumer Worker Deployment and Consumer Group Management

- **Date**: 2026-08-22
- **Author**: example.com
- **Status**: active

## Symptom / Use-case

You use Cloudflare Queues to decouple a producer Worker from asynchronous processing (email sends, webhook fanouts, image processing, audit log writes). When you deploy a new version of the consumer Worker, messages that are in-flight or already in the queue must be handled correctly by either the old or new consumer logic. Deploying a consumer with a changed message schema or broken handler silently leaves messages unprocessed in the queue or triggers retry storms.

Common failure modes:

- Consumer deploy changes the expected message format while producer still enqueues old-format messages → consumer throws on deserialization → every message fails and retries until it hits the dead-letter queue (DLQ) or the retry limit.
- Consumer deploy changes batching parameters without accounting for in-flight messages → larger batches time out; `max_batch_timeout` is exceeded and the batch is re-enqueued.
- Consumer removed from `wrangler.toml` without draining the queue first → messages pile up, never processed, silently lost after the retention period.
- A buggy consumer is deployed and immediately starts ACK-ing messages it fails to process, causing silent data loss.

## Context

Cloudflare Queues delivers messages from a queue to a bound consumer Worker via the `queue` handler. The consumer is responsible for processing each message and calling `message.ack()` (or `batch.ackAll()`) to confirm success, or `message.retry()` to re-enqueue. If the handler throws or times out, the platform retries all un-ACKed messages automatically.

Key queue delivery parameters (configured in `wrangler.toml`):
- `max_batch_size`: maximum number of messages per batch (1–100).
- `max_batch_timeout`: maximum seconds to wait for a full batch before delivering a partial batch (1–30).
- `max_retries`: number of re-delivery attempts before moving to DLQ (0–100).
- `dead_letter_queue`: name of a second queue that receives failed messages after `max_retries` is exhausted.
- `visibility_timeout_ms`: time (ms) a message is invisible after delivery before being re-delivered if not ACKed (not yet GA in all regions; check docs).

Queues retain messages for 4 days by default. A consumer outage of more than 4 days risks message loss.

## Step 1 — wrangler.toml configuration

```toml
# workers/consumer/wrangler.toml

name = "orchords-job-consumer"
main = "src/index.ts"
compatibility_date = "2025-09-01"

# Produce to this queue from any Worker:
[[queues.producers]]
queue = "orchords-jobs"
binding = "JOB_QUEUE"   # env.JOB_QUEUE.send() in producer Workers

# Consume from this queue:
[[queues.consumers]]
queue = "orchords-jobs"
max_batch_size = 10
max_batch_timeout = 5       # seconds
max_retries = 3
dead_letter_queue = "orchords-jobs-dlq"

[env.staging]
[[env.staging.queues.consumers]]
queue = "orchords-jobs-staging"
max_batch_size = 10
max_batch_timeout = 5
max_retries = 3
dead_letter_queue = "orchords-jobs-dlq-staging"
```

## Step 2 — Consumer handler with explicit ACK/retry discipline

Never use implicit ACK (letting the handler return without calling `ack`/`retry` on each message). Always be explicit:

```typescript
// workers/consumer/src/index.ts
import type { MessageBatch, Message, Queue } from "@cloudflare/workers-types";

interface JobMessage {
  type: "send_email" | "process_image" | "fanout_webhook";
  version: number;  // schema version field for compatibility gating
  payload: unknown;
}

export interface Env {
  JOB_QUEUE: Queue<JobMessage>;  // producer binding (for re-queueing)
  DB: D1Database;
}

export default {
  async queue(
    batch: MessageBatch<JobMessage>,
    env: Env
  ): Promise<void> {
    const results = await Promise.allSettled(
      batch.messages.map((msg) => processMessage(msg, env))
    );

    for (let i = 0; i < batch.messages.length; i++) {
      const msg = batch.messages[i];
      const result = results[i];

      if (result.status === "fulfilled") {
        msg.ack();
      } else {
        console.error("Message processing failed", {
          messageId: msg.id,
          error: result.reason,
          retryCount: msg.attempts,
        });
        // retry() re-enqueues; after max_retries the message goes to DLQ
        msg.retry({ delaySeconds: exponentialBackoff(msg.attempts) });
      }
    }
  },
};

async function processMessage(
  msg: Message<JobMessage>,
  env: Env
): Promise<void> {
  const job = msg.body;

  // Schema version gate: reject old-format messages gracefully
  if (job.version < 2) {
    console.warn("Skipping legacy v1 message", { messageId: msg.id });
    // ACK deliberately — v1 messages were already processed by old consumer
    // and should not be retried forever. Log to DLQ manually if needed.
    return;
  }

  switch (job.type) {
    case "send_email":
      await handleSendEmail(job.payload, env);
      break;
    case "process_image":
      await handleProcessImage(job.payload, env);
      break;
    case "fanout_webhook":
      await handleFanoutWebhook(job.payload, env);
      break;
    default:
      throw new Error(`Unknown job type: ${job.type}`);
  }
}

function exponentialBackoff(attempts: number): number {
  // Cap at 300 seconds (5 minutes)
  return Math.min(Math.pow(2, attempts), 300);
}
```

## Step 3 — Zero-downtime consumer deploy procedure

### Phase 1: Deploy new consumer with dual-schema support

Before removing support for old message formats, deploy a consumer that handles both the old (`version: 1`) and new (`version: 2`) message schemas:

```typescript
async function processMessage(
  msg: Message<JobMessage>,
  env: Env
): Promise<void> {
  const job = msg.body;

  if (job.version === 1) {
    await processV1Job(job, env);   // old logic still works
  } else if (job.version === 2) {
    await processV2Job(job, env);   // new logic
  } else {
    throw new Error(`Unsupported message version: ${job.version}`);
  }
}
```

### Phase 2: Update producer to enqueue v2 messages

```typescript
// workers/producer/src/index.ts — updated producer
await env.JOB_QUEUE.send({
  type: "send_email",
  version: 2,          // bump to v2
  payload: { to: "user@example.com", templateId: "welcome-v2" },
});
```

Deploy the producer. At this point the queue contains a mix of v1 and v2 messages; the dual-schema consumer handles both.

### Phase 3: Wait for queue drain

Monitor the queue depth until v1 messages are exhausted:

```bash
# Check queue depth via wrangler
npx wrangler queues list

# Or query via Cloudflare API for precise depth metrics
curl -s \
  "https://api.cloudflare.com/client/v4/accounts/$CF_ACCOUNT_ID/queues" \
  -H "Authorization: Bearer $CF_API_TOKEN" | jq '.result[] | select(.name=="orchords-jobs") | .stats'
```

### Phase 4: Remove v1 support from consumer

Once queue depth of v1 messages is zero (or below acceptable threshold), deploy the consumer without v1 handling.

## Step 4 — GitHub Actions pipeline

```yaml
# .github/workflows/deploy-consumer.yml
name: Deploy Queue Consumer Worker

on:
  push:
    branches: [main]
    paths:
      - "workers/consumer/**"

jobs:
  check-queue-depth:
    runs-on: ubuntu-latest
    outputs:
      queue_depth: ${{ steps.check.outputs.depth }}
    steps:
      - name: Check queue depth before deploy
        id: check
        run: |
          RESPONSE=$(curl -s \
            "https://api.cloudflare.com/client/v4/accounts/$CF_ACCOUNT_ID/queues" \
            -H "Authorization: Bearer $CF_API_TOKEN")
          DEPTH=$(echo "$RESPONSE" | jq -r \
            '.result[] | select(.name=="orchords-jobs") | .stats.num_messages_delayed // 0')
          echo "depth=$DEPTH" >> "$GITHUB_OUTPUT"
          echo "Queue depth: $DEPTH messages pending"
        env:
          CF_ACCOUNT_ID: ${{ secrets.CF_ACCOUNT_ID }}
          CF_API_TOKEN: ${{ secrets.CF_API_TOKEN }}

  deploy-consumer:
    runs-on: ubuntu-latest
    needs: check-queue-depth
    environment: production
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with: { node-version: "20", cache: "npm" }
      - run: npm ci

      - name: Log queue depth context
        run: echo "Deploying consumer; queue depth before = ${{ needs.check-queue-depth.outputs.queue_depth }}"

      - name: Deploy consumer Worker
        working-directory: workers/consumer
        run: npx wrangler deploy --env production
        env:
          CLOUDFLARE_API_TOKEN: ${{ secrets.CF_API_TOKEN }}
          CLOUDFLARE_ACCOUNT_ID: ${{ secrets.CF_ACCOUNT_ID }}

      - name: Monitor queue error rate (5 min window)
        run: |
          # Poll DLQ depth for 5 minutes; alert if it grows
          INITIAL_DLQ=$(curl -s \
            "https://api.cloudflare.com/client/v4/accounts/$CF_ACCOUNT_ID/queues" \
            -H "Authorization: Bearer $CF_API_TOKEN" | \
            jq -r '.result[] | select(.name=="orchords-jobs-dlq") | .stats.num_messages_delayed // 0')
          echo "DLQ depth at deploy: $INITIAL_DLQ"

          for i in $(seq 1 10); do
            sleep 30
            CURRENT_DLQ=$(curl -s \
              "https://api.cloudflare.com/client/v4/accounts/$CF_ACCOUNT_ID/queues" \
              -H "Authorization: Bearer $CF_API_TOKEN" | \
              jq -r '.result[] | select(.name=="orchords-jobs-dlq") | .stats.num_messages_delayed // 0')
            echo "DLQ check $i/10: $CURRENT_DLQ messages"
            if [ "$CURRENT_DLQ" -gt $((INITIAL_DLQ + 5)) ]; then
              echo "DLQ spike detected! Rolling back consumer."
              cd workers/consumer && npx wrangler rollback --env production
              exit 1
            fi
          done
          echo "No DLQ spike detected. Deploy successful."
        env:
          CF_ACCOUNT_ID: ${{ secrets.CF_ACCOUNT_ID }}
          CF_API_TOKEN: ${{ secrets.CF_API_TOKEN }}
          CLOUDFLARE_API_TOKEN: ${{ secrets.CF_API_TOKEN }}
          CLOUDFLARE_ACCOUNT_ID: ${{ secrets.CF_ACCOUNT_ID }}
```

## Step 5 — Dead-letter queue monitoring and reprocessing

Set up a DLQ consumer for operational visibility:

```typescript
// workers/dlq-monitor/src/index.ts
export default {
  async queue(
    batch: MessageBatch<unknown>,
    env: Env
  ): Promise<void> {
    for (const msg of batch.messages) {
      // Log to an external system or Cloudflare Analytics Engine
      console.error("Dead-lettered message", {
        messageId: msg.id,
        body: JSON.stringify(msg.body),
        attempts: msg.attempts,
        timestamp: msg.timestamp,
      });

      // Optionally: write to D1 for operator investigation
      await env.DB.prepare(
        "INSERT INTO dlq_log (id, body, attempts, failed_at) VALUES (?, ?, ?, ?)"
      ).bind(
        msg.id,
        JSON.stringify(msg.body),
        msg.attempts,
        Math.floor(Date.now() / 1000)
      ).run();

      msg.ack(); // Remove from DLQ after logging
    }
  },
};
```

To reprocess DLQ messages after fixing the consumer bug:

```typescript
// workers/dlq-replay/src/index.ts — reads from DLQ log and re-enqueues
export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    // Only accept internal requests
    if (request.headers.get("X-Internal-Token") !== env.INTERNAL_TOKEN) {
      return new Response("Unauthorized", { status: 401 });
    }

    const rows = await env.DB.prepare(
      "SELECT id, body FROM dlq_log WHERE replayed = 0 LIMIT 100"
    ).all();

    for (const row of rows.results) {
      const body = JSON.parse(row.body as string);
      await env.JOB_QUEUE.send(body);
      await env.DB.prepare(
        "UPDATE dlq_log SET replayed = 1 WHERE id = ?"
      ).bind(row.id).run();
    }

    return Response.json({ replayed: rows.results.length });
  },
};
```

## Anti-patterns

- **Implicit ACK by returning without calling `msg.ack()`**: In Cloudflare Queues, returning from the `queue` handler without explicitly ACKing or retrying causes the entire batch to be re-delivered. Use `batchAll()` only when all messages succeeded.
- **Using `batch.ackAll()` when some messages failed**: ACKs are permanent. Calling `ackAll()` after a partial failure permanently loses the failed messages (they do not go to DLQ).
- **Deploying a consumer that changes `max_batch_size` drastically during high queue depth**: In-flight messages are already batched. A sudden change in batch size does not affect batches being processed. Changing from 10 to 100 during a queue backlog extends the consumer timeout window, risking CPU limit hits.
- **No dead-letter queue configured**: Without a DLQ, messages that fail `max_retries` times are permanently lost with no trace.
- **Testing consumer with `--local` when message schema relies on D1 bindings**: Local Queues simulation uses an in-memory queue that does not reflect production ordering or retry semantics precisely.

## Gotchas

- The `queue` handler does not support streaming; all processing must complete within the Worker CPU time limit (50 ms CPU for bundled Workers, 30 seconds wall clock). A consumer processing 100-message batches with heavy I/O must use `waitUntil` carefully or shrink batch size.
- Queue message delivery is at-least-once. Your consumer must be idempotent — use the message `id` field as a deduplication key in D1 or KV.
- Removing a `[[queues.consumers]]` binding from `wrangler.toml` and deploying does **not** delete the queue or the consumer registration in Cloudflare. You must manually delete the consumer association via the Cloudflare dashboard or API to stop delivery to the Worker.
- Cloudflare Queues are per-account, not per-Worker. Multiple Workers in the same account can produce to the same queue, but only one Worker (or multiple Workers in a consumer group, if using consumer groups) can consume from it.
- Consumer groups (multiple Workers consuming from the same queue with partitioned delivery) are an advanced feature — check current GA status in the Cloudflare docs before using in production.

## Verification

```bash
# Confirm queue and DLQ depths
npx wrangler queues list

# Send a test message manually and tail the consumer
npx wrangler queues send orchords-jobs \
  --message '{"type":"send_email","version":2,"payload":{"to":"test@example.com","templateId":"test"}}'

npx wrangler tail orchords-job-consumer --env production --format pretty

# Check DLQ is empty after a clean deploy
npx wrangler d1 execute orchords-prod --remote \
  --command "SELECT COUNT(*) as dlq_count FROM dlq_log WHERE replayed = 0;"
```

## Related

- `workers-service-bindings-deployment-ordering.md`
- `serverless-deploy-cloudflare-workers.md`
- `d1-schema-migration-sequencing-wrangler-remote.md`
- `rollback-strategies-workers-pages.md`
- `event-schema-compat-deploys.md`
- `feature-flag-deploy-coupling.md`

## Sources

- Cloudflare Queues configuration: https://developers.cloudflare.com/queues/configuration/configure-queues/
- Queues consumer Workers: https://developers.cloudflare.com/queues/reference/how-queues-works/
- Dead-letter queues: https://developers.cloudflare.com/queues/reference/dead-letter-queues/
- Queues JavaScript API: https://developers.cloudflare.com/queues/reference/javascript-apis/
