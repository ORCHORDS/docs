# KV Namespace Corruption Partial Write Postmortem

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom

After a rollout that changed the serialisation format of session objects, approximately 3 % of
active users encountered silent logouts or stale permission sets. The bug was invisible in
staging because the new Worker deserialised correctly; the corruption only appeared when an old
Worker wrote a key that a new Worker later read, or vice-versa. Support tickets spiked over two
days before the root cause was identified.

## Context

Workers KV is an eventually consistent, edge-cached key-value store. Writes propagate globally
within ~60 s, but reads may return a cached value for up to 60 s after a write. The team stored
serialised session objects (`JSON.stringify`) under a versioned key pattern. During the rollout,
two versions of the Worker ran simultaneously for ~8 minutes. The new version wrote a new field
(`permissions` as an array) while the old version expected a legacy shape (`perms` as a string).
Neither version validated the shape on read; both silently used whatever they got.

---

## Root Cause: No Schema Version in the Envelope

```typescript
// BEFORE — raw JSON, no version field
async function writeSession(env: Env, sid: string, session: Session): Promise<void> {
  await env.SESSIONS.put(`sess:${sid}`, JSON.stringify(session), { expirationTtl: 3600 });
}

async function readSession(env: Env, sid: string): Promise<Session | null> {
  const raw = await env.SESSIONS.get(`sess:${sid}`);
  if (!raw) return null;
  return JSON.parse(raw) as Session; // No validation — silent corruption consumer
}

// AFTER — envelope with version field; unknown versions fast-fail
interface SessionEnvelope {
  v: number;
  payload: unknown;
}

const CURRENT_VERSION = 2;

async function writeSessionV2(env: Env, sid: string, session: SessionV2): Promise<void> {
  const envelope: SessionEnvelope = { v: CURRENT_VERSION, payload: session };
  await env.SESSIONS.put(`sess:${sid}`, JSON.stringify(envelope), { expirationTtl: 3600 });
}

async function readSessionV2(env: Env, sid: string): Promise<SessionV2 | null> {
  const raw = await env.SESSIONS.get(`sess:${sid}`);
  if (!raw) return null;
  const envelope: SessionEnvelope = JSON.parse(raw);
  if (envelope.v !== CURRENT_VERSION) {
    // Treat as expired — force re-auth rather than silently misread
    await env.SESSIONS.delete(`sess:${sid}`);
    return null;
  }
  return envelope.payload as SessionV2;
}
```

## Read Validation with Zod

```typescript
import { z } from 'zod';

const SessionV2Schema = z.object({
  userId: z.string().uuid(),
  permissions: z.array(z.string()),  // was `perms: z.string()` in v1
  expiresAt: z.number(),
});

type SessionV2 = z.infer<typeof SessionV2Schema>;

async function readSessionValidated(env: Env, sid: string): Promise<SessionV2 | null> {
  const raw = await env.SESSIONS.get(`sess:${sid}`);
  if (!raw) return null;

  let envelope: SessionEnvelope;
  try {
    envelope = JSON.parse(raw);
  } catch {
    // Corrupted bytes — delete and treat as expired
    await env.SESSIONS.delete(`sess:${sid}`);
    return null;
  }

  if (envelope.v !== CURRENT_VERSION) {
    await env.SESSIONS.delete(`sess:${sid}`);
    return null;
  }

  const parsed = SessionV2Schema.safeParse(envelope.payload);
  if (!parsed.success) {
    console.error('Session schema mismatch', { sid, error: parsed.error.flatten() });
    await env.SESSIONS.delete(`sess:${sid}`);
    return null;
  }
  return parsed.data;
}
```

## Canary-Safe Rollout: Dual Writes During Migration

