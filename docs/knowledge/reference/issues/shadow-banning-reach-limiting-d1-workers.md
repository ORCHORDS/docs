# Shadow Banning: Limiting Reach of Flagged Accounts Without Notifying Them

**Date:** 2026-08-22
**Author:** example.com
**Status:** production

---

## Symptom / Use-case

Flagged accounts on example project continue to post content that appears normal to them but should be invisible or severely down-ranked for the rest of the platform. You need a covert reach-limiter that survives account re-registration attempts, degrades gracefully under high write volume, and leaves zero fingerprint in client-facing API responses.

---

## Context

Shadow banning (also called ghost banning or stealth banning) is a trust-and-safety technique where the platform silently restricts a bad actor's reach rather than issuing an explicit suspension. The user can still post; they see their own content; but no one else does. This prevents evasion through immediate re-registration and gives investigators time to collect evidence before a formal enforcement action.

On example project the canonical store is Cloudflare D1 (SQLite). Feed assembly and content delivery run in Workers. The shadow-ban flag must be:

- Applied atomically with zero client visibility
- Checked at sub-millisecond latency on every feed query
- Auditable for legal/appeals purposes
- Reversible without cache poisoning

---

## Section 1: Schema Design

Add a `shadow_ban` table separate from the accounts table so DDL migrations on one do not lock the other.

```sql
-- migration 0023_shadow_ban.sql
CREATE TABLE IF NOT EXISTS shadow_ban (
  account_id    TEXT    NOT NULL PRIMARY KEY,
  applied_at    INTEGER NOT NULL,            -- Unix ms
  applied_by    TEXT    NOT NULL,            -- moderator ID or 'system'
  reason_code   TEXT    NOT NULL,            -- enum: SPAM | CIB | CSAM_ADJACENT | ABUSE
  visibility    TEXT    NOT NULL DEFAULT 'self_only',
  -- self_only: only the owner sees their content
  -- degraded:  content appears with rank score = 0
  -- removed:   content excluded from all indexes
  expires_at    INTEGER,                     -- NULL = indefinite
  audit_json    TEXT                         -- JSON blob for appeals record
);

CREATE INDEX IF NOT EXISTS idx_shadow_ban_account
  ON shadow_ban (account_id, expires_at);
```

The `accounts` table does **not** gain a `is_banned` column — querying the shadow_ban table is the single source of truth.

---

## Section 2: Applying a Shadow Ban

```typescript
// src/moderation/shadow-ban.ts
import type { Env } from '../types';

export interface ShadowBanOptions {
  accountId: string;
  appliedBy: string;
  reasonCode: 'SPAM' | 'CIB' | 'CSAM_ADJACENT' | 'ABUSE';
  visibility?: 'self_only' | 'degraded' | 'removed';
  ttlSeconds?: number;
  auditJson?: Record<string, unknown>;
}

export async function applyShadowBan(env: Env, opts: ShadowBanOptions): Promise<void> {
  const now = Date.now();
  const expiresAt = opts.ttlSeconds ? now + opts.ttlSeconds * 1000 : null;

  await env.DB.prepare(
    `INSERT INTO shadow_ban
       (account_id, applied_at, applied_by, reason_code, visibility, expires_at, audit_json)
     VALUES (?, ?, ?, ?, ?, ?, ?)
     ON CONFLICT(account_id) DO UPDATE SET
       applied_at  = excluded.applied_at,
       applied_by  = excluded.applied_by,
       reason_code = excluded.reason_code,
       visibility  = excluded.visibility,
       expires_at  = excluded.expires_at,
       audit_json  = excluded.audit_json`
  )
    .bind(
      opts.accountId,
      now,
      opts.appliedBy,
      opts.reasonCode,
      opts.visibility ?? 'self_only',
      expiresAt,
      opts.auditJson ? JSON.stringify(opts.auditJson) : null
    )
    .run();

  // Purge KV cache so the next feed request picks up the flag immediately.
  await env.SHADOW_BAN_KV.delete(`sb:${opts.accountId}`);
}
```

---

