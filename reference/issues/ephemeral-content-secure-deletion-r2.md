# Ephemeral Content Secure Deletion from R2 after TTL Expiry

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case
Stories and disappearing messages appear deleted to the user but remain accessible via
direct R2 signed URLs and warm CDN edge caches, creating privacy exposure after the
intended expiry window.

## Context
Ephemeral content (24-hour stories, disappearing DMs, timed posts) must be unrecoverable
once TTL elapses — not just hidden from the UI. On Cloudflare Workers, deletion has three
layers: R2 object removal, CDN cache purge, and cryptographic key rotation so any cached
ciphertext is computationally useless. GDPR Article 17 and CPRA treat "inaccessible but
retained" ciphertext as still-personal data if the decryption key still exists.

## D1 TTL Registry and Cron Trigger Scheduling

Track every ephemeral object in D1 with its expiry timestamp, encryption key ID, and
Cache-Tag for targeted purge.

```sql
-- migrations/0012_ephemeral_registry.sql
CREATE TABLE ephemeral_objects (
  id          TEXT PRIMARY KEY,          -- nanoid
  r2_key      TEXT NOT NULL,
  kek_id      TEXT NOT NULL,             -- key-encryption-key id in KV
  cache_tag   TEXT NOT NULL,             -- e.g. "eph-<user_id>-<post_id>"
  expires_at  INTEGER NOT NULL,          -- unix seconds
  deleted_at  INTEGER,
  created_at  INTEGER NOT NULL DEFAULT (unixepoch())
);
CREATE INDEX idx_ephemeral_expires ON ephemeral_objects(expires_at) WHERE deleted_at IS NULL;
```

```typescript
// src/jobs/purge-expired-ephemeral.ts
import type { Env } from '../env';

export async function purgeExpiredEphemeral(env: Env): Promise<void> {
  const now = Math.floor(Date.now() / 1000);

  // Fetch a bounded batch — cron fires every minute, so 200 rows per tick is safe
  const { results } = await env.DB.prepare(
    `SELECT id, r2_key, kek_id, cache_tag
     FROM ephemeral_objects
     WHERE expires_at <= ? AND deleted_at IS NULL
     LIMIT 200`
  ).bind(now).all<{ id: string; r2_key: string; kek_id: string; cache_tag: string }>();

  if (!results.length) return;

  await Promise.allSettled(results.map(row => deleteOneObject(row, env, now)));
}

async function deleteOneObject(
  row: { id: string; r2_key: string; kek_id: string; cache_tag: string },
  env: Env,
  now: number,
): Promise<void> {
  // 1. Delete the R2 object
  await env.CONTENT_BUCKET.delete(row.r2_key);

  // 2. Destroy the key-encryption-key — renders any cached ciphertext unreadable
  await env.CRYPTO_KEYS.delete(row.kek_id);

  // 3. Purge CDN cache by tag
  await purgeCacheTag(row.cache_tag, env);

  // 4. Mark deleted in D1 (retain tombstone for audit; not the content)
  await env.DB.prepare(
    `UPDATE ephemeral_objects SET deleted_at = ? WHERE id = ?`
  ).bind(now, row.id).run();
}
```

Wire the cron in `wrangler.toml`:

```toml
[[triggers.crons]]
cron = "* * * * *"   # every minute
```

```typescript
// src/index.ts  (scheduled handler)
export default {
  async scheduled(_event: ScheduledEvent, env: Env, _ctx: ExecutionContext) {
    await purgeExpiredEphemeral(env);
  },
};
```

## Envelope Encryption on Upload

Encrypt each ephemeral object with a unique data-encryption key (DEK) wrapped by a
key-encryption key (KEK) stored in KV. Deleting the KEK makes the DEK irrecoverable.

```typescript
// src/lib/ephemeral-upload.ts
import { nanoid } from 'nanoid';

export async function uploadEphemeralContent(
  body: ReadableStream,
  ttlSeconds: number,
  userId: string,
  env: Env,
): Promise<{ objectId: string; cacheTag: string; expiresAt: number }> {
  const objectId  = nanoid();
  const kekId     = `kek-${objectId}`;
  const cacheTag  = `eph-${userId}-${objectId}`;
  const expiresAt = Math.floor(Date.now() / 1000) + ttlSeconds;

  // Generate DEK and KEK in SubtleCrypto
  const dek = await crypto.subtle.generateKey({ name: 'AES-GCM', length: 256 }, true, ['encrypt']);
  const kek = await crypto.subtle.generateKey({ name: 'AES-KW',  length: 256 }, true, ['wrapKey', 'unwrapKey']);

  const iv         = crypto.getRandomValues(new Uint8Array(12));
  const rawBody    = await new Response(body).arrayBuffer();
  const ciphertext = await crypto.subtle.encrypt({ name: 'AES-GCM', iv }, dek, rawBody);

  // Wrap DEK with KEK; store wrapped key in KV (expires with object TTL + 60s grace)
  const wrappedDek = await crypto.subtle.wrapKey('raw', dek, kek, 'AES-KW');
  const rawKek     = await crypto.subtle.exportKey('raw', kek);

  await env.CRYPTO_KEYS.put(kekId, rawKek, { expirationTtl: ttlSeconds + 60 });

  // Store: iv + wrappedDek header + ciphertext in R2
  const header  = new Uint8Array(wrappedDek);
  const payload = concat(iv, header, new Uint8Array(ciphertext));
  await env.CONTENT_BUCKET.put(objectId, payload, {
    customMetadata: { kekId, userId, expiresAt: String(expiresAt) },
    httpMetadata: { cacheControl: 'private, no-store' },
  });

  // Register in D1
  await env.DB.prepare(
    `INSERT INTO ephemeral_objects (id, r2_key, kek_id, cache_tag, expires_at)
     VALUES (?, ?, ?, ?, ?)`
  ).bind(objectId, objectId, kekId, cacheTag, expiresAt).run();

  return { objectId, cacheTag, expiresAt };
}

function concat(...arrays: Uint8Array[]): Uint8Array {
  const total  = arrays.reduce((n, a) => n + a.byteLength, 0);
  const result = new Uint8Array(total);
  let offset   = 0;
  for (const a of arrays) { result.set(a, offset); offset += a.byteLength; }
  return result;
}
```

