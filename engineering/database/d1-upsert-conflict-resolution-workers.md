# D1 UPSERT and ON CONFLICT Resolution Patterns in Workers

- **Date:** 2026-08-23
- **Author:** example.com
- **Status:** production

## Symptom / Use-case

You need to insert-or-update rows in D1 from a Cloudflare Worker — for example, syncing external webhook events, upserting user preferences, or merging idempotent API writes — without issuing a SELECT first. A naive INSERT fails with UNIQUE constraint violation on duplicate keys, and a SELECT-then-INSERT-or-UPDATE pattern requires two round trips to D1 with no atomicity guarantee.

## Context

SQLite's `INSERT OR REPLACE` and the ANSI-compliant `INSERT ... ON CONFLICT ... DO UPDATE SET` (available since SQLite 3.24, present in D1) both solve this atomically in one statement. The two forms differ in behaviour: `REPLACE` deletes the conflicting row and inserts a new one (triggers `DELETE` + `INSERT`, resets any unset columns, and changes the `rowid`); `ON CONFLICT DO UPDATE` updates only the named columns in-place, preserving `rowid` and firing `UPDATE` triggers. For most Workers use-cases the `DO UPDATE` form is safer because it preserves foreign key children that reference the row's `rowid`.

## Basic UPSERT with DO UPDATE

```typescript
// src/upsert.ts
import type { D1Database } from '@cloudflare/workers-types';

interface Env {
  DB: D1Database;
}

interface UserPreference {
  userId: string;
  key: string;
  value: string;
  updatedAt: string;
}

// Single-row upsert: update only if the incoming value differs
export async function upsertPreference(
  env: Env,
  pref: UserPreference
): Promise<void> {
  await env.DB.prepare(
    `INSERT INTO user_preferences (user_id, key, value, updated_at)
     VALUES (?1, ?2, ?3, ?4)
     ON CONFLICT (user_id, key) DO UPDATE SET
       value      = excluded.value,
       updated_at = excluded.updated_at
     WHERE excluded.value IS NOT user_preferences.value`
    // WHERE clause: skip the write if value hasn't changed (reduces WAL churn)
  )
    .bind(pref.userId, pref.key, pref.value, pref.updatedAt)
    .run();
}

// Return the final row after upsert using RETURNING
export async function upsertPreferenceReturning(
  env: Env,
  pref: UserPreference
): Promise<UserPreference> {
  const row = await env.DB.prepare(
    `INSERT INTO user_preferences (user_id, key, value, updated_at)
     VALUES (?1, ?2, ?3, ?4)
     ON CONFLICT (user_id, key) DO UPDATE SET
       value      = excluded.value,
       updated_at = excluded.updated_at
     RETURNING user_id, key, value, updated_at`
  )
    .bind(pref.userId, pref.key, pref.value, pref.updatedAt)
    .first<UserPreference>();

  if (!row) throw new Error('Upsert returned no row');
  return row;
}
```

## Batch UPSERT via D1 Batch API

```typescript
// src/batch-upsert.ts
// D1's batch() sends multiple statements in one HTTP round trip.
// Use it to upsert many rows atomically (all succeed or all fail).

interface WebhookEvent {
  eventId: string;
  source: string;
  payload: string;
  receivedAt: string;
}

export async function batchUpsertEvents(
  env: Env,
  events: WebhookEvent[]
): Promise<void> {
  if (events.length === 0) return;

  // D1 batch limit is 100 statements; chunk if necessary
  const CHUNK = 100;
  for (let i = 0; i < events.length; i += CHUNK) {
    const chunk = events.slice(i, i + CHUNK);

    const statements = chunk.map(ev =>
      env.DB.prepare(
        `INSERT INTO webhook_events (event_id, source, payload, received_at)
         VALUES (?1, ?2, ?3, ?4)
         ON CONFLICT (event_id) DO UPDATE SET
           payload     = excluded.payload,
           received_at = excluded.received_at`
      ).bind(ev.eventId, ev.source, ev.payload, ev.receivedAt)
    );

    await env.DB.batch(statements);
  }
}
```

## Conflict-Target Variants and Partial Indexes

