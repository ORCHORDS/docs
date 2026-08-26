# soft-delete-pattern-detail

**Issue:** Soft delete with restore, audit, and retention
**Date:** 2026-08-09
**Status:** documented

## Symptom
A user clicks "Delete my account." You DELETE the row. A
week later, the user says "Wait, I want my account back."
The data is gone. The team scrambles to restore from
backups. You learn the hard way that hard deletes are
risky.

## Root cause
**Hard deletes are irreversible.** Once a row is deleted,
you can't recover it. The user can't un-delete. Compliance
forensics can't audit. The data is just gone.

**Source:** GDPR Article 17 (Right to erasure):
https://gdpr-info.eu/art-17-gdpr/

## The "soft delete" pattern

Instead of `DELETE`, set a `deleted_at` timestamp:
```sql
-- Schema
ALTER TABLE users ADD COLUMN deleted_at TEXT;  -- ISO 8601 or NULL

-- "Delete"
UPDATE users SET deleted_at = ? WHERE id = ? AND tenant_id = ?;
-- Instead of:
-- DELETE FROM users WHERE id = ? AND tenant_id = ?;
```

```ts
async function softDeleteUser(id: string, ctx: McContext): Promise<void> {
  await ctx.env.DB!.prepare(
    `UPDATE users SET deleted_at = ? WHERE id = ? AND tenant_id = ?`
  ).bind(new Date().toISOString(), id, ctx.tenant.id).run();

  // Audit log
  await writeAudit(ctx.env, {
    userId: ctx.user.id,
    tenantId: ctx.tenant.id,
    action: 'user.deleted',
    resourceType: 'user',
    resourceId: id,
  });
}
```

The row stays; the `deleted_at` is set.

## The "filtering soft-deleted rows" pattern

By default, queries should exclude soft-deleted rows:
```ts
async function getUser(id: string, ctx: McContext): Promise<User | null> {
  return ctx.env.DB!.prepare(
    `SELECT * FROM users WHERE id = ? AND tenant_id = ? AND deleted_at IS NULL`
  ).bind(id, ctx.tenant.id).first<User>();
}
```

For all "active" queries, add `AND deleted_at IS NULL`.

For a repository:
```ts
class UserRepository {
  constructor(private db: D1Database) {}

  async getActiveById(id: string, tenantId: string): Promise<User | null> {
    return this.db.prepare(
      `SELECT * FROM users WHERE id = ? AND tenant_id = ? AND deleted_at IS NULL`
    ).bind(id, tenantId).first<User>();
  }

  async getDeletedById(id: string, tenantId: string): Promise<User | null> {
    return this.db.prepare(
      `SELECT * FROM users WHERE id = ? AND tenant_id = ? AND deleted_at IS NOT NULL`
    ).bind(id, tenantId).first<User>();
  }

  async listDeleted(tenantId: string, limit = 100): Promise<User[]> {
    return this.db.prepare(
      `SELECT * FROM users WHERE tenant_id = ? AND deleted_at IS NOT NULL ORDER BY deleted_at DESC LIMIT ?`
    ).bind(tenantId, limit).all<User[]>().then(r => r.results);
  }
}
```

## The "restore" pattern

```ts
async function restoreUser(id: string, ctx: McContext): Promise<User> {
  const user = await ctx.env.DB!.prepare(
    `UPDATE users SET deleted_at = NULL WHERE id = ? AND tenant_id = ? AND deleted_at IS NOT NULL RETURNING *`
  ).bind(id, ctx.tenant.id).first<User>();

  if (!user) {
    throw new Error('User not found or not deleted');
  }

  // Audit log
  await writeAudit(ctx.env, {
    userId: ctx.user.id,
    tenantId: ctx.tenant.id,
    action: 'user.restored',
    resourceType: 'user',
    resourceId: id,
  });

  return user;
}
```

## The "GDPR Article 17" consideration

GDPR says: "The data subject shall have the right to obtain
from the controller the erasure of personal data concerning
him or her without undue delay."

A soft delete may not satisfy this. The user wants the data
GONE, not just hidden. Options:

1. **Soft delete + hard delete after retention period:**
   - Day 0: user clicks delete → soft delete
   - Day 30: hard delete (data is gone for real)
   - Day 1-30: user can restore

2. **Hard delete immediately:**
   - User clicks delete → row is gone
   - Audit log records the deletion (without PII)
   - User can't restore

