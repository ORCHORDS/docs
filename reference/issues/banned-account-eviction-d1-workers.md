# Banned Account Eviction on Anonymous Platform with D1 and Workers

Date: 2026-08-23
Author: example.com
Status: production

## Symptom / Use-case

When example project (example.com) bans an anonymous account, the ban must do more than flip a flag in D1. The banned session token must be invalidated across all active Durable Objects holding per-session state, the account's content must be soft-deleted or shadow-suppressed from feeds without destroying evidence needed for legal holds, and any Cloudflare KV cache entries that would continue serving the account's content must be purged. Failing to complete all three steps allows the banned account to continue operating via cached responses or stale Durable Object state.

A second symptom is that on an anonymous platform, banned actors immediately re-register with a fresh anonymous session. The eviction system must therefore also write the banned account's behavioral fingerprint to a blocklist in D1 and KV so that the re-registration detection pipeline can catch the returning actor within minutes rather than days.

## Context

example project anonymous accounts are identified by a session token derived from Cloudflare Turnstile attestation combined with a per-install random ID. The eviction pipeline must coordinate across four systems in a defined order: (1) D1 — canonical ban record and content suppression; (2) Cloudflare KV — CDN-layer content cache purge; (3) Durable Objects — per-session state cleanup; (4) behavioral fingerprint blocklist — re-registration prevention.

A Workers Queue acts as the orchestration backbone. The ban decision is written to D1 and a `ban_event` message is enqueued atomically. The queue consumer drives the remaining eviction steps asynchronously, with retry and dead-letter handling so a transient KV timeout does not leave a partially evicted account.

## Step 1: Ban Record and Content Suppression in D1

The initial ban action writes the canonical ban record and suppresses all content authored by the account in a single D1 batch. D1's batch API ensures both writes succeed or both fail.

```typescript
// worker: ban-action.ts
export interface Env {
  DB: D1Database;
  BAN_EVENTS: Queue;
}

interface BanRequest {
  accountId: string;       // hashed anon session token
  reason: string;
  bannedBy: string;        // moderator ID or 'system'
  retainContent: boolean;  // true = legal hold; false = immediate suppression
  fingerprintHash: string; // behavioral fingerprint for re-registration detection
}

export async function executeBan(env: Env, ban: BanRequest): Promise<string> {
  const banId = crypto.randomUUID();
  const now = Math.floor(Date.now() / 1000);

  await env.DB.batch([
    env.DB.prepare(`
      INSERT INTO account_bans (ban_id, account_id, reason, banned_by, banned_at, status)
      VALUES (?1, ?2, ?3, ?4, ?5, 'active')
      ON CONFLICT(account_id) DO UPDATE SET
        reason    = excluded.reason,
        banned_by = excluded.banned_by,
        banned_at = excluded.banned_at,
        status    = 'active'
    `).bind(banId, ban.accountId, ban.reason, ban.bannedBy, now),

    // Suppress or flag content depending on legal hold requirement
    ban.retainContent
      ? env.DB.prepare(`
          UPDATE posts SET visibility = 'legal_hold'
          WHERE author_id = ?1 AND visibility = 'public'
        `).bind(ban.accountId)
      : env.DB.prepare(`
          UPDATE posts SET visibility = 'banned_suppressed'
          WHERE author_id = ?1 AND visibility = 'public'
        `).bind(ban.accountId),

    env.DB.prepare(`
      INSERT INTO fingerprint_blocklist (fingerprint_hash, source_account_id, blocked_at, reason)
      VALUES (?1, ?2, ?3, ?4)
      ON CONFLICT(fingerprint_hash) DO NOTHING
    `).bind(ban.fingerprintHash, ban.accountId, now, ban.reason),
  ]);

  // Enqueue async eviction steps
  await env.BAN_EVENTS.send({
    banId,
    accountId: ban.accountId,
    fingerprintHash: ban.fingerprintHash,
    step: 'kv_purge',
  });

  return banId;
}
```

## Step 2: KV Cache Purge via Queue Consumer

The queue consumer receives the `ban_event` and purges all KV cache entries for the banned account's content. KV `list()` with a prefix allows bulk key enumeration without knowing individual content IDs.

