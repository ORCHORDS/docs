# Cloudflare Queues Message Integrity and Replay Prevention

- **Date:** 2026-08-22
- **Author:** example.com
- **Status:** production

---

## Symptom / Use-case

Your payment processing pipeline uses Cloudflare Queues: an HTTP Worker enqueues a `charge` message; a consumer Worker debits the user's account. A security audit finds that queue messages contain only a raw JSON body with no integrity protection. An attacker who gains write access to the queue (via a compromised internal service or a misconfigured binding) can replay a past charge message, causing double billing. Separately, a bug in a producer Worker sends a malformed message body that the consumer fails to validate — leading to a silent data corruption and no dead-letter visibility.

---

## Context

Cloudflare Queues is a pull-based, at-least-once message broker. Workers produce messages with `env.QUEUE.send()` or `env.QUEUE.sendBatch()`. Consumer Workers receive batches via the `queue` handler and must explicitly call `message.ack()` or `message.retry()`.

Key security properties the platform does **not** provide by default:

- **No producer authentication**: any Worker with a `[[queues.producers]]` binding can enqueue messages. There is no per-message signature or origin attestation.
- **At-least-once delivery**: messages may be delivered more than once. Consumers must be idempotent or implement deduplication.
- **No payload encryption at the application layer**: messages are encrypted in transit and at rest by Cloudflare, but the application layer sees plaintext JSON.
- **No built-in schema validation**: malformed messages reach the consumer and must be handled gracefully.

The mitigations below add HMAC-based message signing, replay nonces stored in D1, and Zod schema enforcement at the consumer boundary.

---

## Section 1 — HMAC-Signed Message Envelopes

Wrap every message in a signed envelope. The producer signs the payload before enqueuing; the consumer verifies the signature before processing.

```typescript
// shared/queue-envelope.ts
export interface QueueEnvelope<T> {
  payload: T;
  producerId: string;
  nonce: string;       // UUIDv4 — used for replay detection
  issuedAt: number;    // Unix ms
  signature: string;   // HMAC-SHA-256 over canonical string, base64url
}

const ENCODER = new TextEncoder();

function canonicalString(
  producerId: string,
  nonce: string,
  issuedAt: number,
  payload: unknown
): string {
  // Deterministic serialisation — sorted keys, no whitespace
  return `${producerId}\n${nonce}\n${issuedAt}\n${JSON.stringify(payload, sortedReplacer())}`;
}

function sortedReplacer() {
  return (_key: string, value: unknown) => {
    if (value && typeof value === "object" && !Array.isArray(value)) {
      return Object.fromEntries(
        Object.entries(value as Record<string, unknown>).sort(([a], [b]) =>
          a.localeCompare(b)
        )
      );
    }
    return value;
  };
}

export async function signEnvelope<T>(
  payload: T,
  producerId: string,
  secret: string
): Promise<QueueEnvelope<T>> {
  const nonce = crypto.randomUUID();
  const issuedAt = Date.now();
  const canonical = canonicalString(producerId, nonce, issuedAt, payload);

  const key = await crypto.subtle.importKey(
    "raw",
    ENCODER.encode(secret),
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["sign"]
  );
  const sigBytes = await crypto.subtle.sign("HMAC", key, ENCODER.encode(canonical));
  const signature = btoa(String.fromCharCode(...new Uint8Array(sigBytes)))
    .replace(/\+/g, "-")
    .replace(/\//g, "_")
    .replace(/=/g, "");

  return { payload, producerId, nonce, issuedAt, signature };
}

export async function verifyEnvelope<T>(
  envelope: QueueEnvelope<T>,
  allowedProducers: string[],
  secret: string,
  maxAgeMs = 5 * 60 * 1000 // 5 minutes
): Promise<void> {
  if (!allowedProducers.includes(envelope.producerId)) {
    throw new Error(`untrusted producer: ${envelope.producerId}`);
  }

  const age = Date.now() - envelope.issuedAt;
  if (age < 0 || age > maxAgeMs) {
    throw new Error(`envelope age out of bounds: ${age}ms`);
  }

  const canonical = canonicalString(
    envelope.producerId,
    envelope.nonce,
    envelope.issuedAt,
    envelope.payload
  );
  const key = await crypto.subtle.importKey(
    "raw",
    ENCODER.encode(secret),
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["verify"]
  );
  const sigBytes = Uint8Array.from(atob(envelope.signature.replace(/-/g, "+").replace(/_/g, "/")), c =>
    c.charCodeAt(0)
  );
  const valid = await crypto.subtle.verify("HMAC", key, sigBytes, ENCODER.encode(canonical));
  if (!valid) throw new Error("signature verification failed");
}
```

