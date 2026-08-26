# Queues Message-Ordering FIFO Assumption Postmortem

Date: 2026-08-23 / Author: example.com / Status: production

## Symptom / Use-case

During a billing cycle run on 2026-07-14, invoice-generation workers processed renewal events in the wrong order for ~340 subscriptions. Some customers received a "payment overdue" email before their renewal confirmation email, triggering 47 support tickets in 90 minutes. Revenue impact: $0 (no double-charges), but trust impact was severe.

## Context

example project uses Cloudflare Queues to fan out subscription lifecycle events from a central `billing-orchestrator` Worker. Engineers assumed Cloudflare Queues delivers messages in strict FIFO order per producer. The Queues documentation states delivery is **best-effort ordered** — not guaranteed FIFO. Under load, a batch retry for failed messages re-inserts them ahead of newer messages from the same producer, causing observable out-of-order processing.

---

## Section 1: The Flawed Producer Pattern

The original producer sent sequenced events without embedding ordering metadata, relying on queue position alone.

```typescript
// BEFORE — assumed queue insertion order === processing order
async function emitBillingEvents(
  queue: Queue,
  subscriptionId: string
): Promise<void> {
  await queue.send({ type: 'RENEWAL_INITIATED',   subscriptionId });
  await queue.send({ type: 'PAYMENT_CAPTURED',    subscriptionId });
  await queue.send({ type: 'INVOICE_GENERATED',   subscriptionId });
  await queue.send({ type: 'CONFIRMATION_QUEUED', subscriptionId });
}
```

A single failed delivery of `PAYMENT_CAPTURED` caused Queues to retry it after newer messages had already been consumed.

---

## Section 2: Embedding a Sequence Number

Fix: attach a monotonic sequence number and wall-clock timestamp to every event so the consumer can detect and reorder.

```typescript
// AFTER — producer stamps every event with sequence metadata
let seq = 0;

async function emitBillingEvents(
  queue: Queue,
  subscriptionId: string,
  traceId: string
): Promise<void> {
  const events = [
    'RENEWAL_INITIATED',
    'PAYMENT_CAPTURED',
    'INVOICE_GENERATED',
    'CONFIRMATION_QUEUED',
  ] as const;

  for (const type of events) {
    await queue.send({
      type,
      subscriptionId,
      traceId,
      seq: seq++,
      producedAt: Date.now(),
    });
  }
}
```

---

## Section 3: Consumer-Side Sequence Validation via Durable Object

A lightweight Durable Object acts as a per-subscription sequencer, buffering and replaying events in the correct order.

```typescript
// billing-sequencer.ts
export class BillingSequencer implements DurableObject {
  private pending = new Map<number, BillingEvent>();
  private nextExpected = 0;

  async fetch(request: Request): Promise<Response> {
    const event: BillingEvent = await request.json();

    this.pending.set(event.seq, event);
    await this.storage.put('pending', [...this.pending.entries()]);
    await this.storage.put('nextExpected', this.nextExpected);

    return new Response(JSON.stringify({ buffered: event.seq }));
  }

  async processReady(): Promise<BillingEvent[]> {
    const ready: BillingEvent[] = [];
    while (this.pending.has(this.nextExpected)) {
      ready.push(this.pending.get(this.nextExpected)!);
      this.pending.delete(this.nextExpected);
      this.nextExpected++;
    }
    await this.storage.put('nextExpected', this.nextExpected);
    return ready;
  }
}
```

---

## Section 4: Consumer Worker Routing Through the Sequencer