```typescript
// During rollout: write both v1 and v2 so the old Worker can still read
async function writeSessionDual(
  env: Env,
  sid: string,
  sessionV1: SessionV1,
  sessionV2: SessionV2,
): Promise<void> {
  // v1 key for old workers still in rotation
  await env.SESSIONS.put(
    `sess:v1:${sid}`,
    JSON.stringify({ v: 1, payload: sessionV1 }),
    { expirationTtl: 3600 },
  );
  // v2 key for new workers
  await env.SESSIONS.put(
    `sess:v2:${sid}`,
    JSON.stringify({ v: 2, payload: sessionV2 }),
    { expirationTtl: 3600 },
  );
}

// New worker reads v2 first, falls back to v1 key, migrates on read
async function readSessionMigrating(env: Env, sid: string): Promise<SessionV2 | null> {
  const rawV2 = await env.SESSIONS.get(`sess:v2:${sid}`);
  if (rawV2) {
    // Happy path
    return SessionV2Schema.parse(JSON.parse(rawV2).payload);
  }

  const rawV1 = await env.SESSIONS.get(`sess:v1:${sid}`);
  if (!rawV1) return null;

  // Migrate: promote v1 → v2 on read
  const v1 = SessionV1Schema.parse(JSON.parse(rawV1).payload);
  const v2 = migrateV1toV2(v1);
  // Background write; do not block the response
  await env.SESSIONS.put(
    `sess:v2:${sid}`,
    JSON.stringify({ v: 2, payload: v2 }),
    { expirationTtl: 3600 },
  );
  return v2;
}
```

## Detecting Corruption in Production via Tail Worker

```typescript
// tail-worker.ts — attached to the main Worker
export default {
  async tail(events: TraceItem[]): Promise<void> {
    for (const event of events) {
      for (const log of event.logs) {
        if (log.message[0] === 'Session schema mismatch') {
          // Emit to Analytics Engine for monitoring
          await fetch('https://api.cloudflare.com/client/v4/...', {
            method: 'POST',
            body: JSON.stringify({ name: 'kv_schema_mismatch', value: 1 }),
          });
        }
      }
    }
  },
};
```

## Cleanup: Purge Legacy Keys After Rollout Stabilises

```typescript
// Run from a Cron Trigger once dual-write window closes (e.g. 7 days)
export default {
  async scheduled(event: ScheduledEvent, env: Env): Promise<void> {
    const { keys } = await env.SESSIONS.list({ prefix: 'sess:v1:' });
    for (const key of keys) {
      // Only delete if a v2 counterpart exists so we don't orphan active sessions
      const sid = key.name.replace('sess:v1:', '');
      const v2Exists = await env.SESSIONS.get(`sess:v2:${sid}`, { cacheTtl: 0 });
      if (v2Exists) {
        await env.SESSIONS.delete(key.name);
      }
    }
  },
};
```

---

## Anti-Patterns

- **Casting raw KV output directly to a typed interface.** `JSON.parse(raw) as MyType` skips
  runtime validation. TypeScript types are erased at runtime; `as` is a lie the compiler accepts.
- **No version field in the stored envelope.** Any future shape change creates a silent
  compatibility window during deploys.
- **Assuming deploys are atomic.** Workers traffic is shifted gradually. Old and new isolates
  run concurrently for several minutes; both will read and write to the same KV namespace.
- **Using `cacheTtl` default on reads during debug.** KV's default cache can serve a stale
  write for up to 60 s. Pass `{ cacheTtl: 0 }` when you need consistency (at higher cost).

## Gotchas

- KV `list()` is eventually consistent too — a key deleted 30 s ago may still appear in a
  listing. Do not rely on `list()` for real-time inventory.
- KV `put()` with `expirationTtl` does not extend an existing key's TTL if the value is the
  same; the write still succeeds, resetting the TTL from the call time.
- Zod `safeParse` is the correct call on untrusted data; `parse` throws and can leak internal
  schema details into error responses if not caught.
- Large KV values (>25 MB) are rejected silently in some SDK versions — add a byte-length
  check before writing.

## Verification

```bash
# Check for schema mismatch logs in production
wrangler tail --format=pretty 2>&1 | grep "Session schema mismatch"

# Verify version envelope is present in a sample of keys
wrangler kv key get --namespace-id=$NS_ID "sess:v2:some-test-sid" | jq '.v'

# Count v1 legacy keys remaining (should drop to zero after cleanup)
wrangler kv key list --namespace-id=$NS_ID --prefix="sess:v1:" | jq 'length'
```

## Related

- `kv-consistency-mode-eventual-reads-production-bug.md`
- `kv-write-rate-limit-exceeded-postmortem.md`
- `kv-namespace-deleted-wrong-environment-postmortem.md`
- `silent-data-loss-partial-writes.md`
- `migrations-must-be-backward-compatible.md`

## Sources

- Workers KV consistency docs: https://developers.cloudflare.com/kv/reference/consistency/
- KV limits: https://developers.cloudflare.com/kv/platform/limits/
- Zod validation: https://zod.dev/
- Cloudflare KV `get` options: https://developers.cloudflare.com/kv/api/read-key-value-pairs/