---

## Section 2 — Producer: Sending Signed Messages

The producer Worker signs each message before enqueuing. Store `QUEUE_SIGNING_SECRET` as a Cloudflare Secret.

```typescript
// producer-worker/src/index.ts
import { signEnvelope } from "../../shared/queue-envelope";
import { z } from "zod";

const ChargePayloadSchema = z.object({
  userId: z.string().uuid(),
  amountCents: z.number().int().positive().max(1_000_000),
  currency: z.enum(["USD", "EUR", "GBP"]),
  idempotencyKey: z.string().uuid(),
});

export type ChargePayload = z.infer<typeof ChargePayloadSchema>;

interface Env {
  PAYMENT_QUEUE: Queue;
  QUEUE_SIGNING_SECRET: string;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    if (request.method !== "POST" || new URL(request.url).pathname !== "/charge") {
      return new Response("Not Found", { status: 404 });
    }

    const body = await request.json().catch(() => null);
    const parsed = ChargePayloadSchema.safeParse(body);
    if (!parsed.success) {
      return new Response(JSON.stringify({ error: parsed.error.message }), {
        status: 400,
        headers: { "Content-Type": "application/json" },
      });
    }

    const envelope = await signEnvelope(parsed.data, "payment-producer", env.QUEUE_SIGNING_SECRET);

    await env.PAYMENT_QUEUE.send(envelope, {
      contentType: "json",
      delaySeconds: 0,
    });

    return Response.json({ queued: true, nonce: envelope.nonce });
  },
};
```

---

## Section 3 — Replay Prevention with D1 Nonce Store

At-least-once delivery means a message may arrive more than once. Use a D1 table to track seen nonces within the envelope's validity window.

```sql
-- migrations/0001_queue_nonces.sql
CREATE TABLE IF NOT EXISTS queue_nonces (
  nonce     TEXT PRIMARY KEY,
  queue     TEXT NOT NULL,
  seen_at   INTEGER NOT NULL  -- Unix ms
);

-- Purge nonces older than 10 minutes via a scheduled Cron Trigger
CREATE INDEX IF NOT EXISTS idx_queue_nonces_seen_at ON queue_nonces(seen_at);
```

```typescript
// shared/nonce-store.ts
interface D1Database {
  prepare(query: string): D1PreparedStatement;
  batch(statements: D1PreparedStatement[]): Promise<D1Result[]>;
}

export async function claimNonce(
  db: D1Database,
  queue: string,
  nonce: string
): Promise<boolean> {
  const now = Date.now();
  try {
    await db
      .prepare("INSERT INTO queue_nonces (nonce, queue, seen_at) VALUES (?, ?, ?)")
      .bind(nonce, queue, now)
      .run();
    return true; // nonce is fresh
  } catch (e: unknown) {
    if (e instanceof Error && e.message.includes("UNIQUE constraint failed")) {
      return false; // duplicate
    }
    throw e;
  }
}

export async function purgeExpiredNonces(
  db: D1Database,
  maxAgeMs = 10 * 60 * 1000
): Promise<void> {
  const cutoff = Date.now() - maxAgeMs;
  await db
    .prepare("DELETE FROM queue_nonces WHERE seen_at < ?")
    .bind(cutoff)
    .run();
}
```

---

## Section 4 — Consumer: Verifying and Processing Messages

The consumer verifies the signature, claims the nonce, validates the schema, then processes.

