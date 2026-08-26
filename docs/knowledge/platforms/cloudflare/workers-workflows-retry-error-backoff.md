# Cloudflare Workflows Retry and Error Backoff

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

Your Workflow calls external APIs, writes to D1, or fans out to queues — and any of those steps can fail transiently. You want automatic retry with exponential backoff, a permanent failure path that routes to a DLQ or alert, and clear observability about which step failed and why — without littering every step with try/catch boilerplate.

## Context

Cloudflare Workflows (beta/GA 2025) provides durable, multi-step execution via the `WorkflowEntrypoint` class. Each `step.do()` call is atomic and retried independently: if a step throws, the Workflow runtime retries it without re-running earlier steps. The default retry behavior is configurable per step via `RetryConfig`. Steps that exhaust retries throw a `WorkflowStepError` to the enclosing step body, giving the Workflow author a chance to handle permanent failures explicitly.

Key constraint: step bodies must be idempotent. The runtime may call a step body more than once during retry; side effects that aren't idempotent (e.g. charging a card) must be guarded with an idempotency key stored in DO or D1.

---

## 1. Basic Retry Configuration per Step

```typescript
// src/workflow.ts
import { WorkflowEntrypoint, WorkflowStep, WorkflowEvent } from "cloudflare:workers";

export interface Env {
  MY_WORKFLOW: Workflow;
}

interface OrderPayload {
  orderId: string;
  userId: string;
  amount: number;
}

export class OrderWorkflow extends WorkflowEntrypoint<Env, OrderPayload> {
  async run(event: WorkflowEvent<OrderPayload>, step: WorkflowStep) {
    const { orderId, userId, amount } = event.payload;

    // Step with aggressive retry for transient DB failures
    const reserved = await step.do(
      "reserve-inventory",
      {
        retries: {
          limit: 5,
          delay: "1 second",       // initial backoff
          backoff: "exponential",   // doubles each attempt: 1s, 2s, 4s, 8s, 16s
        },
        timeout: "10 seconds",
      },
      async () => {
        const res = await fetch("https://inventory.internal/reserve", {
          method: "POST",
          body: JSON.stringify({ orderId, amount }),
        });
        if (!res.ok) throw new Error(`Inventory reserve failed: ${res.status}`);
        return await res.json<{ reservationId: string }>();
      }
    );

    // Step that should not retry (non-idempotent without idempotency key)
    await step.do(
      "charge-payment",
      { retries: { limit: 0 } },
      async () => {
        const res = await fetch("https://payments.internal/charge", {
          method: "POST",
          headers: { "Idempotency-Key": orderId },
          body: JSON.stringify({ userId, amount }),
        });
        if (!res.ok) throw new Error(`Payment failed: ${res.status}`);
      }
    );

    return { orderId, reservationId: reserved.reservationId, status: "complete" };
  }
}
```

---

## 2. Catching Permanent Step Failures

When a step exhausts its retry budget, the Workflow engine throws from `step.do()`. Wrap it in try/catch to route to a failure handler:

```typescript
export class OrderWorkflow extends WorkflowEntrypoint<Env, OrderPayload> {
  async run(event: WorkflowEvent<OrderPayload>, step: WorkflowStep) {
    const { orderId, userId, amount } = event.payload;

    let paymentResult: { txId: string } | null = null;

    try {
      paymentResult = await step.do(
        "charge-payment",
        {
          retries: { limit: 3, delay: "2 seconds", backoff: "exponential" },
          timeout: "15 seconds",
        },
        async () => {
          const res = await fetch("https://payments.internal/charge", {
            method: "POST",
            headers: { "Idempotency-Key": orderId },
            body: JSON.stringify({ userId, amount }),
          });
          if (res.status === 402) {
            // Payment declined — not a transient error; mark non-retryable
            throw new NonRetryableError("Payment declined: insufficient funds");
          }
          if (!res.ok) throw new Error(`Payment error: ${res.status}`);
          return await res.json<{ txId: string }>();
        }
      );
    } catch (err) {
      // Step permanently failed — route to dead-letter path
      await step.do(
        "notify-failure",
        { retries: { limit: 2, delay: "500 milliseconds" } },
        async () => {
          await fetch("https://alerts.internal/order-failed", {
            method: "POST",
            body: JSON.stringify({ orderId, reason: String(err) }),
          });
        }
      );
      return { orderId, status: "failed", reason: String(err) };
    }

    return { orderId, txId: paymentResult.txId, status: "complete" };
  }
}
```

`NonRetryableError` is exported from `cloudflare:workers`. Throwing it inside a step body skips all remaining retries immediately and propagates to the surrounding `try/catch`.

---

## 3. Jitter to Avoid Thundering Herd

When many Workflow instances fail simultaneously (e.g. a downstream outage), synchronized retries hammer the recovering service at the same intervals. Add jitter:

