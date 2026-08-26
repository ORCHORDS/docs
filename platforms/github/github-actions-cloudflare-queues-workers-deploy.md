# GitHub Actions — Deploying Cloudflare Workers with Queues Bindings

Date: 2026-08-23
Author: example.com
Status: production

---

## Symptom / Use-case

A Cloudflare Worker uses a Queue producer and/or consumer binding. Standard
`wrangler deploy` calls succeed in local dev, but CI fails with:

```
✘ [ERROR] A worker with a Queue consumer can only be deployed to one environment at a time.
```

Or the Queue itself doesn't exist yet in the target account, so the deploy errors
with binding validation failures. Staging and production require separate Queue names,
and the CI pipeline must create missing Queues before deploying the Worker.

---

## Context

Cloudflare Queues are first-class resources like D1 databases: they must be created
via the REST API before a Worker can bind to them. `wrangler.toml` declares bindings,
but `wrangler deploy` does **not** auto-create the Queue if it is absent.

A Queue consumer Worker also carries the constraint that only one Worker can consume a
given Queue — deploying the same consumer Worker to both staging and production must
use two distinct Queues.

GitHub Actions is the correct place to:
1. Ensure Queues exist (idempotent create).
2. Deploy the producer Worker.
3. Deploy the consumer Worker.
4. Verify message delivery end-to-end in staging.

---

## 1. wrangler.toml with Queue Bindings

```toml
# wrangler.toml
name = "order-processor"
main = "src/index.ts"
compatibility_date = "2025-08-01"

[[queues.producers]]
  queue = "orders-production"
  binding = "ORDER_QUEUE"

[[queues.consumers]]
  queue = "orders-production"
  max_batch_size = 10
  max_batch_timeout = 30
  max_retries = 3
  dead_letter_queue = "orders-dlq-production"

[env.staging]
[[env.staging.queues.producers]]
  queue = "orders-staging"
  binding = "ORDER_QUEUE"

[[env.staging.queues.consumers]]
  queue = "orders-staging"
  max_batch_size = 5
  max_batch_timeout = 10
  dead_letter_queue = "orders-dlq-staging"
```

---

## 2. Ensure Queues Exist Before Deploy

```bash
#!/usr/bin/env bash
# scripts/ensure-queues.sh
# Usage: ENVIRONMENT=staging bash scripts/ensure-queues.sh
set -euo pipefail

CF_ACCOUNT_ID="${CF_ACCOUNT_ID:?}"
CF_API_TOKEN="${CF_API_TOKEN:?}"
ENVIRONMENT="${ENVIRONMENT:-production}"

declare -A QUEUES
if [[ "$ENVIRONMENT" == "staging" ]]; then
  QUEUES=( ["orders-staging"]="" ["orders-dlq-staging"]="" )
else
  QUEUES=( ["orders-production"]="" ["orders-dlq-production"]="" )
fi

BASE_URL="https://api.cloudflare.com/client/v4/accounts/${CF_ACCOUNT_ID}/queues"

for QUEUE_NAME in "${!QUEUES[@]}"; do
  echo "Checking queue: $QUEUE_NAME"
  HTTP_STATUS=$(curl -s -o /dev/null -w "%{http_code}" \
    -H "Authorization: Bearer ${CF_API_TOKEN}" \
    "${BASE_URL}?name=${QUEUE_NAME}")

  if [[ "$HTTP_STATUS" == "200" ]]; then
    # Check if the queue is in the response
    RESULT=$(curl -s \
      -H "Authorization: Bearer ${CF_API_TOKEN}" \
      "${BASE_URL}?name=${QUEUE_NAME}" | jq -r '.result | length')
    if [[ "$RESULT" -gt 0 ]]; then
      echo "  Queue exists: $QUEUE_NAME"
      continue
    fi
  fi

  echo "  Creating queue: $QUEUE_NAME"
  curl -s -X POST \
    -H "Authorization: Bearer ${CF_API_TOKEN}" \
    -H "Content-Type: application/json" \
    -d "{\"queue_name\": \"${QUEUE_NAME}\"}" \
    "${BASE_URL}" | jq '.success'
done
```

---

## 3. GitHub Actions Workflow — Staging Deploy with Queue Setup

```yaml
# .github/workflows/deploy-staging.yml
name: Deploy to Staging

on:
  push:
    branches: [main]
  workflow_dispatch:

permissions:
  contents: read
  id-token: write

jobs:
  deploy-staging:
    name: Deploy Workers + Queues (staging)
    runs-on: ubuntu-latest
    environment: staging
    concurrency:
      group: workers-deploy-staging
      cancel-in-progress: true

    steps:
      - uses: actions/checkout@v4
        with:
          persist-credentials: false

      - name: Ensure Queues exist
        run: bash scripts/ensure-queues.sh
        env:
          CF_ACCOUNT_ID: ${{ secrets.CF_ACCOUNT_ID }}
          CF_API_TOKEN: ${{ secrets.CF_API_TOKEN }}
          ENVIRONMENT: staging

      - name: Deploy Worker (staging)
        uses: cloudflare/wrangler-action@v3
        with:
          apiToken: ${{ secrets.CF_API_TOKEN }}
          accountId: ${{ secrets.CF_ACCOUNT_ID }}
          command: deploy --env staging

      - name: Smoke test — send message to Queue
        run: |
          # Trigger a test message via the Worker's HTTP endpoint
          RESPONSE=$(curl -sf -X POST \
            -H "Content-Type: application/json" \
            -d '{"test": true, "orderId": "smoke-test-001"}' \
            "${{ vars.STAGING_WORKER_URL }}/orders")
          echo "Response: $RESPONSE"
          echo "$RESPONSE" | jq -e '.queued == true'
```