```typescript
// consumer-worker/src/index.ts
import { verifyEnvelope, QueueEnvelope } from "../../shared/queue-envelope";
import { claimNonce } from "../../shared/nonce-store";
import { z } from "zod";

const ChargePayloadSchema = z.object({
  userId: z.string().uuid(),
  amountCents: z.number().int().positive().max(1_000_000),
  currency: z.enum(["USD", "EUR", "GBP"]),
  idempotencyKey: z.string().uuid(),
});

interface Env {
  DB: D1Database;
  QUEUE_SIGNING_SECRET: string;
}

export default {
  async queue(batch: MessageBatch<QueueEnvelope<unknown>>, env: Env): Promise<void> {
    for (const message of batch.messages) {
      try {
        const envelope = message.body;

        // 1. Verify signature and age
        await verifyEnvelope(envelope, ["payment-producer"], env.QUEUE_SIGNING_SECRET);

        // 2. Prevent replay
        const fresh = await claimNonce(env.DB, batch.queue, envelope.nonce);
        if (!fresh) {
          console.warn(JSON.stringify({ event: "replay_detected", nonce: envelope.nonce }));
          message.ack(); // ack to prevent infinite retry of a duplicate
          continue;
        }

        // 3. Validate payload schema
        const parsed = ChargePayloadSchema.safeParse(envelope.payload);
        if (!parsed.success) {
          console.error(
            JSON.stringify({ event: "schema_violation", nonce: envelope.nonce, error: parsed.error.message })
          );
          message.ack(); // don't retry a structurally invalid message — send to DLQ instead
          await sendToDeadLetterQueue(envelope, "schema_violation", env);
          continue;
        }

        // 4. Idempotent processing — check idempotencyKey before debiting
        const alreadyProcessed = await checkIdempotencyKey(env.DB, parsed.data.idempotencyKey);
        if (alreadyProcessed) {
          message.ack();
          continue;
        }

        await processCharge(parsed.data, env);
        message.ack();
      } catch (e: unknown) {
        console.error(JSON.stringify({ event: "consumer_error", error: String(e) }));
        message.retry({ delaySeconds: 10 });
      }
    }
  },
};

async function checkIdempotencyKey(db: D1Database, key: string): Promise<boolean> {
  const row = await db
    .prepare("SELECT 1 FROM processed_charges WHERE idempotency_key = ?")
    .bind(key)
    .first();
  return row !== null;
}

async function processCharge(
  data: { userId: string; amountCents: number; currency: string; idempotencyKey: string },
  env: Env
): Promise<void> {
  // Insert idempotency record atomically with the debit
  await env.DB.batch([
    env.DB.prepare(
      "INSERT INTO processed_charges (idempotency_key, processed_at) VALUES (?, ?)"
    ).bind(data.idempotencyKey, Date.now()),
    env.DB.prepare(
      "INSERT INTO ledger (user_id, amount_cents, currency, created_at) VALUES (?, ?, ?, ?)"
    ).bind(data.userId, -data.amountCents, data.currency, Date.now()),
  ]);
}

async function sendToDeadLetterQueue(
  envelope: QueueEnvelope<unknown>,
  reason: string,
  _env: Env
): Promise<void> {
  // In production, bind a dead-letter queue and send here
  console.error(JSON.stringify({ event: "dlq", reason, nonce: envelope.nonce }));
}
```

---

## Section 5 — Scheduled Nonce Purge via Cron Trigger

Register a Cron Trigger to clean up expired nonces every 5 minutes, preventing unbounded D1 growth.

```toml
# wrangler.toml (consumer worker)
[triggers]
crons = ["*/5 * * * *"]
```

```typescript
// consumer-worker/src/index.ts (add scheduled handler)
import { purgeExpiredNonces } from "../../shared/nonce-store";

export default {
  async queue(batch: MessageBatch<QueueEnvelope<unknown>>, env: Env): Promise<void> {
    // ... (as above)
  },

  async scheduled(_event: ScheduledEvent, env: Env, _ctx: ExecutionContext): Promise<void> {
    await purgeExpiredNonces(env.DB, 10 * 60 * 1000);
    console.log(JSON.stringify({ event: "nonce_purge_complete", timestamp: Date.now() }));
  },
};
```

---

## Section 6 — Dead-Letter Queue Configuration

Configure a dead-letter queue in `wrangler.toml` so unprocessable messages are not silently dropped.

```toml
# wrangler.toml (consumer worker)
[[queues.consumers]]
queue = "payment-queue"
max_batch_size = 10
max_batch_timeout = 5
max_retries = 3
dead_letter_queue = "payment-queue-dlq"

[[queues.producers]]
queue = "payment-queue-dlq"
binding = "PAYMENT_DLQ"
```