## Section 3: Low-Latency Lookup with KV Cache

D1 read latency averages ~3–8 ms. For hot feed paths serving thousands of requests per second, cache the shadow-ban status in Workers KV with a short TTL.

```typescript
// src/moderation/shadow-ban-lookup.ts
import type { Env } from '../types';

export interface BanStatus {
  isBanned: boolean;
  visibility: 'self_only' | 'degraded' | 'removed' | null;
}

const KV_TTL = 60; // seconds

export async function getBanStatus(env: Env, accountId: string): Promise<BanStatus> {
  const cacheKey = `sb:${accountId}`;

  // 1. Check KV first (< 1 ms in-colo)
  const cached = await env.SHADOW_BAN_KV.get(cacheKey, 'json');
  if (cached !== null) return cached as BanStatus;

  // 2. Fall back to D1
  const row = await env.DB
    .prepare(
      `SELECT visibility FROM shadow_ban
       WHERE account_id = ?
         AND (expires_at IS NULL OR expires_at > ?)`
    )
    .bind(accountId, Date.now())
    .first<{ visibility: string }>();

  const status: BanStatus = row
    ? { isBanned: true, visibility: row.visibility as BanStatus['visibility'] }
    : { isBanned: false, visibility: null };

  // 3. Backfill KV — expirationTtl prevents stale bans surviving indefinitely
  await env.SHADOW_BAN_KV.put(cacheKey, JSON.stringify(status), {
    expirationTtl: KV_TTL,
  });

  return status;
}
```

---

## Section 4: Feed Filtering in Workers

Integrate the status check into the feed assembly pipeline without leaking any information to the requesting user.

```typescript
// src/workers/feed.ts
import { getBanStatus } from '../moderation/shadow-ban-lookup';
import type { Env, Post } from '../types';

export async function assembleFeed(
  env: Env,
  viewerId: string,
  cursor: string | null
): Promise<Post[]> {
  const rawPosts = await fetchRawFeed(env, cursor, 50);

  const filtered: Post[] = [];

  for (const post of rawPosts) {
    if (post.authorId === viewerId) {
      // Authors always see their own content — critical for stealth.
      filtered.push(post);
      continue;
    }

    const ban = await getBanStatus(env, post.authorId);

    if (!ban.isBanned) {
      filtered.push(post);
      continue;
    }

    // 'degraded' posts can appear in search but not feeds — omit here.
    // 'self_only' and 'removed' never appear for other viewers.
    // No error, no empty-slot indicator, just silent exclusion.
  }

  return filtered;
}

async function fetchRawFeed(env: Env, cursor: string | null, limit: number): Promise<Post[]> {
  const { results } = await env.DB
    .prepare(
      `SELECT id, author_id, body, created_at
       FROM posts
       WHERE (? IS NULL OR id < ?)
       ORDER BY id DESC
       LIMIT ?`
    )
    .bind(cursor, cursor, limit)
    .all<Post>();
  return results;
}
```

---

## Section 5: Automatic Expiry Sweep

Expired bans should lift automatically. A scheduled Worker runs the cleanup.

```typescript
// src/workers/shadow-ban-sweep.ts  — scheduled cron: "0 * * * *"
import type { Env } from '../types';

export default {
  async scheduled(_event: ScheduledEvent, env: Env, _ctx: ExecutionContext): Promise<void> {
    const now = Date.now();

    const { results } = await env.DB
      .prepare(
        `DELETE FROM shadow_ban
         WHERE expires_at IS NOT NULL AND expires_at <= ?
         RETURNING account_id`
      )
      .bind(now)
      .all<{ account_id: string }>();

    // Flush KV entries for lifted bans so feeds update within seconds.
    await Promise.all(
      results.map(r => env.SHADOW_BAN_KV.delete(`sb:${r.account_id}`))
    );

    console.log(`Shadow ban sweep: lifted ${results.length} expired bans.`);
  },
};
```

---

## Section 6: Audit Log for Appeals

Every ban application must be reversible and auditable.