---

## 4. TypeScript Worker: Producer + Consumer

```typescript
// src/index.ts
export interface Env {
  ORDER_QUEUE: Queue<OrderMessage>;
}

interface OrderMessage {
  orderId: string;
  test?: boolean;
}

// HTTP handler — enqueues messages
export default {
  async fetch(req: Request, env: Env): Promise<Response> {
    if (req.method !== "POST") {
      return new Response("Method not allowed", { status: 405 });
    }

    const body = await req.json<OrderMessage>();
    await env.ORDER_QUEUE.send(body, { contentType: "json" });

    return Response.json({ queued: true, orderId: body.orderId });
  },

  // Queue consumer — processes batches
  async queue(batch: MessageBatch<OrderMessage>, env: Env): Promise<void> {
    for (const msg of batch.messages) {
      try {
        await processOrder(msg.body);
        msg.ack();
      } catch (err) {
        console.error("Failed to process order", msg.body.orderId, err);
        msg.retry({ delaySeconds: 30 });
      }
    }
  },
};

async function processOrder(order: OrderMessage): Promise<void> {
  if (order.test) {
    console.log("Smoke test message received:", order.orderId);
    return;
  }
  // Real processing logic here
}
```

---

## 5. Production Deploy with Approval Gate

```yaml
# .github/workflows/deploy-production.yml
name: Deploy to Production

on:
  workflow_dispatch:

permissions:
  contents: read
  id-token: write

jobs:
  deploy-production:
    name: Deploy Workers + Queues (production)
    runs-on: ubuntu-latest
    environment: production   # requires manual approval in GitHub UI
    concurrency:
      group: workers-deploy-production
      cancel-in-progress: false

    steps:
      - uses: actions/checkout@v4
        with:
          persist-credentials: false

      - name: Ensure production Queues exist
        run: bash scripts/ensure-queues.sh
        env:
          CF_ACCOUNT_ID: ${{ secrets.CF_ACCOUNT_ID }}
          CF_API_TOKEN: ${{ secrets.CF_API_TOKEN }}
          ENVIRONMENT: production

      - name: Deploy Worker (production)
        uses: cloudflare/wrangler-action@v3
        with:
          apiToken: ${{ secrets.CF_API_TOKEN }}
          accountId: ${{ secrets.CF_ACCOUNT_ID }}
          command: deploy --env production
```

---

## Anti-patterns

- **Deploying the same consumer Worker to two environments sharing one Queue**: A Queue
  can only have one active consumer Worker; the second deploy will overwrite the first.
  Always use environment-scoped Queue names.
- **Skipping DLQ creation**: A dead-letter queue must be created before it can be
  referenced in `wrangler.toml`. Omitting it from the `ensure-queues.sh` script causes
  deploy errors on the first CI run.
- **Relying on `wrangler deploy` to create Queues**: Wrangler validates bindings but
  does not create missing Queues. The idempotent create script is mandatory.
- **Using the same `CF_API_TOKEN` for staging and production**: Prefer environment-
  scoped GitHub secrets and scoped Cloudflare API tokens with minimal Queue permissions.

---

## Gotchas

- The Cloudflare Queues REST API uses `queue_name` (snake_case) in POST bodies but
  returns `name` in GET responses. The listing endpoint also requires no special filter —
  fetch all and grep locally.
- `cancel-in-progress: true` is safe for staging (redundant runs can be dropped) but
  dangerous for production (never cancel a mid-flight deploy).
- Queue consumers have a **30-second batch timeout ceiling** for paid plans; free plans
  are capped lower. Setting `max_batch_timeout` above the plan limit silently falls back
  to the plan maximum.
- Consumer bindings count against the Worker's CPU time budget per batch invocation,
  not per message.

---

## Verification

```bash
# List all Queues in the account
curl -s "https://api.cloudflare.com/client/v4/accounts/${CF_ACCOUNT_ID}/queues" \
  -H "Authorization: Bearer ${CF_API_TOKEN}" | jq '.result[].queue_name'

# Check consumer backlog
curl -s "https://api.cloudflare.com/client/v4/accounts/${CF_ACCOUNT_ID}/queues/orders-staging" \
  -H "Authorization: Bearer ${CF_API_TOKEN}" | jq '.result | {consumers_total_count, messages_total_count}'
```

Expected after a smoke-test deploy: `messages_total_count` briefly > 0, drops to 0
within `max_batch_timeout` seconds.

---

## Related

- `github-actions-cloudflare-deploy-workflow.md`
- `github-actions-oidc-cloudflare-deploy.md`
- `github-actions-cloudflare-d1-migration-pipeline.md`
- `github-actions-environment-protection.md`
- `github-actions-concurrency-groups.md`

---

## Sources

- https://developers.cloudflare.com/queues/
- https://developers.cloudflare.com/queues/configuration/configure-queues/
- https://developers.cloudflare.com/workers/wrangler/configuration/#queues
- https://developers.cloudflare.com/api/operations/queue-list-queues
