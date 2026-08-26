# Domain Event Schema Registry with D1 and Workers

Date: 2026-08-23
Author: example.com
Status: production

## Symptom / Use-case

In event-driven systems built on Cloudflare Workers and Queues, producers and consumers must agree on the shape of every domain event. Without a shared schema contract, a producer silently adds or renames a field and downstream consumers break—often in production, hours after the deploy. The problem compounds in multi-team settings where bounded contexts publish events that cross context boundaries and need stable, versioned contracts.

A schema registry solves this by making every event schema an explicit, versioned, addressable artifact. Producers validate outgoing payloads before enqueuing; consumers reject unknown versions early rather than propagating corrupt state into D1 or Durable Objects.

## Context

Cloudflare's stack gives you three natural anchors for a schema registry: D1 as the durable schema store (SQL rows survive across requests), Workers as the validation and lookup layer (zero cold-start per-schema cache), and KV as an edge-side read cache for hot schema lookups. Queues deliver the events themselves and can be intercepted at the producer side to enforce schema checks before a message is accepted.

Because D1 is strongly consistent within a region and globally replicated with eventual consistency, schema writes are safe to perform infrequently (schema registration is a rare operation), while schema reads can be served at the edge from KV with a short TTL.

## Schema Storage in D1

Every event type and version is a row in D1. The registry supports JSON Schema (for structural validation) and optionally a fingerprint column for content-addressable lookup—useful for deduplication and caching.

```typescript
// migrations/001_schema_registry.sql
CREATE TABLE IF NOT EXISTS event_schemas (
  id          TEXT PRIMARY KEY,           -- "{namespace}.{event_type}@{version}"
  namespace   TEXT NOT NULL,
  event_type  TEXT NOT NULL,
  version     INTEGER NOT NULL,
  status      TEXT NOT NULL DEFAULT 'draft', -- draft | active | deprecated
  json_schema TEXT NOT NULL,
  fingerprint TEXT NOT NULL,              -- SHA-256 of canonical JSON Schema
  created_at  TEXT NOT NULL DEFAULT (datetime('now')),
  UNIQUE(namespace, event_type, version)
);

CREATE INDEX idx_schemas_namespace_type ON event_schemas(namespace, event_type);
CREATE INDEX idx_schemas_status ON event_schemas(status);
```

The registry Worker exposes a simple REST surface:

```typescript
// src/registry/handler.ts
import { Env } from './types';

export async function handleRegistry(request: Request, env: Env): Promise<Response> {
  const url = new URL(request.url);
  const [, , namespace, eventType, version] = url.pathname.split('/');

  if (request.method === 'PUT') {
    return registerSchema(request, env, namespace, eventType, Number(version));
  }

  if (request.method === 'GET') {
    return getSchema(env, namespace, eventType, Number(version));
  }

  return new Response('Method Not Allowed', { status: 405 });
}

async function registerSchema(
  request: Request,
  env: Env,
  namespace: string,
  eventType: string,
  version: number
): Promise<Response> {
  const body = await request.json() as { schema: object; status?: string };
  const canonical = JSON.stringify(body.schema, Object.keys(body.schema).sort());
  const fingerprint = await sha256(canonical);
  const id = `${namespace}.${eventType}@${version}`;

  await env.DB.prepare(
    `INSERT INTO event_schemas (id, namespace, event_type, version, status, json_schema, fingerprint)
     VALUES (?, ?, ?, ?, ?, ?, ?)
     ON CONFLICT(namespace, event_type, version) DO UPDATE
     SET json_schema = excluded.json_schema,
         fingerprint = excluded.fingerprint,
         status = excluded.status`
  ).bind(id, namespace, eventType, version, body.status ?? 'draft', canonical, fingerprint).run();

  // Invalidate KV cache
  await env.SCHEMA_CACHE.delete(id);

  return new Response(JSON.stringify({ id, fingerprint }), {
    status: 201,
    headers: { 'Content-Type': 'application/json' },
  });
}

async function getSchema(
  env: Env,
  namespace: string,
  eventType: string,
  version: number
): Promise<Response> {
  const id = `${namespace}.${eventType}@${version}`;

  // Check KV cache first (TTL 300 s)
  const cached = await env.SCHEMA_CACHE.get(id);
  if (cached) {
    return new Response(cached, { headers: { 'Content-Type': 'application/json', 'X-Cache': 'HIT' } });
  }

  const row = await env.DB.prepare(
    'SELECT * FROM event_schemas WHERE id = ?'
  ).bind(id).first<{ json_schema: string; fingerprint: string; status: string }>();

  if (!row) return new Response('Not Found', { status: 404 });

  const payload = JSON.stringify({ schema: JSON.parse(row.json_schema), fingerprint: row.fingerprint, status: row.status });
  await env.SCHEMA_CACHE.put(id, payload, { expirationTtl: 300 });

  return new Response(payload, { headers: { 'Content-Type': 'application/json', 'X-Cache': 'MISS' } });
}

async function sha256(text: string): Promise<string> {
  const buf = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(text));
  return Array.from(new Uint8Array(buf)).map(b => b.toString(16).padStart(2, '0')).join('');
}
```

