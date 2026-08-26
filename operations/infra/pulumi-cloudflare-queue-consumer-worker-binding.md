# Pulumi Cloudflare Queue Consumer Worker Binding

Date: 2026-08-23 / Author: example.com / Status: production

## Symptom / Use-case

Your team provisions Cloudflare Queues alongside consumer Workers through the console and
loses track of which queue feeds which worker. You want reproducible IaC that creates the
queue, binds it as a producer binding on upstream workers, and wires a dedicated consumer
worker — all in one `pulumi up`.

---

## Context

Cloudflare Queues (GA 2024) are push-based message queues with at-least-once delivery.
A **producer binding** lets any Worker enqueue messages. A **consumer binding** wires a
Worker's `queue` handler as the sole consumer. Dead-letter queues (DLQ) are a separate
queue resource wired through `deadLetterQueue` on the binding.

Pulumi's `@pulumi/cloudflare` package exposes:
- `cloudflare.Queue` — creates the queue resource
- `cloudflare.WorkerScript` — the worker code artifact
- `cloudflare.WorkersScript` (v5 provider alias) — same resource, cleaner ergonomics
- Queue bindings live inside `queueBindings[]` on the script resource

Provider: `@pulumi/cloudflare` ≥ 5.30.0. Pin exactly in production.

---

## 1. Install and Configure the Provider

```typescript
// package.json (relevant deps)
// "@pulumi/cloudflare": "^5.30.0"
// "@pulumi/pulumi": "^3.118.0"

import * as pulumi from "@pulumi/pulumi";
import * as cloudflare from "@pulumi/cloudflare";

const cfg = new pulumi.Config("cloudflare");
const accountId = cfg.requireSecret("accountId");
```

Set secrets once:

```bash
pulumi config set --secret cloudflare:accountId <YOUR_ACCOUNT_ID>
pulumi config set --secret cloudflare:apiToken  <YOUR_API_TOKEN>
```

---

## 2. Create the Dead-Letter Queue and Main Queue

```typescript
const dlq = new cloudflare.Queue("orders-dlq", {
  accountId,
  name: "orders-dlq",
});

const ordersQueue = new cloudflare.Queue("orders", {
  accountId,
  name: "orders",
}, { dependsOn: [dlq] });

export const ordersQueueId   = ordersQueue.id;
export const dlqQueueId      = dlq.id;
```

Queues are account-scoped; `name` must be unique per account.
The DLQ itself is just a plain Queue — wiring happens on the consumer binding.

---

## 3. Package and Deploy the Consumer Worker

```typescript
// src/consumer/index.ts  (referenced as asset below)
// export default {
//   async queue(batch: MessageBatch<OrderEvent>, env: Env): Promise<void> {
//     for (const msg of batch.messages) {
//       await processOrder(msg.body);
//       msg.ack();
//     }
//   }
// }

import * as fs from "fs";
import * as path from "path";

const consumerAsset = new pulumi.asset.FileAsset(
  path.join(__dirname, "dist/consumer/index.js"),
);

const consumerWorker = new cloudflare.WorkersScript("orders-consumer", {
  accountId,
  name: "orders-consumer",
  content: consumerAsset,
  module: true,
  queueBindings: [
    {
      binding: "ORDERS_QUEUE",           // env var name inside the worker
      queue:   ordersQueue.name,
      // deadLetterQueue: dlq.name,      // not valid on consumer binding
    },
  ],
});
```

> **Note**: `deadLetterQueue` is configured on the queue resource itself or via the
> Cloudflare dashboard/API consumer configuration, not on the binding block.

---

## 4. Register the Queue Consumer

Pulumi does not yet expose a first-class `QueueConsumer` resource (as of v5.30).
Use the `cloudflare.WorkerCronTrigger` workaround or a raw API call via `Command`:

```typescript
import { local } from "@pulumi/command";

// Attach consumer after the worker and queue exist
const consumerReg = new local.Command("register-queue-consumer", {
  create: pulumi.interpolate`
    curl -s -X POST \
      "https://api.cloudflare.com/client/v4/accounts/${accountId}/queues/${ordersQueue.id}/consumers" \
      -H "Authorization: Bearer $CF_API_TOKEN" \
      -H "Content-Type: application/json" \
      -d '{"script_name":"${consumerWorker.name}","dead_letter_queue":"${dlq.name}","settings":{"batch_size":10,"max_retries":3,"max_wait_time_ms":5000}}'
  `,
  delete: pulumi.interpolate`
    echo "Consumer removal is manual via CF dashboard or API"
  `,
}, {
  dependsOn: [consumerWorker, ordersQueue, dlq],
  environment: { CF_API_TOKEN: cfg.requireSecret("apiToken") as unknown as string },
});
```