```typescript
// worker: eviction-consumer.ts
export interface Env {
  DB: D1Database;
  CONTENT_CACHE: KVNamespace;
  SESSION_STORE: KVNamespace;
  BAN_EVENTS: Queue;
  DURABLE_SESSION: DurableObjectNamespace;
}

interface BanEvent {
  banId: string;
  accountId: string;
  fingerprintHash: string;
  step: 'kv_purge' | 'do_eviction' | 'complete';
}

export default {
  async queue(batch: MessageBatch<BanEvent>, env: Env): Promise<void> {
    for (const message of batch.messages) {
      const event = message.body;

      try {
        if (event.step === 'kv_purge') {
          await purgeKVCache(env, event.accountId);
          // Re-enqueue next step
          await env.BAN_EVENTS.send({ ...event, step: 'do_eviction' });
          message.ack();

        } else if (event.step === 'do_eviction') {
          await evictDurableObject(env, event.accountId);
          await env.BAN_EVENTS.send({ ...event, step: 'complete' });
          message.ack();

        } else if (event.step === 'complete') {
          await markBanComplete(env.DB, event.banId);
          message.ack();
        }
      } catch (err) {
        console.error(`Eviction step ${event.step} failed for ${event.accountId}:`, err);
        // Do NOT ack; let the queue retry with backoff
        message.retry({ delaySeconds: 30 });
      }
    }
  },
};

async function purgeKVCache(env: Env, accountId: string): Promise<void> {
  const prefix = `content:${accountId}:`;
  let cursor: string | undefined;

  // Paginate through all KV keys for this account
  do {
    const page = await env.CONTENT_CACHE.list({ prefix, cursor, limit: 100 });
    const deleteOps = page.keys.map(k => env.CONTENT_CACHE.delete(k.name));
    await Promise.all(deleteOps);
    cursor = page.list_complete ? undefined : page.cursor;
  } while (cursor);

  // Also invalidate the session token
  await env.SESSION_STORE.delete(`session:${accountId}`);
}

async function evictDurableObject(env: Env, accountId: string): Promise<void> {
  // Send an eviction signal to the account's Durable Object so it clears in-memory state
  const id = env.DURABLE_SESSION.idFromName(accountId);
  const stub = env.DURABLE_SESSION.get(id);

  await stub.fetch('https://internal/evict', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ accountId, reason: 'ban' }),
  });
}

async function markBanComplete(db: D1Database, banId: string): Promise<void> {
  await db.prepare(`
    UPDATE account_bans SET eviction_completed_at = unixepoch() WHERE ban_id = ?1
  `).bind(banId).run();
}
```

## Step 3: Durable Object Self-Eviction

The session Durable Object receives the eviction signal and clears its in-memory state, sets a permanent banned flag in its durable storage, and returns 403 for all subsequent requests from that account.

```typescript
// durable-object: SessionObject.ts
export class SessionObject implements DurableObject {
  private banned = false;

  constructor(
    private readonly state: DurableObjectState,
    _env: unknown
  ) {
    this.state.blockConcurrencyWhile(async () => {
      this.banned = (await this.state.storage.get<boolean>('banned')) ?? false;
    });
  }

  async fetch(request: Request): Promise<Response> {
    const url = new URL(request.url);

    if (url.pathname === '/evict') {
      await this.state.storage.put('banned', true);
      await this.state.storage.deleteAll(); // clear all transient state
      await this.state.storage.put('banned', true); // re-set after deleteAll
      this.banned = true;
      return new Response('evicted', { status: 200 });
    }

    if (this.banned) {
      return new Response('Account banned', { status: 403 });
    }

    // Normal session handling...
    return new Response('ok');
  }
}
```

## Step 4: Re-registration Detection via Fingerprint Blocklist

New anonymous registrations are checked against the fingerprint blocklist in D1 and a KV-cached bloom-filter approximation for speed. Matching fingerprints are rejected at Turnstile attestation time.

