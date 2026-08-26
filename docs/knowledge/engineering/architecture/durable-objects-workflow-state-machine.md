# Serverless Workflow Orchestration: Durable Objects as State Machine

- **Date:** 2026-08-22
- **Author:** example.com
- **Status:** production

---

## Symptom / Use-case

You need long-running, multi-step workflows — order fulfillment, document approval chains, multi-party signing — in a serverless environment. Cloudflare Workers are stateless and capped at 30 s CPU time per request, making classical saga/workflow engines (Temporal, AWS Step Functions) an external dependency. Durable Objects offer a single-threaded, hibernation-capable JavaScript actor with persistent storage, making them a natural fit for embedding the state machine directly at the edge.

---

## Context

A Cloudflare Durable Object instance is:
- **Single-writer**: all requests to the same DO ID are serialized
- **Persistent**: `this.ctx.storage` survives hibernation and restart
- **Hibernation-aware**: WebSocket hibernation keeps connections alive for hours with zero CPU charge between messages
- **Alarm-capable**: `this.ctx.storage.setAlarm()` wakes the DO at a future timestamp, enabling timeouts and scheduled transitions

These four properties map cleanly onto a state machine: the instance IS the workflow run, the storage IS the persisted state, and alarms ARE the timeout edges.

---

## Section 1: State Machine Data Model

Define workflow state as a typed record stored in the DO's KV storage.

```typescript
// workflow-types.ts
export type WorkflowStatus =
  | 'PENDING'
  | 'AWAITING_PAYMENT'
  | 'PAYMENT_CAPTURED'
  | 'FULFILLMENT_QUEUED'
  | 'SHIPPED'
  | 'COMPLETED'
  | 'FAILED'
  | 'TIMED_OUT';

export interface WorkflowState {
  id: string;
  status: WorkflowStatus;
  payload: Record<string, unknown>;
  history: Array<{ status: WorkflowStatus; ts: number; actor: string }>;
  timeoutMs?: number;
  createdAt: number;
  updatedAt: number;
}

// Allowed transitions: adjacency list
export const TRANSITIONS: Record<WorkflowStatus, WorkflowStatus[]> = {
  PENDING:            ['AWAITING_PAYMENT', 'FAILED'],
  AWAITING_PAYMENT:   ['PAYMENT_CAPTURED', 'TIMED_OUT', 'FAILED'],
  PAYMENT_CAPTURED:   ['FULFILLMENT_QUEUED', 'FAILED'],
  FULFILLMENT_QUEUED: ['SHIPPED', 'FAILED'],
  SHIPPED:            ['COMPLETED'],
  COMPLETED:          [],
  FAILED:             [],
  TIMED_OUT:          [],
};
```

---

## Section 2: Durable Object Actor Implementation

```typescript
// OrderWorkflowDO.ts
import { DurableObject } from 'cloudflare:workers';
import { WorkflowState, WorkflowStatus, TRANSITIONS } from './workflow-types';

export class OrderWorkflowDO extends DurableObject {
  private state!: WorkflowState;

  async fetch(request: Request): Promise<Response> {
    const url = new URL(request.url);
    const action = url.pathname.split('/').pop();

    switch (action) {
      case 'init':   return this.handleInit(request);
      case 'event':  return this.handleEvent(request);
      case 'status': return this.handleStatus();
      default:       return new Response('Not Found', { status: 404 });
    }
  }

  private async loadState(): Promise<void> {
    const stored = await this.ctx.storage.get<WorkflowState>('state');
    if (stored) this.state = stored;
  }

  private async saveState(): Promise<void> {
    this.state.updatedAt = Date.now();
    await this.ctx.storage.put('state', this.state);
  }

  private async handleInit(req: Request): Promise<Response> {
    await this.loadState();
    if (this.state) {
      return Response.json({ error: 'Already initialized' }, { status: 409 });
    }

    const body = await req.json<{ id: string; payload: Record<string, unknown>; timeoutMs?: number }>();
    this.state = {
      id: body.id,
      status: 'PENDING',
      payload: body.payload,
      history: [{ status: 'PENDING', ts: Date.now(), actor: 'system' }],
      timeoutMs: body.timeoutMs ?? 30 * 60 * 1000,
      createdAt: Date.now(),
      updatedAt: Date.now(),
    };

    // Set a global timeout alarm
    if (this.state.timeoutMs) {
      await this.ctx.storage.setAlarm(Date.now() + this.state.timeoutMs);
    }

    await this.saveState();
    return Response.json({ id: this.state.id, status: this.state.status });
  }

  private async handleEvent(req: Request): Promise<Response> {
    await this.loadState();
    if (!this.state) return Response.json({ error: 'Not found' }, { status: 404 });

    const { nextStatus, actor } = await req.json<{
      nextStatus: WorkflowStatus;
      actor: string;
    }>();

    const allowed = TRANSITIONS[this.state.status];
    if (!allowed.includes(nextStatus)) {
      return Response.json(
        { error: `Illegal transition ${this.state.status} → ${nextStatus}` },
        { status: 422 }
      );
    }

    this.state.history.push({ status: nextStatus, ts: Date.now(), actor });
    this.state.status = nextStatus;

    // Cancel alarm once workflow reaches a terminal state
    if (['COMPLETED', 'FAILED', 'TIMED_OUT'].includes(nextStatus)) {
      await this.ctx.storage.deleteAlarm();
    }

    await this.saveState();
    return Response.json({ id: this.state.id, status: this.state.status });
  }

  private async handleStatus(): Promise<Response> {
    await this.loadState();
    if (!this.state) return Response.json({ error: 'Not found' }, { status: 404 });
    return Response.json(this.state);
  }

  // Alarm fires when workflow exceeds the global timeout
  async alarm(): Promise<void> {
    await this.loadState();
    if (!this.state) return;
    if (!['COMPLETED', 'FAILED', 'TIMED_OUT'].includes(this.state.status)) {
      this.state.history.push({ status: 'TIMED_OUT', ts: Date.now(), actor: 'alarm' });
      this.state.status = 'TIMED_OUT';
      await this.saveState();
      // Optionally: enqueue a compensation job
    }
  }
}
```