```typescript
// src/inventory.ts
// When a table has multiple unique constraints, name the specific conflict target.

export async function reserveStock(
  env: Env,
  warehouseId: number,
  sku: string,
  delta: number      // positive = restock, negative = reserve
): Promise<{ available: number }> {
  // ON CONFLICT (warehouse_id, sku) targets the composite unique index
  const row = await env.DB.prepare(
    `INSERT INTO inventory (warehouse_id, sku, available, last_updated)
     VALUES (?1, ?2, ?3, datetime('now'))
     ON CONFLICT (warehouse_id, sku) DO UPDATE SET
       available    = inventory.available + excluded.available,
       last_updated = excluded.last_updated
     RETURNING available`
  )
    .bind(warehouseId, sku, delta)
    .first<{ available: number }>();

  if (!row) throw new Error('Inventory upsert failed');
  if (row.available < 0) {
    // Roll back by throwing; D1 auto-wraps batch in a transaction
    throw new Error(`Insufficient stock for SKU ${sku}: available=${row.available}`);
  }

  return row;
}

// DO NOTHING variant: idempotent insert, skip if already exists
export async function insertEventOnce(
  env: Env,
  eventId: string,
  data: string
): Promise<boolean> {
  const result = await env.DB.prepare(
    `INSERT INTO processed_events (event_id, data, processed_at)
     VALUES (?1, ?2, datetime('now'))
     ON CONFLICT (event_id) DO NOTHING`
  )
    .bind(eventId, data)
    .run();

  // meta.changes === 0 means row already existed (conflict, nothing done)
  return (result.meta.changes ?? 0) > 0;
}
```

## Multi-Column Merge with Partial Update Logic

```typescript
// src/profile-sync.ts
// Only overwrite non-null incoming fields; preserve existing data for nulls.

interface ProfileUpdate {
  userId: string;
  email: string | null;
  displayName: string | null;
  avatarUrl: string | null;
  syncedAt: string;
}

export async function mergeProfile(
  env: Env,
  update: ProfileUpdate
): Promise<void> {
  await env.DB.prepare(
    `INSERT INTO user_profiles (user_id, email, display_name, avatar_url, synced_at)
     VALUES (?1, ?2, ?3, ?4, ?5)
     ON CONFLICT (user_id) DO UPDATE SET
       -- COALESCE: keep existing value if incoming is NULL
       email        = COALESCE(excluded.email,        user_profiles.email),
       display_name = COALESCE(excluded.display_name, user_profiles.display_name),
       avatar_url   = COALESCE(excluded.avatar_url,   user_profiles.avatar_url),
       synced_at    = excluded.synced_at`
  )
    .bind(
      update.userId,
      update.email,
      update.displayName,
      update.avatarUrl,
      update.syncedAt
    )
    .run();
}
```

## Anti-patterns

- Using `INSERT OR REPLACE` when the row has foreign-key children — `REPLACE` deletes and re-inserts, orphaning child rows and changing `rowid`, even when foreign keys are enabled.
- Issuing a SELECT to check existence before INSERT — two round trips with a TOCTOU race; `ON CONFLICT` handles this atomically.
- Omitting the conflict target column list — without an explicit target D1 falls back to `ON CONFLICT DO NOTHING` semantics on any unique violation, masking unintended conflicts on other indexes.

## Gotchas

- `excluded` is the special alias for the row that was rejected by the conflict; you can reference both `excluded.column` (incoming) and `table_name.column` (existing) in the SET clause.
- `meta.changes` is `1` for an insert and `1` for an update (the row was changed), but `0` for a `DO NOTHING` skip — use it to distinguish insert vs. skip, not insert vs. update; use `RETURNING` to distinguish insert vs. update.
- D1's per-request write quota applies per statement, not per batch; a 100-statement batch still counts as 100 write units toward your plan limits.

## Verification

```bash
# Confirm RETURNING works on your D1 version
wrangler d1 execute MY_DB --remote \
  --command "INSERT INTO user_preferences (user_id, key, value, updated_at)
             VALUES ('u1','theme','dark','2026-08-23')
             ON CONFLICT (user_id, key) DO UPDATE SET value = excluded.value
             RETURNING *;"

# Check meta.changes on DO NOTHING
wrangler d1 execute MY_DB --remote \
  --command "INSERT INTO processed_events (event_id, data, processed_at)
             VALUES ('evt-1','{}',datetime('now'))
             ON CONFLICT (event_id) DO NOTHING;"

# Verify no orphaned foreign-key rows after using REPLACE (dangerous demo)
wrangler d1 execute MY_DB --remote \
  --command "PRAGMA foreign_key_check;"
```

## Related

- `database/upsert-on-conflict.md`
- `database/d1-foreign-keys-referential-integrity.md`
- `database/d1-batch-operations-performance.md`
- `database/idempotency-keys-database.md`
- `database/d1-audit-event-log.md`

## Sources

- https://www.sqlite.org/lang_upsert.html
- https://developers.cloudflare.com/d1/sql-api/sql-statements/
- https://developers.cloudflare.com/d1/worker-api/d1-database/#batch
