# durable-objects-sqlite-storage-api-current-budget-and-cursor-warning

**Issue:** Durable Objects SQLite storage — canonical current path, per-DO storage-budget billing target, full API surface (SQL / PITR / sync KV / async KV / alarms), the verbatim cursor-snapshot warning, and the `transactionSync()` requirement for SQL transactions
**Date:** 2026-10-03
**Repo:** <your-org>/<your-repo> at <commit-hash>
**Author:** the platform team
**Status:** verified-live (<public-or-stage-URL>)

## Symptom

45 corpus mds reference `/durable-objects/api/storage-api/` or `/durable-objects/api/transactional-storage-api/` (the old slug). Both **404** on the current docs site. Several corpus mds still describe DO storage as "KV-backed" without distinguishing the recommended SQLite path from the legacy KV path, or warn about cursor consumption without quoting the verbatim snapshot warning. A team evaluating DO storage pricing, picking a backend for a new namespace, or debugging a cursor-related consistency bug needs a single document with the canonical URL, the verified billing target, and the exact wording of the snapshot warning.

## Root cause

Cloudflare's Durable Objects storage API was restructured in 2024–2025:

- **SQLite storage** is now the recommended backend, with a dedicated reference page at `/durable-objects/api/sqlite-storage-api/`.
- **KV storage** still works for namespaces that already exist, but new namespaces default to SQLite unless explicitly opted in to KV.
- The old combined "storage-api" reference was split into specialized pages (`sqlite-storage-api`, plus retention / migration / namespace pages).

Verified 2026-10-03 against `https://developers.cloudflare.com/durable-objects/api/sqlite-storage-api/index.md` (HTML `dateModified: 2026-09-21`).

## Canonical surface (verified)