---

## Section 3: Worker Router — Routing to the Right DO Instance

```typescript
// worker.ts
import { OrderWorkflowDO } from './OrderWorkflowDO';
export { OrderWorkflowDO };

interface Env {
  ORDER_WORKFLOW: DurableObjectNamespace;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);
    // /workflow/{orderId}/{action}
    const segments = url.pathname.split('/').filter(Boolean);
    if (segments[0] !== 'workflow' || segments.length < 3) {
      return new Response('Not Found', { status: 404 });
    }

    const orderId = segments[1];
    const action  = segments[2];

    // Deterministic DO ID — same order always routes to the same actor
    const id   = env.ORDER_WORKFLOW.idFromName(orderId);
    const stub = env.ORDER_WORKFLOW.get(id);

    // Forward to DO with internal URL
    const doUrl = new URL(request.url);
    doUrl.pathname = `/${action}`;
    return stub.fetch(new Request(doUrl, request));
  },
};
```

`wrangler.toml`:
```toml
[[durable_objects.bindings]]
name        = "ORDER_WORKFLOW"
class_name  = "OrderWorkflowDO"

[[migrations]]
tag               = "v1"
new_classes       = ["OrderWorkflowDO"]
```

---

## Section 4: Step-Level Timeouts with Per-Step Alarms

The global alarm handles total workflow duration. For per-step deadlines, store the alarm purpose in state:

```typescript
// Inside handleEvent, after successful transition to AWAITING_PAYMENT:
if (nextStatus === 'AWAITING_PAYMENT') {
  // Payment must arrive within 15 min
  const paymentDeadline = Date.now() + 15 * 60 * 1000;
  await this.ctx.storage.put('pendingAlarmType', 'payment_timeout');
  await this.ctx.storage.setAlarm(paymentDeadline);
}

// In alarm():
async alarm(): Promise<void> {
  await this.loadState();
  const alarmType = await this.ctx.storage.get<string>('pendingAlarmType');
  await this.ctx.storage.delete('pendingAlarmType');

  if (alarmType === 'payment_timeout' && this.state.status === 'AWAITING_PAYMENT') {
    this.state.status = 'TIMED_OUT';
    this.state.history.push({ status: 'TIMED_OUT', ts: Date.now(), actor: 'alarm:payment_timeout' });
    await this.saveState();
    // Trigger compensation: release reserved inventory
  }
}
```

---

## Section 5: Saga Compensation with Reverse Traversal

When a workflow fails mid-flight, replay the history in reverse to call compensating actions:

```typescript
// compensation.ts
const COMPENSATORS: Partial<Record<WorkflowStatus, (payload: Record<string, unknown>) => Promise<void>>> = {
  PAYMENT_CAPTURED:   async (p) => { /* issue refund */ },
  FULFILLMENT_QUEUED: async (p) => { /* cancel pick ticket */ },
  SHIPPED:            async (p) => { /* initiate return */ },
};

export async function compensate(state: WorkflowState, env: Env): Promise<void> {
  // Walk history in reverse, skipping PENDING and FAILED entries
  const reversible = [...state.history]
    .reverse()
    .filter(h => COMPENSATORS[h.status as WorkflowStatus]);

  for (const entry of reversible) {
    const compensator = COMPENSATORS[entry.status as WorkflowStatus];
    if (compensator) {
      await compensator(state.payload);
    }
  }
}
```

