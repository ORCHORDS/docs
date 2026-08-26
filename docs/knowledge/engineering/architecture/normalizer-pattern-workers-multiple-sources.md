# Normalizer Pattern — Workers Multi-Source Ingestion

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case
Your platform ingests webhook events from Stripe, Shopify, and an internal CRM, each with incompatible schemas and content types. Downstream services should receive a single canonical `DomainEvent` regardless of source.

## Context
The Normalizer pattern routes messages from heterogeneous source queues through specialised translator Workers, each responsible for a single source format, before publishing to a single canonical output queue. On Cloudflare Workers this is implemented as one Queue consumer Worker per source, all writing to a shared canonical Queue. KV stores source-specific routing metadata and format versions. The pattern is closely related to the Message Translator but adds the routing step before translation.

---

## Architecture / Setup

```typescript
// Shared types — publish as an internal package or vendor copy
export interface CanonicalDomainEvent {
  id: string;
  occurredAt: string;       // ISO-8601
  source: 'stripe' | 'shopify' | 'crm';
  type: string;             // e.g. "payment.succeeded"
  entityId: string;
  payload: Record<string, unknown>;
  schemaVersion: number;
}

export interface Env {
  CANONICAL_QUEUE: Queue<CanonicalDomainEvent>;
  FORMAT_CONFIG: KVNamespace;  // maps source -> expected schema version
  // Each source has its own inbound queue, configured in wrangler.toml
}

// Stripe raw message shape (subset)
interface StripeEvent {
  id: string;
  type: string;
  created: number;
  data: { object: Record<string, unknown> };
}

// Shopify raw message shape (subset)
interface ShopifyWebhook {
  id: number;
  topic: string;
  occurred_at: string;
  payload: Record<string, unknown>;
}

// Internal CRM event (subset)
interface CrmEvent {
  eventId: string;
  eventType: string;
  timestamp: string;
  entityRef: string;
  attributes: Record<string, unknown>;
}
```

## Stripe Normalizer Worker

```typescript
// stripe-normalizer/src/index.ts
export default {
  async queue(
    batch: MessageBatch<StripeEvent>,
    env: Env,
  ): Promise<void> {
    const out: MessageSendRequest<CanonicalDomainEvent>[] = [];

    for (const msg of batch.messages) {
      try {
        const e = msg.body;
        const canonical: CanonicalDomainEvent = {
          id: e.id,
          occurredAt: new Date(e.created * 1000).toISOString(),
          source: 'stripe',
          type: e.type,                          // already dot-delimited
          entityId: String(e.data.object['id'] ?? e.id),
          payload: e.data.object,
          schemaVersion: 1,
        };
        out.push({ body: canonical });
        msg.ack();
      } catch (err) {
        console.error('stripe_normalizer_error', { id: msg.id, err });
        msg.retry();
      }
    }

    if (out.length) await env.CANONICAL_QUEUE.sendBatch(out);
  },
} satisfies ExportedHandler<Env>;
```

## Shopify Normalizer Worker

```typescript
// shopify-normalizer/src/index.ts
function shopifyTopicToType(topic: string): string {
  // "orders/paid" -> "orders.paid"
  return topic.replace('/', '.');
}

export default {
  async queue(
    batch: MessageBatch<ShopifyWebhook>,
    env: Env,
  ): Promise<void> {
    const out: MessageSendRequest<CanonicalDomainEvent>[] = [];

    for (const msg of batch.messages) {
      try {
        const e = msg.body;
        out.push({
          body: {
            id: crypto.randomUUID(),            // Shopify doesn't provide event id
            occurredAt: e.occurred_at,
            source: 'shopify',
            type: shopifyTopicToType(e.topic),
            entityId: String(e.id),
            payload: e.payload,
            schemaVersion: 1,
          },
        });
        msg.ack();
      } catch (err) {
        console.error('shopify_normalizer_error', { id: msg.id, err });
        msg.retry();
      }
    }

    if (out.length) await env.CANONICAL_QUEUE.sendBatch(out);
  },
} satisfies ExportedHandler<Env>;
```

## CRM Normalizer Worker