```typescript
// worker: registration-gate.ts
export interface Env {
  DB: D1Database;
  BLOCKLIST_CACHE: KVNamespace;
}

interface RegistrationAttempt {
  fingerprintHash: string;
  turnstileToken: string;
  ipAsn: string;
}

export async function checkRegistration(
  env: Env,
  attempt: RegistrationAttempt
): Promise<{ allowed: boolean; reason?: string }> {
  // Fast path: KV cache check (stale-while-revalidate acceptable here)
  const cached = await env.BLOCKLIST_CACHE.get(`bl:${attempt.fingerprintHash}`);
  if (cached === 'blocked') {
    return { allowed: false, reason: 'fingerprint_blocklisted' };
  }

  // Authoritative D1 check
  const row = await env.DB.prepare(`
    SELECT reason FROM fingerprint_blocklist WHERE fingerprint_hash = ?1
  `).bind(attempt.fingerprintHash).first<{ reason: string }>();

  if (row) {
    // Back-populate KV cache with 24h TTL
    await env.BLOCKLIST_CACHE.put(`bl:${attempt.fingerprintHash}`, 'blocked', {
      expirationTtl: 86400,
    });
    return { allowed: false, reason: 'fingerprint_blocklisted' };
  }

  return { allowed: true };
}
```

## Anti-patterns

- Banning by setting a single flag in D1 without purging KV or Durable Object state — the account continues to receive cached responses and the Durable Object retains its rate-limit credits, effectively granting continued access
- Deleting banned content immediately without a legal hold option — in many jurisdictions (UK Online Safety Act, DSA) platforms must preserve reported content for potential law enforcement requests; always soft-delete with a legal hold visibility flag
- Running all eviction steps synchronously in the ban handler — KV list-and-delete for a prolific account can involve hundreds of API calls; doing this synchronously times out the ban handler and leaves eviction incomplete
- Writing the fingerprint blocklist only to KV — KV is a cache, not a source of truth; D1 is the authoritative blocklist and KV is a fast-path cache that can be rebuilt from D1 if corrupted or expired
- Treating Durable Object `deleteAll()` as sufficient eviction — `deleteAll()` clears storage but the DO instance remains in memory and `banned = false` in the instance variable until the object is garbage-collected; always re-set the `banned` flag in durable storage after `deleteAll()`

## Gotchas

- Cloudflare KV `list()` returns at most 1000 keys per call and requires cursor-based pagination for accounts with large content volumes; always loop until `list_complete === true`
- Durable Objects are not immediately garbage-collected after `deleteAll()`; a request arriving within milliseconds of eviction may still hit the old in-memory state before the `banned` flag propagates — the eviction fetch handler sets `this.banned = true` in memory to close this window
- Queue `message.retry({ delaySeconds: 30 })` requires the queue to be configured with `max_retries >= 1`; the default is 3 retries, which is sufficient for transient KV timeouts
- The `fingerprintHash` must be computed from signals that survive a re-install (device canvas fingerprint bucket, timezone + language combination, behavioral biometrics) not from the session token itself — a re-registering actor generates a new session token but the same device fingerprint
- D1 `batch()` is not a true transaction in the ACID sense on read-modify-write operations, but for the ban write (insert + update) it provides atomic success-or-failure semantics sufficient for this use case

## Verification

1. Create a test account in D1 with two posts at `visibility = 'public'` and a KV cache entry at `content:{accountId}:post1`.
2. Call `executeBan` with `retainContent: false` and a synthetic fingerprint hash.
3. Query D1 `account_bans` — expect one row with `status = 'active'` and `eviction_completed_at IS NULL`.
4. Query `posts` — expect both posts to have `visibility = 'banned_suppressed'`.
5. Consume from `BAN_EVENTS` queue through all three steps (kv_purge → do_eviction → complete).
6. Query D1 `account_bans` — expect `eviction_completed_at` to be set.
7. Fetch the KV key `content:{accountId}:post1` — expect `null` (purged).
8. Call `checkRegistration` with the same fingerprint hash — expect `{ allowed: false, reason: 'fingerprint_blocklisted' }`.
9. Send a request to the Durable Object via `evictDurableObject` and then a follow-up fetch to the DO — expect HTTP 403.

## Related

- `account-suspension-appeals-worker-workflow.md`
- `ban-evasion-device-fingerprint-detection-d1.md`
- `repeat-offender-detection-anonymous-sessions.md`
- `legal-hold-evidence-preservation-d1-r2.md`

## Sources

- Cloudflare Durable Objects storage API: https://developers.cloudflare.com/durable-objects/api/storage-api/
- Cloudflare KV list and pagination: https://developers.cloudflare.com/kv/api/list-keys/
- Cloudflare Queues retry and DLQ configuration: https://developers.cloudflare.com/queues/configuration/