```typescript
// queue-consumer.ts
export default {
  async queue(
    batch: MessageBatch<BillingEvent>,
    env: Env
  ): Promise<void> {
    for (const msg of batch.messages) {
      const { subscriptionId, seq } = msg.body;
      const id = env.BILLING_SEQUENCER.idFromName(subscriptionId);
      const stub = env.BILLING_SEQUENCER.get(id);

      await stub.fetch('https://do/buffer', {
        method: 'POST',
        body: JSON.stringify(msg.body),
      });

      const readyResp = await stub.fetch('https://do/drain', { method: 'POST' });
      const ready: BillingEvent[] = await readyResp.json();

      for (const event of ready) {
        await handleBillingEvent(event, env);
      }

      msg.ack();
    }
  },
};
```

---

## Section 5: Dead-Letter Handling for Stalled Sequences

A gap in sequence numbers (e.g., `seq=2` never arrives due to DLQ overflow) would stall the sequencer forever. Use an alarm to detect and skip stale gaps.

```typescript
// Inside BillingSequencer
async alarm(): Promise<void> {
  const staleThresholdMs = 5 * 60 * 1000; // 5 minutes
  const oldestPending = [...this.pending.values()].sort(
    (a, b) => a.producedAt - b.producedAt
  )[0];

  if (oldestPending && Date.now() - oldestPending.producedAt > staleThresholdMs) {
    console.error(
      `[BillingSequencer] Gap detected at seq=${this.nextExpected}; skipping stale event`,
      { subscriptionId: oldestPending.subscriptionId }
    );
    this.nextExpected++; // advance past the gap
    await this.storage.put('nextExpected', this.nextExpected);
    // Re-trigger drain
    await this.processReady();
  }

  // Re-arm if still pending
  if (this.pending.size > 0) {
    await this.storage.setAlarm(Date.now() + 60_000);
  }
}
```

---

## Anti-patterns

- Assuming Cloudflare Queues delivers in strict insertion order — it does not guarantee FIFO under retries or batch splits.
- Encoding business state machines in queue position alone without explicit sequence metadata.
- Sending sequenced events as separate `queue.send()` calls when `sendBatch()` with content-based routing would keep them co-located.
- Skipping sequence validation in consumers because "it's too much infra."

## Gotchas

- `queue.sendBatch()` does not guarantee atomic delivery of the entire batch; individual messages can fail independently.
- Durable Object storage `put()` is synchronous within the request but the sequencer's pending map must be persisted before acknowledging the queue message.
- `msg.ack()` must be called explicitly when using manual acknowledgement; failing to ack re-delivers the message and re-introduces ordering noise.
- Sequence numbers scoped to `(subscriptionId, traceId)` avoid cross-subscription collisions when a single consumer handles mixed traffic.

## Verification

```typescript
// test: ensure out-of-order delivery is re-sequenced correctly
it('buffers and drains in sequence order', async () => {
  const events = [
    { seq: 2, type: 'INVOICE_GENERATED' },
    { seq: 0, type: 'RENEWAL_INITIATED' },
    { seq: 3, type: 'CONFIRMATION_QUEUED' },
    { seq: 1, type: 'PAYMENT_CAPTURED' },
  ];

  const sequencer = new BillingSequencer(mockState, mockEnv);
  for (const e of events) await sequencer.buffer(e);

  const drained = await sequencer.drain();
  expect(drained.map(e => e.seq)).toEqual([0, 1, 2, 3]);
});
```

Run in Miniflare with `MINIFLARE_DURABLE_OBJECT_SEQUENCER=BillingSequencer` and replay a shuffled event fixture.

## Related

- `cloudflare-queues-duplicate-delivery-incident.md`
- `queues-consumer-visibility-timeout-retry-storm-postmortem.md`
- `queues-consumer-crash-loop-dlq-overflow-postmortem.md`
- `durable-objects-alarm-silent-failure-payment-reminders.md`
- `queue-consumers-must-be-idempotent.md`

## Sources

- Cloudflare Queues documentation — Delivery Guarantees: https://developers.cloudflare.com/queues/reference/delivery/
- Cloudflare Durable Objects Alarms: https://developers.cloudflare.com/durable-objects/api/alarms/
- example project incident ticket INC-2026-0714-BILLING