---

## 5. Producer Binding on an Upstream Worker

```typescript
const apiWorker = new cloudflare.WorkersScript("api-worker", {
  accountId,
  name: "api-worker",
  content: new pulumi.asset.FileAsset(
    path.join(__dirname, "dist/api/index.js"),
  ),
  module: true,
  queueBindings: [
    {
      binding: "ORDERS_QUEUE",   // env.ORDERS_QUEUE.send(body)
      queue:   ordersQueue.name,
    },
  ],
});
```

Producer and consumer share the same queue name. The binding direction (producer vs
consumer) is determined at worker execution context, not at the binding declaration level.

---

## 6. Stack Outputs and Cross-Stack References

```typescript
// In a shared infra stack — export queue IDs
export const ordersQueueName = ordersQueue.name;
export const dlqName         = dlq.name;

// In an app stack — reference via StackReference
const infraStack = new pulumi.StackReference("org/infra/prod");
const queueName  = infraStack.getOutput("ordersQueueName");

const workerWithRef = new cloudflare.WorkersScript("other-producer", {
  accountId,
  name: "other-producer",
  content: new pulumi.asset.FileAsset("dist/other/index.js"),
  module: true,
  queueBindings: [{ binding: "Q", queue: queueName }],
});
```

---

## Anti-patterns

- **Hardcoding queue names as strings** — always reference `ordersQueue.name` to avoid
  drift when the resource is renamed or recreated.
- **Binding the same queue as both producer and consumer in one worker** — valid but
  creates implicit self-loops; make the topology explicit in code comments.
- **Skipping DLQ for production queues** — messages that exceed `max_retries` are
  silently dropped without a DLQ.
- **Using `pulumi.all([...]).apply()` inside binding arrays** — causes unknown-during-
  preview errors; compose the binding object before the resource block.
- **Deploying consumer before the queue exists** — add explicit `dependsOn` chains.

---

## Gotchas

- Queue names are **immutable** after creation in Cloudflare. A rename requires destroy
  and recreate — plan downtime or use a blue/green queue strategy.
- `WorkersScript.module: true` is required for `queue` handler export; classic format
  workers cannot consume queues.
- The `@pulumi/cloudflare` v5 provider merged `WorkerScript` and `WorkersScript` — use
  `WorkersScript` for new stacks.
- `batch_size` max is 100; `max_wait_time_ms` max is 30 000 (30 s).
- Consumer registration via the REST API is idempotent on `script_name` — re-running
  the `local.Command` create step will error if a consumer already exists; guard with
  `|| true` or check first.

---

## Verification

```bash
# List queues
curl -s "https://api.cloudflare.com/client/v4/accounts/$CF_ACCOUNT_ID/queues" \
  -H "Authorization: Bearer $CF_API_TOKEN" | jq '.result[].name'

# Check consumers on a queue
curl -s "https://api.cloudflare.com/client/v4/accounts/$CF_ACCOUNT_ID/queues/$QUEUE_ID/consumers" \
  -H "Authorization: Bearer $CF_API_TOKEN" | jq '.result'

# Send a test message
curl -s -X POST \
  "https://api.cloudflare.com/client/v4/accounts/$CF_ACCOUNT_ID/queues/$QUEUE_ID/messages" \
  -H "Authorization: Bearer $CF_API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"messages":[{"body":{"test":true},"content_type":"application/json"}]}'
```

---

## Related

- `cloudflare-queues-terraform-provisioning.md`
- `keda-cloudflare-queue-consumers.md`
- `pulumi-cloudflare-workers-service-bindings.md`
- `pulumi-cloudflare-d1-database-iac.md`

---

## Sources

- Cloudflare Queues docs: https://developers.cloudflare.com/queues/
- Pulumi Cloudflare provider v5: https://www.pulumi.com/registry/packages/cloudflare/
- Queue consumer REST API: https://developers.cloudflare.com/api/operations/queue-create-queue-consumer
- `@pulumi/command` local resource: https://www.pulumi.com/registry/packages/command/
