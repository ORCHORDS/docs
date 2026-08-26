# Stripe Terminal Reader Status via Workers API

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case
Your point-of-sale backend needs to poll or webhook-receive Stripe Terminal reader presence
(online/offline/action states) and expose that status to a floor-management dashboard without
running a persistent Node process.

## Context
Stripe Terminal readers (BBPOS WisePOS E, Stripe Reader S700) communicate their state
back to Stripe's cloud. Workers can proxy the Stripe Terminal API for reader list/retrieve,
forward `terminal.reader.*` webhook events into Durable Objects for real-time state
aggregation, and serve SSE streams to a dashboard UI — all at the edge with zero cold-start
penalty.

---

## Reader List and Status Polling

Fetch all readers for a location and cache the response in KV for 30 seconds so dashboards
don't hammer the Stripe API on every page load.

```typescript
// src/readers.ts
export interface Env {
  STRIPE_SECRET_KEY: string;
  READER_CACHE: KVNamespace;
}

interface StripeReader {
  id: string;
  status: 'online' | 'offline';
  label: string;
  location: string;
  action: { type: string; status: string } | null;
}

export async function listReaders(
  locationId: string,
  env: Env
): Promise<StripeReader[]> {
  const cacheKey = `readers:${locationId}`;
  const cached = await env.READER_CACHE.get(cacheKey, 'json');
  if (cached) return cached as StripeReader[];

  const url = new URL('https://api.stripe.com/v1/terminal/readers');
  url.searchParams.set('location', locationId);
  url.searchParams.set('limit', '100');

  const res = await fetch(url.toString(), {
    headers: {
      Authorization: `Bearer ${env.STRIPE_SECRET_KEY}`,
      'Stripe-Version': '2024-06-20',
    },
  });

  if (!res.ok) {
    const err = await res.json<{ error: { message: string } }>();
    throw new Error(`Stripe readers list failed: ${err.error.message}`);
  }

  const { data } = await res.json<{ data: StripeReader[] }>();
  await env.READER_CACHE.put(cacheKey, JSON.stringify(data), {
    expirationTtl: 30,
  });
  return data;
}
```

## Webhook Ingestion into Durable Objects

`terminal.reader.action_succeeded`, `terminal.reader.action_failed`, and the synthetic
`terminal.reader.status_changed` events carry real-time state. Fan them into a Durable Object
keyed by `reader_id` so every subscriber gets consistent state.

```typescript
// src/reader-state.ts  (Durable Object)
import { DurableObject } from 'cloudflare:workers';

export interface ReaderState {
  readerId: string;
  status: 'online' | 'offline';
  actionType: string | null;
  actionStatus: string | null;
  updatedAt: number;
}

export class ReaderStateDO extends DurableObject {
  private state: ReaderState | null = null;
  private sseClients: Set<WritableStreamDefaultWriter> = new Set();

  async fetch(req: Request): Promise<Response> {
    const url = new URL(req.url);

    if (url.pathname === '/update' && req.method === 'POST') {
      const incoming = await req.json<ReaderState>();
      this.state = { ...incoming, updatedAt: Date.now() };
      await this.ctx.storage.put('state', this.state);
      this.broadcast(this.state);
      return new Response('ok');
    }

    if (url.pathname === '/stream') {
      // SSE: each dashboard tab connects here
      const { readable, writable } = new TransformStream();
      const writer = writable.getWriter();
      this.sseClients.add(writer);
      writer.closed.finally(() => this.sseClients.delete(writer));

      const storedState = await this.ctx.storage.get<ReaderState>('state');
      if (storedState) {
        const enc = new TextEncoder();
        await writer.write(enc.encode(`data: ${JSON.stringify(storedState)}\n\n`));
      }
      return new Response(readable, {
        headers: {
          'Content-Type': 'text/event-stream',
          'Cache-Control': 'no-cache',
        },
      });
    }

    return new Response('not found', { status: 404 });
  }

  private broadcast(state: ReaderState): void {
    const enc = new TextEncoder();
    const payload = enc.encode(`data: ${JSON.stringify(state)}\n\n`);
    for (const writer of this.sseClients) {
      writer.write(payload).catch(() => this.sseClients.delete(writer));
    }
  }
}
```