Call `compensate()` from inside the DO's `handleEvent` when `nextStatus === 'FAILED'`, passing `env` via a service binding or Queue message.

---

## Section 6: Observability — Streaming History via WebSocket

For real-time workflow dashboards, use the DO's WebSocket hibernation API:

```typescript
async fetch(request: Request): Promise<Response> {
  if (request.headers.get('Upgrade') === 'websocket') {
    return this.handleWebSocket();
  }
  // ... normal routing
}

private handleWebSocket(): Response {
  const [client, server] = Object.values(new WebSocketPair()) as [WebSocket, WebSocket];
  this.ctx.acceptWebSocket(server, ['status-stream']);
  return new Response(null, { status: 101, webSocket: client });
}

// Broadcast on every state save
private async saveState(): Promise<void> {
  this.state.updatedAt = Date.now();
  await this.ctx.storage.put('state', this.state);
  const msg = JSON.stringify({ status: this.state.status, ts: this.state.updatedAt });
  for (const ws of this.ctx.getWebSockets('status-stream')) {
    ws.send(msg);
  }
}
```

---

## Anti-patterns

- **Storing large blobs in DO storage**: The 128 KB per-value limit makes it unsuitable for document payloads. Store large objects in R2 and keep only the R2 key in DO state.
- **Using DO for high-fan-out queries**: Listing all workflows by status requires a separate index (D1 table). The DO owns one workflow run; a separate read model handles cross-run queries.
- **Unbounded history arrays**: Cap `history` at N entries and flush older entries to R2 or D1 for audit purposes.
- **Ignoring alarm de-duplication**: `setAlarm()` silently overwrites the existing alarm. If you set a per-step alarm and then transition before it fires, delete it with `deleteAlarm()` before setting the next one.
- **Synchronous compensation inside the alarm handler**: Compensation may fail or be slow. Enqueue compensation work to a Cloudflare Queue instead of executing it inline in `alarm()`.

---

## Gotchas

- **DO storage is not transactional across puts**: Use `ctx.storage.transaction()` for multi-key atomic writes, or structure state as a single serialized object (one `put` call) to keep writes atomic.
- **Alarm precision**: Alarms fire within ~30 seconds of the scheduled time, not exactly at the millisecond. Do not use alarms for sub-minute precision requirements.
- **DO ID namespace**: `idFromName()` is scoped to the binding. Two bindings with the same name string produce different DO instances.
- **Cold start latency**: The first request to a DO ID that has never been used incurs a creation overhead (~10 ms). Pre-warm critical workflow runs immediately after order creation.
- **Eviction and storage cost**: Dormant DOs are evicted from memory after ~10 seconds of inactivity. Storage persists; only in-memory state (class fields) is lost. Always load from `ctx.storage` at the start of each request.

---

## Verification

```bash
# Create a workflow
curl -X POST https://api.example.com/workflow/order-123/init \
  -H 'Content-Type: application/json' \
  -d '{"id":"order-123","payload":{"amount":99},"timeoutMs":900000}'

# Advance state
curl -X POST https://api.example.com/workflow/order-123/event \
  -H 'Content-Type: application/json' \
  -d '{"nextStatus":"AWAITING_PAYMENT","actor":"checkout-service"}'

# Poll current status
curl https://api.example.com/workflow/order-123/status

# Verify history depth
curl https://api.example.com/workflow/order-123/status | jq '.history | length'

# Confirm terminal state after timeout (wait ~1 s after timeoutMs):
curl https://api.example.com/workflow/order-123/status | jq '.status'
# Expected: "TIMED_OUT"
```

---

## Related

- `durable-object-alarm-api-scheduled-retry.md` — alarm mechanics in depth
- `saga-pattern-orchestration.md` — orchestration-based saga design
- `async-job-queue-cloudflare-queues-do.md` — queue-backed step dispatch
- `event-sourcing-d1-append-only-store.md` — using D1 for audit history
- `workflow-orchestration-patterns.md` — general orchestration trade-offs

---

## Sources

- Cloudflare Durable Objects documentation: https://developers.cloudflare.com/durable-objects/
- Cloudflare Durable Objects alarms: https://developers.cloudflare.com/durable-objects/api/alarms/
- Cloudflare Durable Objects storage: https://developers.cloudflare.com/durable-objects/api/storage-api/
- WebSocket hibernation API: https://developers.cloudflare.com/durable-objects/api/websockets/
- Saga pattern: https://microservices.io/patterns/data/saga.html
