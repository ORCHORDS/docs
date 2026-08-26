# Bounce Storm Circuit Breaker for Email Sending with Workers

- **Date:** 2026-08-23
- **Author:** example.com
- **Status:** production

## Symptom / Use-case

A stale list, a misconfigured campaign, or a corrupted import can cause hundreds of hard bounces
per minute. If your Workers-based sending pipeline continues without intervention, bounce rates
spike past the 5% Gmail/Yahoo threshold within hours, destroying sending reputation.
A circuit breaker pattern — borrowed from distributed systems — automatically opens when the
rolling bounce rate crosses a threshold, halts all outbound sends, and half-opens after a cooldown
period for gradual recovery. No human needs to be awake at 3 AM to kill the job.

## Context

The circuit breaker lives in a Durable Object (or KV for simpler deployments) that tracks a
sliding window of send and bounce events. All sending Workers check the circuit state before
calling the ESP API. States are `closed` (normal), `open` (halted), and `half-open` (probe
mode). Bounce webhooks from the ESP increment the counter; the circuit evaluates state on each
increment. A Cloudflare Queue buffers outbound messages so nothing is lost when the circuit opens.

## Durable Object — Circuit Breaker State

```typescript
// circuit-breaker/src/CircuitBreaker.ts
export class CircuitBreaker implements DurableObject {
  private state: DurableObjectState;

  constructor(state: DurableObjectState) {
    this.state = state;
  }

  async fetch(request: Request): Promise<Response> {
    const url = new URL(request.url);
    switch (url.pathname) {
      case '/status':      return this.getStatus();
      case '/record-send': return this.recordSend();
      case '/record-bounce': return this.recordBounce(await request.json());
      case '/reset':       return this.reset();
      default:             return new Response('Not found', { status: 404 });
    }
  }

  private async getStatus(): Promise<Response> {
    const state = await this.state.storage.get<CircuitState>('state') ?? defaultState();
    const evaluated = await this.evaluate(state);
    return Response.json(evaluated);
  }

  private async recordSend(): Promise<Response> {
    const state = await this.state.storage.get<CircuitState>('state') ?? defaultState();
    state.sends.push(Date.now());
    state.sends = pruneWindow(state.sends);
    await this.state.storage.put('state', state);
    return Response.json({ ok: true });
  }

  private async recordBounce(body: { hard: boolean }): Promise<Response> {
    const state = await this.state.storage.get<CircuitState>('state') ?? defaultState();
    if (body.hard) state.hardBounces.push(Date.now());
    else           state.softBounces.push(Date.now());
    state.hardBounces = pruneWindow(state.hardBounces);
    state.softBounces = pruneWindow(state.softBounces);
    const evaluated = await this.evaluate(state);
    await this.state.storage.put('state', evaluated);
    return Response.json({ circuit: evaluated.circuit });
  }

  private async reset(): Promise<Response> {
    await this.state.storage.put('state', defaultState());
    return Response.json({ ok: true });
  }

  private async evaluate(state: CircuitState): Promise<CircuitState> {
    const now = Date.now();
    const sends = state.sends.length;
    const hardBounces = state.hardBounces.length;
    const bounceRate = sends > 0 ? hardBounces / sends : 0;

    if (state.circuit === 'open') {
      // Half-open after cooldown period (default 30 min)
      if (state.openedAt && now - state.openedAt > COOLDOWN_MS) {
        state.circuit = 'half-open';
        state.halfOpenedAt = now;
        console.warn('Circuit half-opened — probe mode active');
      }
    } else if (state.circuit === 'closed' || state.circuit === 'half-open') {
      if (sends >= MIN_SAMPLE_SIZE && bounceRate >= OPEN_THRESHOLD) {
        state.circuit = 'open';
        state.openedAt = now;
        console.error(`Circuit opened: bounce rate ${(bounceRate * 100).toFixed(1)}%`);
        // Notify ops
        await this.notify(bounceRate, sends, hardBounces);
      } else if (state.circuit === 'half-open' && bounceRate < CLOSE_THRESHOLD) {
        state.circuit = 'closed';
        state.openedAt = undefined;
        state.halfOpenedAt = undefined;
        console.warn('Circuit closed — normal operation resumed');
      }
    }

    return state;
  }

  private async notify(rate: number, sends: number, bounces: number): Promise<void> {
    const webhookUrl = await this.state.storage.get<string>('slackWebhookUrl');
    if (!webhookUrl) return;
    await fetch(webhookUrl, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        text: `CIRCUIT OPEN: ${(rate * 100).toFixed(1)}% hard bounce rate ` +
              `(${bounces}/${sends} in last 10min). Sending halted.`,
      }),
    });
  }
}
```

## Supporting Types and Constants