```typescript
// src/moderation/shadow-ban-audit.ts
import type { Env } from '../types';

export async function getBanAuditRecord(
  env: Env,
  accountId: string
): Promise<Record<string, unknown> | null> {
  const row = await env.DB
    .prepare(
      `SELECT account_id, applied_at, applied_by, reason_code,
              visibility, expires_at, audit_json
       FROM shadow_ban WHERE account_id = ?`
    )
    .bind(accountId)
    .first<Record<string, string | number | null>>();

  if (!row) return null;

  return {
    ...row,
    audit_json: row.audit_json ? JSON.parse(row.audit_json as string) : null,
  };
}

export async function liftShadowBan(
  env: Env,
  accountId: string,
  liftedBy: string
): Promise<void> {
  await env.DB
    .prepare(`DELETE FROM shadow_ban WHERE account_id = ?`)
    .bind(accountId)
    .run();

  await env.SHADOW_BAN_KV.delete(`sb:${accountId}`);

  // Append to an immutable audit trail (separate table or R2 object).
  await env.DB
    .prepare(
      `INSERT INTO shadow_ban_audit_log
         (account_id, action, actor, ts)
       VALUES (?, 'LIFT', ?, ?)`
    )
    .bind(accountId, liftedBy, Date.now())
    .run();
}
```

---

## Anti-patterns

- **Adding `is_shadow_banned` to the accounts table** — schema coupling causes DDL locks and leaks the flag through naive `SELECT *` queries in client-facing endpoints.
- **Returning HTTP 200 with an empty array** instead of the normal feed shape — timing differences and response size anomalies can be fingerprinted by sophisticated actors.
- **Long KV TTLs (> 5 min)** — a lifted emergency ban continues suppressing legitimate content for too long.
- **Filtering only on post creation** — posts inserted before a ban was applied survive in search indexes; filter at read time, not write time.
- **Logging ban checks** — any log line that includes `shadow_ban=true` alongside the account ID can leak information if logs are discoverable through legal proceedings or breaches.

---

## Gotchas

- D1 `RETURNING` clause requires SQLite 3.35+. Cloudflare D1 supports this as of 2024 — verify with `SELECT sqlite_version()`.
- KV `expirationTtl` is a floor, not a ceiling. KV may serve stale data up to a few seconds beyond TTL due to eventual consistency across edges.
- The sweep Worker deletes by `expires_at <= now`. If the Worker is delayed (e.g., by a Cron trigger backlog), bans lapse late. This is acceptable; schedule the cron hourly and keep TTLs coarse.
- `ON CONFLICT DO UPDATE` in D1 resets all fields on reapplication — ensure moderators confirm before re-banning at a stricter visibility level.

---

## Verification

```bash
# 1. Apply a short-lived test ban
curl -X POST https://api.example.com/internal/moderation/shadow-ban \
  -H "Authorization: Bearer $MOD_TOKEN" \
  -d '{"accountId":"test-acct-001","reasonCode":"SPAM","ttlSeconds":300}'

# 2. Post content as test-acct-001, then query feed as another account
# Feed should exclude the post for others.

# 3. Confirm the banned account sees its own post.

# 4. Wait for TTL or call lift endpoint; verify post reappears in feed.

# 5. Inspect audit log
curl https://api.example.com/internal/moderation/shadow-ban/test-acct-001/audit \
  -H "Authorization: Bearer $MOD_TOKEN"
```

---

## Related

- `repeat-offender-detection-anonymous-sessions.md`
- `platform-manipulation-brigading-detection.md`
- `botnet-registration-detection-turnstile-fingerprinting.md`
- `coordinated-inauthentic-behavior-detection-d1.md`
- `account-suspension-appeals-worker-workflow.md`

---

## Sources

- Cloudflare D1 documentation — https://developers.cloudflare.com/d1/
- Cloudflare Workers KV — https://developers.cloudflare.com/kv/
- Reddit Engineering: Ghost Mode — internal trust-and-safety blog posts (2021)
- Twitter / X transparency reports, shadow-quality-filter disclosures
- DSA Article 17 (transparency of content moderation decisions) — https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:32022R2065