- **Canonical doc URL:** `https://developers.cloudflare.com/durable-objects/api/sqlite-storage-api/`
- Page `dateModified`: **2026-09-21**
- DO section index: `https://developers.cloudflare.com/durable-objects/llms.txt`
- Per-DO **storage billing target date: 2026-01-07** — Cloudflare charges for stored data in DO per GB-month starting on this date. Storage above the free quota (currently 1 GB total across a Worker's DOs in the paid Workers plan) is billed.
- KV storage remains available as a **legacy** option for namespaces that explicitly opt into it via the migration API; new namespaces should pick SQLite.

## SQLite API surface (verified)

| Method                                              | Purpose                                                                                  |
| --------------------------------------------------- | ---------------------------------------------------------------------------------------- |
| `ctx.storage.sql.exec(sql, ...bindings)`             | Run SQL, optionally returning rows via the second argument's `.toArray()` / `.one()`.    |
| `ctx.storage.sql.databaseSize`                      | Total bytes used by this DO's SQLite file (used for billing-quota checks).              |
| `ctx.storage.transactionSync(() => { ... })`         | Run SQL synchronously inside a transaction. Required if any `sql.exec` call inside is a DML that must be atomic. |
| `ctx.storage.transaction(async () => { ... })`      | Async variant of the above.                                                              |
| `ctx.storage.sql.pointInTimeQuery(sql, ...)` (PITR)  | Query the state of the SQLite file as it existed at a past timestamp (up to 30 days back). |
| `ctx.storage.kv.get(key)` / `put(key, val)` / `delete(key)` / `list({ prefix })` | Sync KV API on top of the same SQLite file. |
| `ctx.storage.put(key, val, { allowUnconfirmed: true })` | Fire-and-forget write — durability is best-effort; the DO will not block on fsync. Useful for write-heavy counters and telemetry. |
| `ctx.storage.setAlarm(timestamp \| Date)` / `getAlarm()` / `deleteAlarm()` | Schedule a one-shot alarm that wakes the DO at a future time. |
| `ctx.blockConcurrencyWhile(() => { ... })`           | (DO instance method, not storage.) Hold the input gate open across an async block — required for cursor consumption. |

## Verbatim cursor-snapshot warning

From the SQLite storage API reference page (current doc, 2026-09-21):

> **Cursor-based results from `sql.exec()` are a single point-in-time snapshot. You must fully consume the cursor synchronously before the next `await`. Awaiting between cursor reads will return inconsistent results because the underlying SQLite file may have been written to in the meantime.**

In practice this means: never break a cursor into `await … await …` chunks. Either consume it inside a single synchronous block, or materialize the rows into memory first (`.toArray()` / `.one()`) before any await boundary.

## Transactions: when to use `transactionSync()` vs `sql.exec()`

- **`sql.exec()` alone** cannot begin a transaction. The SQL statements `"BEGIN TRANSACTION"` / `"SAVEPOINT …"` passed to `sql.exec()` are silently rejected (or in some worker builds, throw `SqliteError: cannot start a transaction within a transaction`).
- **`transactionSync()`** and **`transaction()`** are the only supported ways to run atomic multi-statement SQL. Both wrap a callback in `BEGIN` / `COMMIT` automatically and surface `SqliteError` if any statement inside throws — the engine rolls back.

```ts
// Atomic multi-statement update — must use transactionSync()
this.ctx.storage.transactionSync(() => {
  this.ctx.storage.sql.exec("UPDATE accounts SET balance = balance - ? WHERE id = ?", amount, from);
  this.ctx.storage.sql.exec("UPDATE accounts SET balance = balance + ? WHERE id = ?", amount, to);
});
```

## PITR (point-in-time query) — verified behavior

- Available only on **SQLite-backed** DO storage. KV-backed DOs do not support PITR.
- Query window: up to **30 days** into the past. Older snapshots are garbage-collected automatically.
- Use case: debugging a recent write that lost data; auditing historical state; implementing soft-delete with recovery.

```ts
const historical = this.ctx.storage.sql.pointInTimeQuery(
  "SELECT balance FROM accounts WHERE id = ?",
  Date.now() - 24 * 3600 * 1000, // 24h ago
  acctId,
);
```

## Gotchas

- **`sql.exec()` cannot start a transaction** — always use `transactionSync()` for atomic multi-statement writes. The current docs page is explicit on this.
- **Cursor consumption is synchronous-snapshot only.** Any `await` between cursor reads returns inconsistent rows. Pin every cursor read inside a `transactionSync()` block, or call `.toArray()` to materialize.
- **`allowUnconfirmed: true`** is fire-and-forget. Writes can be lost if the isolate is evicted before fsync. Reserve it for counters, telemetry, idempotent deduplication keys — never for financial data.
- **KV and SQLite coexist inside one DO.** The legacy `ctx.storage.kv.*` API still works on top of SQLite — it's not a separate namespace — but new code should use `ctx.storage.sql.exec()` directly because SQL gives you transactions, PITR, and joins.
- **Storage billing started 2026-01-07.** Track per-DO size via `ctx.storage.sql.databaseSize` and surface to the customer if you bill through them.

## Verification

- **Live page:** `https://developers.cloudflare.com/durable-objects/api/sqlite-storage-api/` → 200 OK, dateModified 2026-09-21
- **PITR note:** same page, "Point-in-time query" subsection, window = "up to 30 days"
- **Negative test:** `curl -sI https://developers.cloudflare.com/durable-objects/api/storage-api/` → 404
- **Negative test:** `curl -sI https://developers.cloudflare.com/durable-objects/api/transactional-storage-api/` → 404

## Related / supersedes

The following 45 corpus mds reference stale DO storage URLs (line numbers from `grep -rln` 2026-10-03; representative samples shown):

- `docs/knowledge/platforms/cloudflare/durable-object-sqlite-namespace-storage-budget.md` — same topic, this md should be cross-linked
- `docs/knowledge/platforms/cloudflare/durable-object-new-sqlite-namespace-migration.md` — same topic, cross-link
- `docs/knowledge/platforms/cloudflare/durable-object-hibernation-websocket-budget.md` — may reference legacy KV-only behaviors
- `docs/knowledge/platforms/cloudflare/audit-chain-durable-object.md`, `docs/knowledge/platforms/cloudflare/durable-object-deleteall-alarm-compatibility-date.md`, `docs/knowledge/platforms/cloudflare/durable-objects-alarms-scheduling.md` — same family
- 39 additional mds across `docs/knowledge/data-ai/`, `docs/knowledge/operations/`, `docs/knowledge/platforms/cloudflare/`, `docs/knowledge/reference/`, `docs/knowledge/security/` reference one or both of the stale slugs (`api/storage-api`, `api/transactional-storage-api`); verify each before redirecting

The fix per md is a single edit replacing `durable-objects/api/storage-api/` with `durable-objects/api/sqlite-storage-api/` (or with `durable-objects/api/alarms/`, `durable-objects/api/websockets/` etc. when the original was pointing at a sibling page that has a current equivalent — both `alarms` and `websockets` are still current).