## Webhook Router in the Main Worker

Verify the Stripe signature and route `terminal.reader.*` events to the right Durable Object.

```typescript
// src/index.ts
import { verifyStripeSignature } from './stripe-verify';
import { ReaderStateDO } from './reader-state';

export { ReaderStateDO };

export interface Env {
  STRIPE_SECRET_KEY: string;
  STRIPE_WEBHOOK_SECRET: string;
  READER_CACHE: KVNamespace;
  READER_STATE: DurableObjectNamespace;
}

export default {
  async fetch(req: Request, env: Env): Promise<Response> {
    const url = new URL(req.url);

    if (url.pathname === '/webhooks/stripe' && req.method === 'POST') {
      const body = await req.text();
      const sig = req.headers.get('stripe-signature') ?? '';
      const event = await verifyStripeSignature(body, sig, env.STRIPE_WEBHOOK_SECRET);
      if (!event) return new Response('invalid signature', { status: 400 });

      if (event.type.startsWith('terminal.reader.')) {
        const reader = event.data.object as {
          id: string;
          status: 'online' | 'offline';
          action: { type: string; status: string } | null;
        };
        const doId = env.READER_STATE.idFromName(reader.id);
        const stub = env.READER_STATE.get(doId);
        await stub.fetch('https://do/update', {
          method: 'POST',
          body: JSON.stringify({
            readerId: reader.id,
            status: reader.status,
            actionType: reader.action?.type ?? null,
            actionStatus: reader.action?.status ?? null,
          }),
        });
      }
      return new Response('ok');
    }

    // SSE proxy: /stream/:readerId
    const match = url.pathname.match(/^\/stream\/([a-z0-9_]+)$/);
    if (match) {
      const doId = env.READER_STATE.idFromName(match[1]);
      const stub = env.READER_STATE.get(doId);
      return stub.fetch('https://do/stream');
    }

    return new Response('not found', { status: 404 });
  },
};
```

## Anti-patterns
- Polling the Stripe Terminal reader API from every dashboard client directly — rate limits
  apply per key, not per reader.
- Skipping signature verification on the webhook endpoint — any caller could forge reader
  status changes.
- Storing the full `Reader` object in KV with long TTLs — `status` can flip within seconds
  when a reader is powered on/off.
- Using a single Durable Object for all readers — ID fan-out per reader is the correct pattern.

## Gotchas
- Stripe does NOT guarantee a `terminal.reader.status_changed` event; synthesize it from
  `action_succeeded`/`action_failed` plus periodic polling for readers with no recent action.
- The `action` field is `null` when the reader is idle, not absent — `reader.action?.type`
  must be optional-chained.
- SSE connections from browser tabs count against the Durable Object's concurrent
  WebSocket/fetch limit; add a connection cap and evict oldest on overflow.
- Readers in `offline` status still appear in list API results; filter them in the dashboard,
  not at the ingestion layer.

## Verification
```bash
# Trigger a test event via Stripe CLI
stripe trigger terminal.reader.action_succeeded \
  --override terminal_reader:status=online

# Check cached reader list
wrangler kv key get --binding READER_CACHE "readers:loca_xxx"

# Tail live SSE stream for a specific reader
curl -N https://your-worker.example.com/stream/tmr_xxx
```

## Related
- `terminal-offline-payment-forwarding-and-reconciliation.md`
- `stripe-issuing-real-time-authorization-webhooks.md`
- `payment-state-machine-design.md`
- `stripe-webhook-event-ordering-d1-workers.md`

## Sources
- https://stripe.com/docs/terminal/fleet/reader-status
- https://stripe.com/docs/api/terminal/readers/object
- https://stripe.com/docs/terminal/references/events
- https://developers.cloudflare.com/durable-objects/
- https://stripe.com/docs/webhooks/signatures
