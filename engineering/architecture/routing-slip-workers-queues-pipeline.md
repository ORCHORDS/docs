# Routing Slip — Workers + Queues Dynamic Pipeline

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case
Different order types require different processing sequences: a digital order needs fraud-check → fulfilment → email, while a physical order needs fraud-check → warehouse-pick → shipping → email. Hard-coding per-type pipelines duplicates logic and couples stages.

## Context
The Routing Slip pattern attaches a self-describing processing itinerary to each message. Each Workers Queue consumer pops the next step from the slip and forwards the message to the appropriate queue. Steps are stateless Workers; the slip travels with the message through Cloudflare Queues, eliminating a central orchestrator while keeping the sequence visible and auditable.

---

## Architecture / Setup

```typescript
export interface Env {
  // One queue per processing stage
  FRAUD_CHECK_QUEUE: Queue<SlippedMessage>;
  WAREHOUSE_QUEUE: Queue<SlippedMessage>;
  FULFILMENT_QUEUE: Queue<SlippedMessage>;
  SHIPPING_QUEUE: Queue<SlippedMessage>;
  EMAIL_QUEUE: Queue<SlippedMessage>;
  AUDIT_KV: KVNamespace;
}

type StepName =
  | 'fraud-check'
  | 'warehouse-pick'
  | 'fulfilment'
  | 'shipping'
  | 'email'
  | 'done';

interface RoutingSlip {
  steps: StepName[];        // remaining steps (head is next)
  completed: StepName[];    // audit trail
}

interface SlippedMessage {
  id: string;
  payload: OrderPayload;
  slip: RoutingSlip;
}

interface OrderPayload {
  orderId: string;
  type: 'digital' | 'physical';
  customerId: string;
  items: Array<{ sku: string; qty: number }>;
}
```

## Slip Factory and Router

```typescript
const SLIP_TEMPLATES: Record<OrderPayload['type'], StepName[]> = {
  digital: ['fraud-check', 'fulfilment', 'email'],
  physical: ['fraud-check', 'warehouse-pick', 'shipping', 'email'],
};

export function createSlippedMessage(order: OrderPayload): SlippedMessage {
  return {
    id: crypto.randomUUID(),
    payload: order,
    slip: {
      steps: [...SLIP_TEMPLATES[order.type]],
      completed: [],
    },
  };
}

// Shared helper — each stage Worker calls this after doing its work
async function advance(
  msg: SlippedMessage,
  env: Env,
): Promise<void> {
  const [current, ...remaining] = msg.slip.steps;
  const updated: SlippedMessage = {
    ...msg,
    slip: {
      steps: remaining,
      completed: [...msg.slip.completed, current],
    },
  };

  const next = remaining[0] ?? 'done';

  if (next === 'done') {
    // Write audit record; no further queue send
    await env.AUDIT_KV.put(
      `order:${msg.payload.orderId}:slip`,
      JSON.stringify(updated.slip),
      { expirationTtl: 60 * 60 * 24 * 30 },
    );
    return;
  }

  const queueMap: Record<StepName, Queue<SlippedMessage> | undefined> = {
    'fraud-check': env.FRAUD_CHECK_QUEUE,
    'warehouse-pick': env.WAREHOUSE_QUEUE,
    'fulfilment': env.FULFILMENT_QUEUE,
    'shipping': env.SHIPPING_QUEUE,
    'email': env.EMAIL_QUEUE,
    'done': undefined,
  };

  const targetQueue = queueMap[next];
  if (!targetQueue) throw new Error(`Unknown step: ${next}`);
  await targetQueue.send(updated);
}
```

## Example Stage Worker — Fraud Check

```typescript
// fraud-check-worker/src/index.ts
export default {
  async queue(
    batch: MessageBatch<SlippedMessage>,
    env: Env,
  ): Promise<void> {
    for (const msg of batch.messages) {
      try {
        const order = msg.body.payload;

        // Domain logic: simple heuristic, replace with real scorer
        const fraudScore = order.items.reduce((s, i) => s + i.qty, 0);
        if (fraudScore > 100) {
          console.warn('fraud_hold', { orderId: order.orderId, fraudScore });
          // Reject and do NOT advance — message goes to DLQ via retry exhaustion
          msg.retry({ delaySeconds: 3600 });
          continue;
        }

        await advance(msg.body, env);
        msg.ack();
      } catch (err) {
        console.error('fraud_check_error', err);
        msg.retry();
      }
    }
  },
} satisfies ExportedHandler<Env>;
```

## Example Stage Worker — Email Notification

```typescript
// email-worker/src/index.ts
export default {
  async queue(
    batch: MessageBatch<SlippedMessage>,
    env: Env,
  ): Promise<void> {
    for (const msg of batch.messages) {
      try {
        const { orderId, customerId } = msg.body.payload;

        // Send confirmation; stub here — use Email Workers or HTTP in prod
        await fetch('https://api.internal/email', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            to: customerId,
            template: 'order-confirmed',
            vars: { orderId, completedSteps: msg.body.slip.completed },
          }),
        });

        await advance(msg.body, env);
        msg.ack();
      } catch (err) {
        console.error('email_error', err);
        msg.retry();
      }
    }
  },
} satisfies ExportedHandler<Env>;
```

## Auditing Slip State

```typescript
// Read slip state for an order via a query Worker
export default {
  async fetch(req: Request, env: Env): Promise<Response> {
    const orderId = new URL(req.url).searchParams.get('orderId');
    if (!orderId) return new Response('missing orderId', { status: 400 });

    const slip = await env.AUDIT_KV.get(`order:${orderId}:slip`, 'json');
    return Response.json(slip ?? { error: 'not_found' }, {
      status: slip ? 200 : 404,
    });
  },
} satisfies ExportedHandler<Env>;
```

## Anti-patterns
- Storing the slip in KV/D1 instead of on the message — the slip should travel with the message to avoid lookup latency and coupling
- Letting a stage mutate `slip.steps` arbitrarily — steps should only be shifted, not reordered at runtime
- Sharing a single queue for all stages — defeats observability and per-stage scaling controls
- Using Durable Objects as the slip store — unnecessary statefulness for a pure-routing concern

## Gotchas
- Queue message size is 128 KB; large `completed` arrays in long pipelines can approach the limit — trim audit data after archival
- `msg.retry()` on a stage failure re-delivers the current step, not the full slip; idempotency must be enforced per step
- Workers Queues batch consumers receive up to 100 messages; all stages must be safe to run concurrently within a batch
- If a stage queue is deleted/renamed, messages silently fail — validate the `queueMap` against live bindings in CI

## Verification
```bash
# Inject a digital order and follow the slip
wrangler queues publish fraud-check-queue \
  '{"id":"x1","payload":{"orderId":"ORD-1","type":"digital","customerId":"C1","items":[{"sku":"A","qty":2}]},"slip":{"steps":["fraud-check","fulfilment","email"],"completed":[]}}'

# After processing, inspect audit KV
wrangler kv key get --namespace-id=<AUDIT_KV_ID> "order:ORD-1:slip"
```

## Related
- `pipeline-architecture-workers-queues-stages.md`
- `choreography-vs-orchestration-distributed-workflows.md`
- `process-manager-vs-saga.md`
- `saga-pattern-choreography.md`
- `dead-letter-queue-architecture.md`

## Sources
- https://www.enterpriseintegrationpatterns.com/patterns/messaging/RoutingTable.html
- https://www.enterpriseintegrationpatterns.com/patterns/messaging/RoutingSlip.html
- https://developers.cloudflare.com/queues/
- https://developers.cloudflare.com/workers/runtime-apis/kv/