3. **Soft delete forever:**
   - User clicks delete → soft delete
   - Data is never hard deleted
   - User can restore
   - Risk: violates GDPR if user says "delete my data"

For GDPR compliance, option 1 is common. For non-GDPR apps,
option 3 (soft delete forever) is also valid.

## The "retention period" pattern

For a configurable retention:
```ts
async function purgeOldSoftDeletes(env: Env, retentionDays = 30): Promise<number> {
  const cutoff = new Date(Date.now() - retentionDays * 24 * 60 * 60 * 1000).toISOString();

  // Audit log entries first (we need to keep the audit log)
  const toDelete = await env.DB!.prepare(
    `SELECT id FROM users WHERE deleted_at < ?`
  ).bind(cutoff).all<{ id: string }>();

  // For each user, write a final audit log entry
  for (const row of toDelete.results) {
    await writeAudit(env, {
      action: 'user.purged',
      resourceType: 'user',
      resourceId: row.id,
      reason: `Soft-deleted for > ${retentionDays} days`,
    });
  }

  // Then hard delete
  const result = await env.DB!.prepare(
    `DELETE FROM users WHERE deleted_at < ?`
  ).bind(cutoff).run();

  return result.meta.changes ?? 0;
}
```

Run this from a cron:
```ts
// Cron: daily at 3am
export async function handleScheduled(event: ScheduledEvent, env: Env, ctx: ExecutionContext): Promise<void> {
  const purged = await purgeOldSoftDeletes(env, 30);
  logEvent('users.purged', 'info', { count: purged });
}
```

## The "soft delete + unique constraint" problem

If email is unique, and user A is soft-deleted, user B can't
sign up with the same email:
```ts
// User A signs up with alice@x.test
// User A deletes (soft delete)
// User B signs up with alice@x.test
// UNIQUE constraint violation: alice@x.test already exists
```

**Solutions:**

1. **Use a partial unique index:**
```sql
CREATE UNIQUE INDEX idx_users_email_active ON users(email) WHERE deleted_at IS NULL;
```

2. **Rename the email on delete:**
```ts
// On soft delete
UPDATE users SET email = 'deleted-' || id || '@deleted.local' WHERE id = ?;
```

3. **Use a UUID for the row, keep email as data:**
```sql
-- The unique constraint is on `id`, not `email`
-- The email can be duplicated across deleted/active users
```

For D1 (SQLite), partial indexes are supported. Use option 1.

## The "soft delete in indexes" pattern

If a query filters by `deleted_at IS NULL`, the index
should include it:
```sql
CREATE INDEX idx_users_tenant_active ON users(tenant_id, deleted_at);
```

This way, the index "active rows per tenant" is fast.

## The "soft delete vs GDPR Article 17" decision

| Soft delete | Hard delete |
|---|---|
| User can restore | User can't restore |
| Data is in the DB | Data is gone |
| GDPR risk if user says "delete" | GDPR safe |
| Forensic value | No forensic value |

For most apps, **soft delete with a retention period** is
the right answer:
- 0-30 days: soft delete (restorable)
- 30+ days: hard delete (GDPR compliant)

## Verification
- **Test:** `test/soft-delete.test.ts > soft delete sets
  deleted_at, queries exclude deleted` — passes
- **Test:** `test/soft-delete.test.ts > restore clears
  deleted_at` — passes
- **Live:** Soft-deleted rows are purged after retention
- **Audit:** Annual review of retention policy

## Gotchas
- **The "soft delete" leaks into every query.** Every SELECT
  must add `AND deleted_at IS NULL`. Use a repository
  pattern to centralize this.
- **The "restore" is not always possible.** If a unique
  constraint is violated (the email is now taken), the
  restore fails. Handle this.
- **The "audit log" must capture the soft delete.** Without
  it, the audit trail is broken.
- **The "hard delete after retention" must be in a cron.**
  Forgetting to set up the cron is a GDPR violation.
- **The "soft delete" can confuse metrics.** A "users
  count" that includes soft-deleted is wrong. Use a
  separate "active users" metric.

## Related
- `multi-tenant-data-isolation.md`
- `audit-log-as-product.md`
- `gdpr-article-17-erasure.md`
- `soft-delete-pattern.md` (the pattern entry)
- `database-migration-strategy.md`
- GDPR: https://gdpr-info.eu/art-17-gdpr/