```typescript
// crm-normalizer/src/index.ts
export default {
  async queue(
    batch: MessageBatch<CrmEvent>,
    env: Env,
  ): Promise<void> {
    // Validate format version from KV config
    const expectedVersion = await env.FORMAT_CONFIG.get('crm:schema_version');

    const out: MessageSendRequest<CanonicalDomainEvent>[] = [];

    for (const msg of batch.messages) {
      try {
        const e = msg.body;
        const detectedVersion =
          (e.attributes['_schema_version'] as number | undefined) ?? 1;

        if (
          expectedVersion !== null &&
          detectedVersion !== Number(expectedVersion)
        ) {
          console.warn('crm_schema_mismatch', {
            expected: expectedVersion,
            got: detectedVersion,
            eventId: e.eventId,
          });
          // Route to DLQ path — do not ack
          msg.retry({ delaySeconds: 0 });
          continue;
        }

        out.push({
          body: {
            id: e.eventId,
            occurredAt: e.timestamp,
            source: 'crm',
            type: e.eventType.toLowerCase().replace(/_/g, '.'),
            entityId: e.entityRef,
            payload: e.attributes,
            schemaVersion: detectedVersion,
          },
        });
        msg.ack();
      } catch (err) {
        console.error('crm_normalizer_error', err);
        msg.retry();
      }
    }

    if (out.length) await env.CANONICAL_QUEUE.sendBatch(out);
  },
} satisfies ExportedHandler<Env>;
```

## Canonical Consumer (Downstream)

```typescript
// canonical-processor/src/index.ts — receives all sources, uniform shape
export default {
  async queue(
    batch: MessageBatch<CanonicalDomainEvent>,
    env: Env,
  ): Promise<void> {
    for (const msg of batch.messages) {
      const { source, type, entityId } = msg.body;
      console.log('canonical_event', { source, type, entityId });

      // Domain logic here — no source-specific branching needed
      await processDomainEvent(msg.body, env);
      msg.ack();
    }
  },
} satisfies ExportedHandler<Env>;

async function processDomainEvent(
  event: CanonicalDomainEvent,
  _env: Env,
): Promise<void> {
  // Route by canonical type regardless of original source
  if (event.type === 'orders.paid' || event.type === 'payment.succeeded') {
    // Trigger fulfilment
  }
}
```

## Anti-patterns
- Adding source-specific `if/else` branches inside the canonical consumer — defeats the entire normalizer chain
- A single shared normalizer that handles all sources — coupling formats inside one Worker means all sources redeploy together
- Storing raw source payloads in D1 without the canonical wrapper — consumers will eventually read raw format and need translation again
- Silently dropping unrecognised schema versions — always DLQ or alert on schema mismatches

## Gotchas
- `crypto.randomUUID()` in Workers is synchronous and cryptographically secure — prefer it over third-party UUID libs which add bundle size
- KV `get()` inside the queue handler is eventually consistent — cache schema version for the lifetime of the batch with a module-level variable or fetch once per batch, not per message
- Each normalizer Worker needs its own `wrangler.toml` with the correct inbound queue binding; sharing a single worker file for all sources risks entanglement
- Shopify sends the same event multiple times on retry — ensure downstream processor is idempotent on `entityId + type + occurredAt`

## Verification
```bash
# Inject a Stripe event into the stripe inbound queue
wrangler queues publish stripe-raw-queue \
  '{"id":"evt_123","type":"payment.succeeded","created":1724400000,"data":{"object":{"id":"pi_abc","amount":9900}}}'

# Tail the canonical consumer to confirm normalised shape
wrangler tail canonical-processor-worker --format=json

# Check KV config
wrangler kv key get --namespace-id=<FORMAT_CONFIG_ID> "crm:schema_version"
```

## Related
- `message-translator-workers-queues.md`
- `event-bridge-pattern-workers-queues-routing.md`
- `domain-event-schema-registry-d1-workers.md`
- `dead-letter-queue-architecture.md`
- `poison-pill-message-handling-workers-queues.md`

## Sources
- https://www.enterpriseintegrationpatterns.com/patterns/messaging/Normalizer.html
- https://developers.cloudflare.com/queues/
- https://developers.cloudflare.com/workers/runtime-apis/kv/
- https://stripe.com/docs/api/events
- https://shopify.dev/docs/apps/build/webhooks
