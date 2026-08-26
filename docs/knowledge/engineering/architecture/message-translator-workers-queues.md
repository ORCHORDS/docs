# Message Translator Pattern — Workers + Queues

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case
You are integrating two systems that speak different message schemas — a legacy CRM emits XML-flavoured JSON while your event bus expects CloudEvents. Every consumer must not have to understand the legacy format.

## Context
Cloudflare Workers consume from a Queue, perform structural transformation on each message, and re-publish to a downstream Queue or HTTP endpoint. The translator Worker is stateless and horizontally scaled by the Queues runtime. Bindings to KV or D1 allow schema lookups when mappings are configuration-driven.

---

## Architecture / Setup

```typescript
// wrangler.toml bindings
// [[queues.consumers]]  queue = "crm-raw",    binding = "RAW_QUEUE"
// [[queues.producers]]  queue = "events-out",  binding = "OUT_QUEUE"
// [vars] SCHEMA_VERSION = "v2"

export interface Env {
  RAW_QUEUE: Queue;
  OUT_QUEUE: Queue<CloudEvent>;
  SCHEMA_CACHE: KVNamespace;  // optional — stores field maps
}

interface CrmLegacyPayload {
  cust_id: string;
  evt_type: string;
  ts_epoch: number;
  data: Record<string, unknown>;
}

interface CloudEvent {
  specversion: '1.0';
  type: string;
  source: string;
  id: string;
  time: string;
  datacontenttype: 'application/json';
  data: Record<string, unknown>;
}
```

## Translation Logic

```typescript
import { createId } from '@paralleldrive/cuid2'; // bundled

function translateCrmToCloudEvent(raw: CrmLegacyPayload): CloudEvent {
  // Normalise type: "order.created" -> "com.example.crm.order.created"
  const type = `com.example.crm.${raw.evt_type.replace(/_/g, '.')}`;

  return {
    specversion: '1.0',
    type,
    source: '/crm/legacy',
    id: createId(),
    time: new Date(raw.ts_epoch * 1000).toISOString(),
    datacontenttype: 'application/json',
    data: {
      customerId: raw.cust_id,
      ...raw.data,
    },
  };
}

export default {
  async queue(batch: MessageBatch<CrmLegacyPayload>, env: Env): Promise<void> {
    const translated: MessageSendRequest<CloudEvent>[] = [];
    const dlq: string[] = [];

    for (const msg of batch.messages) {
      try {
        validateCrmPayload(msg.body);          // throws on schema violation
        translated.push({ body: translateCrmToCloudEvent(msg.body) });
        msg.ack();
      } catch (err) {
        console.error('translation_failed', { id: msg.id, err });
        dlq.push(msg.id);
        msg.retry({ delaySeconds: 0 });        // send to DLQ on repeated failure
      }
    }

    if (translated.length > 0) {
      await env.OUT_QUEUE.sendBatch(translated);
    }
  },
} satisfies ExportedHandler<Env>;
```

## Schema Validation Helper

```typescript
function validateCrmPayload(body: unknown): asserts body is CrmLegacyPayload {
  if (
    typeof body !== 'object' ||
    body === null ||
    typeof (body as CrmLegacyPayload).cust_id !== 'string' ||
    typeof (body as CrmLegacyPayload).evt_type !== 'string' ||
    typeof (body as CrmLegacyPayload).ts_epoch !== 'number'
  ) {
    throw new TypeError('Invalid CRM payload shape');
  }
}

// Optional: config-driven field mapping stored in KV
async function loadFieldMap(
  env: Env,
  evtType: string,
): Promise<Record<string, string>> {
  const raw = await env.SCHEMA_CACHE.get(`field_map:${evtType}`, 'json');
  return (raw as Record<string, string>) ?? {};
}

function applyFieldMap(
  data: Record<string, unknown>,
  map: Record<string, string>,
): Record<string, unknown> {
  return Object.fromEntries(
    Object.entries(data).map(([k, v]) => [map[k] ?? k, v]),
  );
}
```

## Configuration-Driven Translation

```typescript
// Extend the queue handler to use KV-stored mappings
export const advancedHandler: ExportedHandler<Env> = {
  async queue(batch: MessageBatch<CrmLegacyPayload>, env: Env): Promise<void> {
    // Pre-load all unique event-type maps in parallel
    const types = [...new Set(batch.messages.map((m) => m.body.evt_type))];
    const maps = Object.fromEntries(
      await Promise.all(
        types.map(async (t) => [t, await loadFieldMap(env, t)] as const),
      ),
    );

    const out: MessageSendRequest<CloudEvent>[] = [];

    for (const msg of batch.messages) {
      try {
        validateCrmPayload(msg.body);
        const fieldMap = maps[msg.body.evt_type] ?? {};
        const remapped = applyFieldMap(msg.body.data, fieldMap);
        out.push({
          body: {
            specversion: '1.0',
            type: `com.example.crm.${msg.body.evt_type}`,
            source: '/crm/legacy',
            id: crypto.randomUUID(),
            time: new Date(msg.body.ts_epoch * 1000).toISOString(),
            datacontenttype: 'application/json',
            data: { customerId: msg.body.cust_id, ...remapped },
          },
        });
        msg.ack();
      } catch {
        msg.retry();
      }
    }

    if (out.length) await env.OUT_QUEUE.sendBatch(out);
  },
};
```

## Anti-patterns
- Embedding translation logic inside domain consumers — every consumer now has to know two schemas
- Mutating the original message body — the raw message should be treated as immutable
- Doing HTTP lookups inside the per-message loop — pre-batch KV fetches instead
- Re-using translated type strings (`com.example.crm.order_created` vs `com.example.crm.order.created`) without a canonical registry

## Gotchas
- Queue message size limit is 128 KB — enriching a message can push it over; use Claim Check pattern if payload grows large
- `msg.retry()` without a delay re-delivers immediately; use `delaySeconds` for back-pressure
- KV reads inside `queue()` are subject to the 50 ms eventual-consistency window — tolerable for schema maps but not for per-message state
- CloudEvents `id` must be globally unique per source; use `crypto.randomUUID()` or cuid2, not incrementing counters

## Verification
```bash
# Publish a raw CRM event and inspect the out queue consumer logs
wrangler queues publish crm-raw '{"cust_id":"C1","evt_type":"order_placed","ts_epoch":1724400000,"data":{"amount":99}}'
wrangler tail crm-translator-worker

# Check schema cache
wrangler kv key get --namespace-id=<id> "field_map:order_placed"
```

## Related
- `dead-letter-queue-architecture.md`
- `claim-check-pattern-large-messages.md`
- `event-carried-state-transfer-workers-kv.md`
- `message-enrichment-pipeline-workers-kv.md`
- `domain-event-schema-registry-d1-workers.md`

## Sources
- https://www.enterpriseintegrationpatterns.com/patterns/messaging/MessageTranslator.html
- https://developers.cloudflare.com/queues/
- https://cloudevents.io/
- https://developers.cloudflare.com/workers/runtime-apis/kv/