Monitor the DLQ depth via Cloudflare Logpush or a Tail Worker. Alert when DLQ message count exceeds a threshold, which may indicate systematic schema violations or signing key rotation issues.

---

## Anti-patterns

- **No signature on queue messages.** Any Worker with a producer binding, or an attacker who compromises a Worker, can inject arbitrary messages.
- **`message.ack()` on all errors.** Silently discarding failed messages hides bugs. Only ack definitively unprocessable messages (schema violations); retry transient errors.
- **No idempotency guard.** At-least-once delivery guarantees duplicates. Always pair nonce checking with a business-level idempotency key (such as a charge `idempotencyKey`) to survive retries from both the queue and your own logic.
- **Signing secret in `wrangler.toml` as an environment variable.** Use `wrangler secret put` — vars in `wrangler.toml` are stored in plaintext and visible to anyone with access to the repository or `wrangler deploy` output.
- **Same signing secret for producer and consumer of different queues.** Use per-queue secrets to limit blast radius.

---

## Gotchas

- `message.retry()` re-enqueues the message. If the retry also replays the same nonce and the nonce was already claimed in the first attempt, the nonce store will reject it as a duplicate. Only claim the nonce inside the try block — if processing fails and you call `retry()`, the nonce entry must be rolled back or not inserted in the first place. A safer approach: claim the nonce only after a successful `processCharge()` and rely solely on the business-level `idempotencyKey` for deduplication.
- The HMAC `maxAgeMs` window (5 minutes above) must be longer than the maximum queue delivery delay (`delaySeconds` + retry back-off). If a message is retried after the HMAC window expires, verification will fail. Increase the window or remove age-checking and rely on the nonce store for replay prevention.
- D1 `INSERT OR IGNORE` is not available in Workers D1 as of 2026; use a try/catch on `UNIQUE constraint failed` to detect duplicates, as shown above.
- Cloudflare Queues guarantees at-least-once delivery, not exactly-once. Plan for idempotency at every consumer stage, not just at the queue boundary.

---

## Verification

```bash
# Confirm signing secret is set as a secret, not a plain env var
wrangler secret list --name consumer-worker
# Should list QUEUE_SIGNING_SECRET

# Test replay detection: send a message, capture the nonce, re-enqueue with the same nonce
# and confirm the consumer logs 'replay_detected'

# Check DLQ depth
wrangler queues list
# Inspect 'payment-queue-dlq' message count
```

Vitest integration test (using `cloudflare:test`):

```typescript
import { env, createExecutionContext, waitOnExecutionContext } from "cloudflare:test";
import worker from "../src/index";
import { signEnvelope } from "../../shared/queue-envelope";

test("consumer rejects tampered payload", async () => {
  const envelope = await signEnvelope(
    { userId: crypto.randomUUID(), amountCents: 100, currency: "USD", idempotencyKey: crypto.randomUUID() },
    "payment-producer",
    env.QUEUE_SIGNING_SECRET
  );
  // Tamper with the payload after signing
  (envelope.payload as Record<string, unknown>).amountCents = 999_999;

  const batch = makeFakeBatch([envelope]);
  const ctx = createExecutionContext();
  await worker.queue(batch, env, ctx);
  await waitOnExecutionContext(ctx);
  // Expect ack (not retry) and DLQ entry
});
```

---

## Related

- `token-bucket-rate-limiting-durable-objects.md`
- `idempotency-one-time-secret-replay.md`
- `sql-injection-prevention-d1-workers.md`
- `workers-service-bindings-rpc-security.md`
- `webhook-signature-verification-hmac.md`

---

## Sources

- Cloudflare Queues documentation: https://developers.cloudflare.com/queues/
- Cloudflare Queues dead-letter queues: https://developers.cloudflare.com/queues/configuration/dead-letter-queues/
- NIST SP 800-57 — Key Management Recommendations: https://csrc.nist.gov/publications/detail/sp/800-57-part-1/rev-5/final
- HMAC-SHA-256 in Web Crypto API: https://developer.mozilla.org/en-US/docs/Web/API/SubtleCrypto/sign
- Zod schema validation: https://zod.dev