```typescript
interface CircuitState {
  circuit: 'closed' | 'open' | 'half-open';
  sends: number[];       // Timestamps of sends within window
  hardBounces: number[]; // Timestamps of hard bounces within window
  softBounces: number[]; // Timestamps of soft bounces within window
  openedAt?: number;
  halfOpenedAt?: number;
}

const WINDOW_MS       = 10 * 60 * 1000; // 10-minute rolling window
const COOLDOWN_MS     = 30 * 60 * 1000; // 30-minute open → half-open cooldown
const OPEN_THRESHOLD  = 0.05;           // 5% hard bounce rate triggers open
const CLOSE_THRESHOLD = 0.01;           // 1% bounce rate allows close from half-open
const MIN_SAMPLE_SIZE = 20;             // Don't trip on first few sends

function pruneWindow(timestamps: number[]): number[] {
  const cutoff = Date.now() - WINDOW_MS;
  return timestamps.filter(t => t > cutoff);
}

function defaultState(): CircuitState {
  return { circuit: 'closed', sends: [], hardBounces: [], softBounces: [] };
}
```

## Sending Worker — Check Before Send

```typescript
export default {
  async queue(batch: MessageBatch<OutboundEmail>, env: Env): Promise<void> {
    // Check circuit state once per batch, not per message
    const stub = env.CIRCUIT_BREAKER.get(env.CIRCUIT_BREAKER.idFromName('global'));
    const statusRes = await stub.fetch('https://do/status');
    const { circuit } = await statusRes.json<CircuitState>();

    if (circuit === 'open') {
      // Requeue all messages for later — don't ack them
      batch.retryAll({ delaySeconds: 1800 }); // retry in 30 min
      console.error('Circuit open — all messages requeued');
      return;
    }

    // half-open: process one probe message only
    const messages = circuit === 'half-open' ? batch.messages.slice(0, 1) : batch.messages;

    for (const msg of messages) {
      try {
        await sendViaEsp(msg.body, env);
        await stub.fetch('https://do/record-send', { method: 'POST' });
        msg.ack();
      } catch (err) {
        console.error('Send failed:', err);
        msg.retry({ delaySeconds: 60 });
      }
    }

    // Requeue remaining half-open messages
    if (circuit === 'half-open') {
      batch.messages.slice(1).forEach(m => m.retry({ delaySeconds: 300 }));
    }
  },
} satisfies ExportedHandler<Env>;
```

## Bounce Webhook Handler

```typescript
// Receives bounce events from ESP (SendGrid, Postmark, Resend, etc.)
export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const payload = await request.json<EspBounceEvent[]>();
    const stub = env.CIRCUIT_BREAKER.get(env.CIRCUIT_BREAKER.idFromName('global'));

    for (const event of payload) {
      const isHard = event.type === 'bounce' || event.bounceClassification === 'invalid';
      await stub.fetch('https://do/record-bounce', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ hard: isHard }),
      });
    }

    return Response.json({ ok: true });
  },
} satisfies ExportedHandler<Env>;
```

## Anti-patterns

- **Using a plain KV counter without atomic updates**: KV `put` is not atomic; concurrent Workers
  can race and under-count. Use a Durable Object for correct state.
- **Opening the circuit on soft bounces alone**: Soft bounces (mailbox full) are transient; the
  circuit should trip primarily on hard bounces.
- **Never half-opening**: An `open` circuit that never transitions to `half-open` means your
  pipeline is permanently halted after the first incident.
- **Discarding queued messages when the circuit opens**: Always requeue with a delay; the
  underlying list may be cleaned up while the circuit recovers.
- **Setting OPEN_THRESHOLD below 2%**: Normal sending always has some bounce noise; a threshold
  below 2% causes false positives.

## Gotchas

- Durable Objects have a cold-start latency of ~5 ms; at very high send rates, cache the circuit
  state in a Worker-level variable with a short TTL (1–5 s) to reduce DO calls.
- The `retryAll()` method on a Cloudflare Queues batch accepts `delaySeconds` only in explicit
  queue consumer configuration — confirm your queue binding supports delayed retries.
- ESP bounce webhooks may be delivered out of order or with delay (up to 5 minutes on some
  providers); the rolling window should be wide enough (10–15 minutes) to absorb this.
- In `half-open` state, sending a probe message that bounces should immediately re-open the
  circuit without waiting for another batch cycle.

## Verification

```bash
# Check circuit status
curl https://send.example.com/circuit/status

# Manually open the circuit for testing
curl -X POST https://send.example.com/circuit/open

# Send a batch of test bounces through the webhook
curl -X POST https://send.example.com/webhooks/bounce \
  -H "Content-Type: application/json" \
  -d '[{"type":"bounce","bounceClassification":"invalid","email":"bad@test.com"}]'

# Verify circuit opened after crossing threshold
curl https://send.example.com/circuit/status
# {"circuit":"open","sends":20,"hardBounces":2,...}

# Reset for production recovery
curl -X POST https://send.example.com/circuit/reset
```

## Related

- `email-retry-exponential-backoff.md`
- `transactional-email-dead-letter-queue-workers.md`
- `transactional-email-rate-limiting-workers.md`
- `bounce-handling-hard-soft.md`
- `bounce-suppression-d1.md`
- `complaint-rate-monitoring.md`

## Sources

- Martin Fowler — Circuit Breaker pattern — https://martinfowler.com/bliki/CircuitBreaker.html
- Gmail / Yahoo Bulk Sender Requirements — 5% bounce threshold
- Cloudflare Durable Objects — https://developers.cloudflare.com/durable-objects/
- Cloudflare Queues — https://developers.cloudflare.com/queues/