```typescript
async () => {
  // Uniform jitter: sleep 0–1000 ms before each retry attempt
  const jitter = Math.floor(Math.random() * 1000);
  await step.sleep("jitter", `${jitter} milliseconds`);

  const res = await fetch("https://api.external.com/endpoint");
  if (!res.ok) throw new Error(`${res.status}`);
  return await res.json();
}
```

`step.sleep()` is durable — the Workflow hibernates during the sleep and doesn't consume CPU time. Avoid `setTimeout` / `await new Promise(r => setTimeout(r, n))` inside step bodies; they consume CPU and are not durable across evictions.

---

## 4. Idempotency Guard for Non-Retryable Side Effects

```typescript
// Protect a step that must not execute twice
// Use D1 to record completion with orderId as idempotency key
await step.do(
  "send-confirmation-email",
  { retries: { limit: 3, delay: "1 second", backoff: "exponential" } },
  async () => {
    // Check idempotency key before acting
    const already = await env.DB.prepare(
      "SELECT 1 FROM sent_emails WHERE order_id = ?"
    ).bind(orderId).first();

    if (already) return; // Already sent; idempotent no-op

    await env.SEND_EMAIL.send({
      from: "orders@example.com",
      to: event.payload.userEmail,
      subject: `Order ${orderId} confirmed`,
      text: `Your order ${orderId} has been confirmed.`,
    });

    await env.DB.prepare(
      "INSERT OR IGNORE INTO sent_emails (order_id, sent_at) VALUES (?, ?)"
    ).bind(orderId, new Date().toISOString()).run();
  }
);
```

---

## 5. Workflow-Level Timeout and Status Reporting

```typescript
// wrangler.toml
// [workflows]
// [[workflows.bindings]]
// name = "MY_WORKFLOW"
// class_name = "OrderWorkflow"

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const body = await request.json<OrderPayload>();

    // Create instance with unique ID for deduplication
    const instance = await env.MY_WORKFLOW.create({
      id: `order-${body.orderId}`,   // idempotent: re-creating with same ID returns existing
      params: body,
    });

    return Response.json({
      workflowId: instance.id,
      status: await instance.status(),
    });
  },

  async scheduled(event: ScheduledEvent, env: Env): Promise<void> {
    // Cron: poll for stuck workflows (> 1 hour in running state)
    // Workflows expose status via instance.status() — inspect in your own monitoring
  },
} satisfies ExportedHandler<Env>;
```

---

## Anti-patterns

- **Retrying inside a step body with a manual loop** — if the Workflow itself handles retries, the manual loop runs every time the step is retried, multiplying attempts. Set `retries.limit` in the step config and throw on failure; let the runtime retry.
- **`setTimeout` for backoff** — consumes CPU, is evicted, and doesn't survive Worker restarts. Use `step.sleep()` for durable delays.
- **Side-effectful steps without idempotency keys** — email sends, Stripe charges, or queue publishes that run twice produce duplicates. Always guard with an idempotency key checked in D1 or DO storage.
- **One giant step** — large step bodies that call five APIs sequentially lose all progress if the fifth call fails. Break into one step per external call so retries restart only the failed call.
- **Swallowing `NonRetryableError`** — catching `NonRetryableError` and re-throwing a generic `Error` causes the runtime to retry it. Let `NonRetryableError` propagate or catch at the Workflow level.

---

## Gotchas

- `retries.delay` is specified as a string with units: `"1 second"`, `"500 milliseconds"`, `"2 minutes"`. Passing a number throws a runtime type error.
- `exponential` backoff doubles the delay each attempt: with `delay: "1 second"` and `limit: 5`, delays are 1 s, 2 s, 4 s, 8 s, 16 s — max delay is 16 s, not 5 s.
- Workflow instance IDs are scoped to the binding — the same string ID can exist in two different Workflow bindings without collision.
- `step.do()` step names must be unique within a Workflow instance. Reusing a step name with different logic after a deploy may cause the runtime to skip the step if it was previously completed (step completion is keyed by name).
- The Workflow `timeout` config (wrangler.toml `max_duration`) caps the entire Workflow lifetime, not individual steps. Default is 15 minutes for paid plans.

---

## Verification

```bash
# Deploy
wrangler deploy

# Trigger a Workflow instance
curl -X POST https://my-worker.<subdomain>.workers.dev/order \
  -H "Content-Type: application/json" \
  -d '{"orderId":"ord_123","userId":"usr_456","amount":4999}'

# Poll status
curl "https://my-worker.<subdomain>.workers.dev/status?id=order-ord_123"

# Inspect logs for retry attempts
wrangler tail --format=pretty
```

---

## Related

- `cloudflare-workflows-long-running-task-orchestration.md`
- `cloudflare-workflows-human-in-the-loop-approval.md`
- `workflows-parallel-step-execution.md`
- `queues-dlq-patterns.md`

## Sources

- https://developers.cloudflare.com/workflows/
- https://developers.cloudflare.com/workflows/reference/step-options/
- https://developers.cloudflare.com/workers/runtime-apis/bindings/workflows/