## Producer-Side Validation

Producers call a lightweight validator before enqueuing. The validator fetches the schema (KV cache hit in the hot path), runs JSON Schema validation, and only then enqueues the event.

```typescript
// src/events/producer.ts
import Ajv from 'ajv';

const ajv = new Ajv({ allErrors: true });

export class EventProducer {
  constructor(
    private readonly queue: Queue,
    private readonly registryUrl: string
  ) {}

  async publish<T extends object>(
    namespace: string,
    eventType: string,
    version: number,
    payload: T
  ): Promise<void> {
    const schema = await this.fetchSchema(namespace, eventType, version);
    const validate = ajv.compile(schema);

    if (!validate(payload)) {
      throw new SchemaValidationError(
        `Event ${namespace}.${eventType}@${version} failed validation`,
        validate.errors ?? []
      );
    }

    const envelope: EventEnvelope<T> = {
      specVersion: '1.0',
      id: crypto.randomUUID(),
      type: `${namespace}.${eventType}`,
      schemaVersion: version,
      time: new Date().toISOString(),
      data: payload,
    };

    await this.queue.send(envelope, { contentType: 'json' });
  }

  private async fetchSchema(namespace: string, eventType: string, version: number): Promise<object> {
    const res = await fetch(`${this.registryUrl}/${namespace}/${eventType}/${version}`);
    if (!res.ok) throw new Error(`Schema not found: ${namespace}.${eventType}@${version}`);
    const body = await res.json() as { schema: object; status: string };
    if (body.status === 'deprecated') {
      console.warn(`Schema ${namespace}.${eventType}@${version} is deprecated`);
    }
    return body.schema;
  }
}

interface EventEnvelope<T> {
  specVersion: string;
  id: string;
  type: string;
  schemaVersion: number;
  time: string;
  data: T;
}

class SchemaValidationError extends Error {
  constructor(message: string, public readonly errors: object[]) {
    super(message);
    this.name = 'SchemaValidationError';
  }
}
```

## Consumer-Side Schema Evolution

Consumers receive the `schemaVersion` field from the envelope and dispatch to the correct handler. Unknown versions are routed to a dead-letter queue rather than failing silently.

```typescript
// src/events/consumer.ts
export class EventConsumer {
  private readonly handlers = new Map<string, EventHandler>();

  register(namespace: string, eventType: string, version: number, handler: EventHandler): void {
    this.handlers.set(`${namespace}.${eventType}@${version}`, handler);
  }

  async process(batch: MessageBatch<EventEnvelope<unknown>>, env: Env): Promise<void> {
    for (const message of batch.messages) {
      const envelope = message.body;
      const key = `${envelope.type}@${envelope.schemaVersion}`;
      const handler = this.handlers.get(key);

      if (!handler) {
        console.error(`No handler for ${key}, routing to DLQ`);
        message.retry({ delaySeconds: 0 });  // exhausts retries → DLQ
        continue;
      }

      try {
        await handler(envelope.data, env);
        message.ack();
      } catch (err) {
        console.error(`Handler failed for ${key}:`, err);
        message.retry({ delaySeconds: 30 });
      }
    }
  }
}

type EventHandler = (data: unknown, env: Env) => Promise<void>;
type EventEnvelope<T> = {
  type: string;
  schemaVersion: number;
  id: string;
  time: string;
  data: T;
};
```

