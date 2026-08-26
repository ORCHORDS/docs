# Cloudflare Queues Terraform Provisioning and Consumer Config

Date: 2026-08-23
Author: example.com
Status: production

## Symptom / Use-case

You need to provision Cloudflare Queues (producers and consumers) as reproducible infrastructure, enforce delivery guarantees, set dead-letter queues, and wire consumer Workers — all from Terraform without manual dashboard clicks that drift from state.

## Context

Cloudflare Queues is the managed message queue service that connects producer Workers to consumer Workers with at-least-once delivery, retries, and optional dead-letter queues. As of 2026, `cloudflare_queue` and `cloudflare_queue_consumer` resources are stable in the Cloudflare Terraform provider (≥ 4.x). Queues are account-scoped; they are not zone-scoped. Consumer bindings live on the Worker script, so Terraform must coordinate both resources. KEDA-based autoscaling (separate concern) reads queue depth via the Cloudflare API — provisioning the queue itself is pure Terraform.

## 1. Provider and Required Variables

```hcl
terraform {
  required_providers {
    cloudflare = {
      source  = "cloudflare/cloudflare"
      version = "~> 4.40"
    }
  }
  required_version = ">= 1.9"
}

variable "cloudflare_account_id" {
  type        = string
  description = "Cloudflare account ID (not zone ID)"
}

variable "cloudflare_api_token" {
  type      = string
  sensitive = true
}

provider "cloudflare" {
  api_token = <redacted-secret>
}
```

## 2. Provisioning a Queue and Its Dead-Letter Queue

```hcl
resource "cloudflare_queue" "orders" {
  account_id = var.cloudflare_account_id
  name       = "orders-${terraform.workspace}"
}

resource "cloudflare_queue" "orders_dlq" {
  account_id = var.cloudflare_account_id
  name       = "orders-dlq-${terraform.workspace}"
}
```

Queue names must be unique within the account. Using `terraform.workspace` as a suffix gives per-environment isolation (staging vs production) without separate provider aliases.

## 3. Producer Worker with Queue Binding

```hcl
resource "cloudflare_worker_script" "order_producer" {
  account_id = var.cloudflare_account_id
  name       = "order-producer-${terraform.workspace}"
  content    = file("${path.module}/dist/producer.js")

  queue_binding {
    binding = "ORDER_QUEUE"
    queue   = cloudflare_queue.orders.name
  }
}
```

The TypeScript producer sends messages:

```typescript
// producer.ts
interface Env {
  ORDER_QUEUE: Queue<OrderPayload>;
}

interface OrderPayload {
  orderId: string;
  userId: string;
  amount: number;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const payload: OrderPayload = await request.json();
    await env.ORDER_QUEUE.send(payload, {
      contentType: "json",
      delaySeconds: 0,
    });
    return new Response(JSON.stringify({ queued: true }), {
      headers: { "Content-Type": "application/json" },
    });
  },
};
```

## 4. Consumer Worker and Queue Consumer Resource

```hcl
resource "cloudflare_worker_script" "order_consumer" {
  account_id = var.cloudflare_account_id
  name       = "order-consumer-${terraform.workspace}"
  content    = file("${path.module}/dist/consumer.js")
}

resource "cloudflare_queue_consumer" "orders_consumer" {
  account_id   = var.cloudflare_account_id
  queue_name   = cloudflare_queue.orders.name
  script_name  = cloudflare_worker_script.order_consumer.name

  batch_size           = 10
  max_retries          = 3
  max_wait_time_ms     = 5000
  dead_letter_queue    = cloudflare_queue.orders_dlq.name
  visibility_timeout_ms = 30000
}
```

Consumer TypeScript with per-message ack/retry:

```typescript
// consumer.ts
interface Env {}

interface OrderPayload {
  orderId: string;
  userId: string;
  amount: number;
}

export default {
  async queue(
    batch: MessageBatch<OrderPayload>,
    env: Env
  ): Promise<void> {
    for (const message of batch.messages) {
      try {
        await processOrder(message.body);
        message.ack();
      } catch (err) {
        // retryAll() is batch-level; retry() is per-message
        message.retry({ delaySeconds: 30 });
      }
    }
  },
};

async function processOrder(order: OrderPayload): Promise<void> {
  // business logic
}
```