## Cache Tag Purge via Cloudflare API

Serve ephemeral content with a `Cache-Tag` response header so zone-level purge is
surgical — it avoids clearing the whole edge cache.

```typescript
// src/lib/purge-cache.ts
export async function purgeCacheTag(tag: string, env: Env): Promise<void> {
  const res = await fetch(
    `https://api.cloudflare.com/client/v4/zones/${env.CF_ZONE_ID}/purge_cache`,
    {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${env.CF_PURGE_TOKEN}`,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ tags: [tag] }),
    }
  );
  if (!res.ok) {
    const body = await res.text();
    throw new Error(`Cache purge failed for tag ${tag}: ${body}`);
  }
}
```

On the read path, attach the tag so Cloudflare tracks it:

```typescript
// Inside your content-serve Worker
return new Response(decryptedStream, {
  headers: {
    'Cache-Control': 'private, max-age=30',
    'Cache-Tag': cacheTag,           // enables targeted purge
    'Content-Type': contentType,
  },
});
```

## Anti-patterns
- Relying solely on R2 lifecycle rules — they don't purge the CDN or destroy keys
- Storing the KEK in R2 metadata alongside the object it protects — defeats envelope encryption
- Bulk zone-wide cache purge — knocks warm assets for all users, causes unnecessary origin traffic
- Keeping a mapping of DEK → plaintext anywhere after object deletion
- Assuming `deleted_at IS NOT NULL` means content is unrecoverable without verifying key deletion

## Gotchas
- KV `expirationTtl` is not a deletion guarantee — add grace seconds and confirm via the purge cron
- `crypto.subtle.wrapKey` is available in Workers runtime; `crypto.subtle.encrypt` of streaming bodies
  requires buffering the stream first (memory-cap large uploads at the edge)
- Cloudflare Cache-Tag purge requires a paid zone plan and the `Cache-Tag` header must be present
  on at least one cached response before the tag is purgeable
- `CONTENT_BUCKET.delete()` is idempotent; it returns success even if the key doesn't exist —
  verify via `head()` before marking deleted if auditability matters
- Tombstone rows in `ephemeral_objects` must themselves be purged on a longer schedule to avoid
  D1 table bloat; a quarterly DELETE WHERE deleted_at < (now - 90 days) is sufficient

## Verification

```sql
-- Confirm no un-deleted rows past expiry
SELECT COUNT(*) AS overdue
FROM ephemeral_objects
WHERE expires_at < unixepoch() AND deleted_at IS NULL;

-- Spot-check a specific object's deletion timeline
SELECT id, r2_key, expires_at, deleted_at,
       deleted_at - expires_at AS lag_seconds
FROM ephemeral_objects
WHERE id = 'OBJECT_ID_HERE';
```

```bash
# Confirm R2 object is gone
wrangler r2 object head CONTENT_BUCKET <r2_key>   # expect "not found"

# Confirm KEK is gone from KV
wrangler kv key get --binding CRYPTO_KEYS kek-<objectId>  # expect "null"
```

## Related
- `gdpr-data-export-worker-r2-signed-url.md` — export pipeline before deletion
- `legal-hold-evidence-preservation-d1-r2.md` — when deletion must be deferred for legal hold
- `ncii-nonconsensual-intimate-imagery-detection-workers-ai.md` — ephemeral NCII still requires proactive scanning before storage
- `right-to-erasure-gdpr-ccpa-deletion-workflow-d1-r2.md` — user-initiated full account deletion

## Sources
- https://developers.cloudflare.com/r2/api/workers/workers-api-reference/
- https://developers.cloudflare.com/workers/runtime-apis/web-crypto/
- https://developers.cloudflare.com/cache/how-to/purge-cache/purge-by-cache-tags/
- https://developers.cloudflare.com/kv/api/write-key-value-pairs/#expiring-keys
- https://gdpr-info.eu/art-17-gdpr/