## Schema Compatibility Checking

Before activating a new schema version, run a backward-compatibility check to ensure existing consumers can still process events.

```typescript
// src/registry/compatibility.ts
export function isBackwardCompatible(existingSchema: object, newSchema: object): boolean {
  const existing = existingSchema as Record<string, unknown>;
  const next = newSchema as Record<string, unknown>;

  const existingProps = (existing['properties'] ?? {}) as Record<string, unknown>;
  const nextProps = (next['properties'] ?? {}) as Record<string, unknown>;
  const existingRequired = new Set((existing['required'] ?? []) as string[]);
  const nextRequired = new Set((next['required'] ?? []) as string[]);

  // Removing a field that was required is a breaking change
  for (const field of existingRequired) {
    if (!nextRequired.has(field) && field in existingProps) {
      return false;
    }
  }

  // Adding a new required field is a breaking change
  for (const field of nextRequired) {
    if (!existingRequired.has(field)) {
      return false;
    }
  }

  return true;
}
```

## Anti-patterns

- Embedding schema definitions as TypeScript types only — types are erased at runtime and cannot validate incoming messages from external producers.
- Using `any` as the type for Queue message bodies and skipping envelope validation — this defeats the entire registry pattern.
- Setting a very long KV TTL (hours) when schemas change frequently during development — stale schemas in the cache will cause validation failures.
- Storing the full JSON Schema in every event message — prefer a version number in the envelope and a registry lookup.
- Registering schemas in the same deploy step as the consumer — a consumer that reads an unknown schema version will have no handler until it is registered first.

## Gotchas

- D1's eventual replication means a schema registered in one region may not be visible immediately in another. Use KV cache with a short TTL as the read path and accept a brief propagation window.
- Ajv is a large dependency for a Worker; consider a tree-shaken build or a lighter validator like `@cfworkers/schema` for edge constraints.
- JSON Schema `$ref` resolution at the edge requires bundling the full dereferenced schema into D1 rather than relying on external `$ref` URLs (CSP blocks outbound fetches in Workers by default).
- Schema fingerprints allow caching by content hash; if you update a schema without changing the version, the fingerprint changes but the cache key (`id`) stays the same. Always increment version on any structural change.
- KV `SCHEMA_CACHE` namespace must be bound in `wrangler.toml` for both the registry Worker and any producer Workers that call the registry internally.

## Verification

1. Register a schema via `PUT /registry/orders/OrderPlaced/1` and confirm HTTP 201 with a `fingerprint` in the response body.
2. `GET /registry/orders/OrderPlaced/1` — first response has `X-Cache: MISS`, second has `X-Cache: HIT`.
3. Publish an event with a missing required field through `EventProducer.publish()` and confirm a `SchemaValidationError` is thrown before any Queue message is sent.
4. Publish a valid event and verify it appears in the Queue consumer with the correct `schemaVersion` field.
5. Register a backward-incompatible schema (add a required field) and confirm `isBackwardCompatible` returns `false`.
6. Verify deprecated schemas still validate events but emit a `console.warn` message visible in Workers Tail.

## Related

- `event-schema-versioning.md` — versioning strategies for event schemas over time
- `domain-events.md` — domain event design within bounded contexts
- `dead-letter-queue-architecture.md` — routing unprocessable events
- `cqrs-cloudflare-workers-d1.md` — CQRS patterns using D1 as the write store

## Sources

- JSON Schema specification: https://json-schema.org/specification
- CloudEvents specification (envelope format): https://cloudevents.io/
- Confluent Schema Registry concepts (patterns applicable to any registry): https://docs.confluent.io/platform/current/schema-registry/fundamentals/index.html