## 5. DLQ Monitor Worker

```hcl
resource "cloudflare_worker_script" "dlq_monitor" {
  account_id = var.cloudflare_account_id
  name       = "orders-dlq-monitor-${terraform.workspace}"
  content    = file("${path.module}/dist/dlq-monitor.js")
}

resource "cloudflare_queue_consumer" "dlq_consumer" {
  account_id   = var.cloudflare_account_id
  queue_name   = cloudflare_queue.orders_dlq.name
  script_name  = cloudflare_worker_script.dlq_monitor.name

  batch_size       = 50
  max_retries      = 0   # do not re-DLQ the DLQ
  max_wait_time_ms = 10000
}
```

## 6. Outputs for CI Integration

```hcl
output "orders_queue_name" {
  value = cloudflare_queue.orders.name
}

output "orders_dlq_name" {
  value = cloudflare_queue.orders_dlq.name
}

output "consumer_worker_name" {
  value = cloudflare_worker_script.order_consumer.name
}
```

## Anti-patterns

- **Hardcoding queue names without workspace suffix** — creates a name collision between staging and production in the same account. Always append environment discriminators.
- **Omitting `dead_letter_queue`** — messages that exceed `max_retries` are silently dropped. Always configure a DLQ in production.
- **Setting `max_retries = 0` on the main queue** — disables at-least-once delivery guarantees. Use at least 3.
- **Deploying consumer Worker without `cloudflare_queue_consumer` resource** — the Worker script exists but is never wired; messages sit unprocessed. The consumer resource is mandatory.
- **Using `terraform destroy` to remove a queue with unprocessed messages** — Terraform will succeed but messages are lost. Drain queues before removal.

## Gotchas

- `cloudflare_queue_consumer` requires the Worker script to already exist. Use `depends_on` or implicit references to enforce ordering.
- `visibility_timeout_ms` must be ≥ `max_wait_time_ms`; otherwise, a batch that fills the wait window will see message re-delivery mid-processing.
- Queue names are immutable after creation — renaming requires destroy + create, which loses enqueued messages. Use `lifecycle { prevent_destroy = true }` on production queues.
- The Cloudflare provider does not surface queue message count as a data source; use the Cloudflare API directly in CI scripts for drain checks.
- `batch_size` max is 100 for HTTP pull consumers and 10 for event-driven consumers depending on account plan.

## Verification

```bash
# Confirm queue and consumer exist
terraform state list | grep cloudflare_queue

# Send a test message via wrangler
wrangler queues send orders-staging --message '{"orderId":"test-1","userId":"u1","amount":9.99}'

# Tail consumer logs
wrangler tail order-consumer-staging --format pretty

# Check DLQ depth (requires API token with Queues:Read)
curl -s "https://api.cloudflare.com/client/v4/accounts/$CF_ACCOUNT_ID/queues" \
  -H "Authorization: Bearer $CF_API_TOKEN" | jq '.result[] | select(.queue_name | startswith("orders"))'
```

## Related

- `keda-cloudflare-queue-consumers.md` — autoscaling consumer Workers via KEDA queue depth
- `cloudflare-workers-cost-optimization-scale.md` — batch sizing economics
- `workers-secrets-rotation-automation.md` — managing secrets for producer/consumer Workers
- `terraform-cloudflare-provider-workers-d1.md` — wiring D1 bindings alongside queues

## Sources

- https://developers.cloudflare.com/queues/reference/terraform/
- https://registry.terraform.io/providers/cloudflare/cloudflare/latest/docs/resources/queue
- https://registry.terraform.io/providers/cloudflare/cloudflare/latest/docs/resources/queue_consumer
- https://developers.cloudflare.com/queues/configuration/consumer-concurrency/
- https://developers.cloudflare.com/queues/configuration/dead-letter-queues/
