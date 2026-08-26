# D1 Audit Trail: Append-Only Event Log for User Actions

- **Date:** 2026-08-22
- **Author:** example.com
- **Status:** production

---

## Symptom / Use-Case

Compliance teams ask: "Who changed this record and when?" Security teams ask: "Which user
accessed this data before the breach?" Product teams ask: "Can we show users their activity
history?" All three questions require an immutable, append-only audit log that records every
meaningful action — create, update, delete, login, export — with enough context to replay
the history of any object or investigate any actor.

---

## Context

D1 (SQLite at the edge) is an excellent fit for append-only event logs because:

- SQLite inserts are fast; audit records are pure inserts with no contention.
- The D1 REST API and Cloudflare Workers make it trivial to write audit events from any
  edge function without network overhead.
- SQLite's JSON support (`json_extract`, `json_each`) allows the event `payload` column to
  carry structured before/after data without requiring a fixed schema per event type.

The key design constraint: **audit rows must never be updated or deleted** by application
code. The table is write-once (INSERT only). Purging for retention compliance is the only
exception and requires an explicit, privileged operation.

---

## 1. Schema

```sql
-- migrations/0003_audit_events.sql
CREATE TABLE audit_events (
  id           TEXT    PRIMARY KEY,
  tenant_id    TEXT    NOT NULL,
  actor_id     TEXT    NOT NULL,         -- user who performed the action
  actor_type   TEXT    NOT NULL,         -- 'user' | 'system' | 'api_key'
  action       TEXT    NOT NULL,         -- verb: 'project.created', 'task.deleted', …
  resource_type TEXT   NOT NULL,         -- 'project' | 'task' | 'user' | …
  resource_id   TEXT   NOT NULL,         -- ID of the affected object
  payload      TEXT,                     -- JSON: before/after state or extra context
  ip_address   TEXT,
  user_agent   TEXT,
  created_at   INTEGER NOT NULL DEFAULT (unixepoch())
);

-- Query patterns: by tenant timeline, by resource, by actor
CREATE INDEX idx_audit_tenant_time    ON audit_events(tenant_id, created_at DESC);
CREATE INDEX idx_audit_resource       ON audit_events(tenant_id, resource_type, resource_id, created_at DESC);
CREATE INDEX idx_audit_actor          ON audit_events(tenant_id, actor_id, created_at DESC);
CREATE INDEX idx_audit_action         ON audit_events(tenant_id, action, created_at DESC);
```

The `payload` column is stored as JSON text and queried with `json_extract()`. This avoids
schema churn when individual event types need different fields.

---

## 2. Event Types and Payload Conventions

Define a typed event catalogue so the payload shape is predictable for each action.

```typescript
// src/lib/audit-types.ts

export type ActorType = 'user' | 'system' | 'api_key';

export interface AuditActor {
  id: string;
  type: ActorType;
  ip?: string;
  userAgent?: string;
}

// Discriminated union of all possible audit events
export type AuditEventPayload =
  | { action: 'project.created'; after: Record<string, unknown> }
  | { action: 'project.updated'; before: Record<string, unknown>; after: Record<string, unknown> }
  | { action: 'project.deleted'; before: Record<string, unknown> }
  | { action: 'project.restored'; after: Record<string, unknown> }
  | { action: 'task.created'; after: Record<string, unknown> }
  | { action: 'task.updated'; before: Record<string, unknown>; after: Record<string, unknown> }
  | { action: 'task.deleted'; before: Record<string, unknown> }
  | { action: 'member.invited'; email: string; role: string }
  | { action: 'member.removed'; userId: string }
  | { action: 'user.login'; method: string }
  | { action: 'user.logout' }
  | { action: 'export.triggered'; format: string; resourceType: string };

export interface AuditEventInput {
  tenantId: string;
  actor: AuditActor;
  resourceType: string;
  resourceId: string;
  payload: AuditEventPayload;
}
```

---

## 3. Audit Logger Service

```typescript
// src/lib/audit-logger.ts
import { AuditEventInput } from './audit-types';

export class AuditLogger {
  constructor(private db: D1Database) {}

  async log(event: AuditEventInput): Promise<void> {
    const id = crypto.randomUUID();
    const now = Math.floor(Date.now() / 1000);

    await this.db
      .prepare(
        `INSERT INTO audit_events
           (id, tenant_id, actor_id, actor_type, action, resource_type,
            resource_id, payload, ip_address, user_agent, created_at)
         VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`
      )
      .bind(
        id,
        event.tenantId,
        event.actor.id,
        event.actor.type,
        event.payload.action,
        event.resourceType,
        event.resourceId,
        JSON.stringify(event.payload),
        event.actor.ip ?? null,
        event.actor.userAgent ?? null,
        now
      )
      .run();
  }

  /**
   * Batch log multiple events atomically (e.g., cascade deletes).
   * Uses D1 batch() so all events share one HTTP round-trip.
   */
  async logBatch(events: AuditEventInput[]): Promise<void> {
    if (events.length === 0) return;
    const now = Math.floor(Date.now() / 1000);

    const statements = events.map((event) =>
      this.db
        .prepare(
          `INSERT INTO audit_events
             (id, tenant_id, actor_id, actor_type, action, resource_type,
              resource_id, payload, ip_address, user_agent, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`
        )
        .bind(
          crypto.randomUUID(),
          event.tenantId,
          event.actor.id,
          event.actor.type,
          event.payload.action,
          event.resourceType,
          event.resourceId,
          JSON.stringify(event.payload),
          event.actor.ip ?? null,
          event.actor.userAgent ?? null,
          now
        )
    );

    await this.db.batch(statements);
  }
}
```

---

## 4. Integration with Repository Operations

Wrap the data mutation and the audit log write in a single `db.batch()` call so both
either succeed together or fail together (D1 batch is atomic).

```typescript
// src/repositories/project-repository.ts (audit-aware version)
import { AuditLogger } from '../lib/audit-logger';
import { AuditActor } from '../lib/audit-types';

export class AuditedProjectRepository {
  private audit: AuditLogger;

  constructor(
    private db: D1Database,
    private tenantId: string,
    private actor: AuditActor
  ) {
    this.audit = new AuditLogger(db);
  }

  async create(name: string): Promise<Project> {
    const id = crypto.randomUUID();
    const now = Math.floor(Date.now() / 1000);
    const project: Project = {
      id, tenant_id: this.tenantId, name,
      status: 'active', created_at: now, updated_at: now, deleted_at: null,
    };

    // Atomic: data insert + audit event
    await this.db.batch([
      this.db.prepare(
        `INSERT INTO projects (id,tenant_id,name,status,created_at,updated_at,deleted_at)
         VALUES (?,?,?,'active',?,?,NULL)`
      ).bind(id, this.tenantId, name, now, now),

      this.db.prepare(
        `INSERT INTO audit_events
           (id,tenant_id,actor_id,actor_type,action,resource_type,resource_id,payload,ip_address,user_agent,created_at)
         VALUES (?,?,?,?,'project.created','project',?,?,?,?,?)`
      ).bind(
        crypto.randomUUID(), this.tenantId,
        this.actor.id, this.actor.type,
        id, JSON.stringify({ action: 'project.created', after: project }),
        this.actor.ip ?? null, this.actor.userAgent ?? null, now
      ),
    ]);

    return project;
  }

  async delete(projectId: string): Promise<void> {
    // Fetch before-state for the audit payload
    const before = await this.db
      .prepare(`SELECT * FROM projects WHERE tenant_id=? AND id=?`)
      .bind(this.tenantId, projectId)
      .first<Project>();

    if (!before) throw new Error('Project not found');

    const now = Math.floor(Date.now() / 1000);

    await this.db.batch([
      this.db.prepare(
        `UPDATE projects SET deleted_at=? WHERE tenant_id=? AND id=? AND deleted_at IS NULL`
      ).bind(now, this.tenantId, projectId),

      this.db.prepare(
        `INSERT INTO audit_events
           (id,tenant_id,actor_id,actor_type,action,resource_type,resource_id,payload,ip_address,user_agent,created_at)
         VALUES (?,?,?,?,'project.deleted','project',?,?,?,?,?)`
      ).bind(
        crypto.randomUUID(), this.tenantId,
        this.actor.id, this.actor.type,
        projectId, JSON.stringify({ action: 'project.deleted', before }),
        this.actor.ip ?? null, this.actor.userAgent ?? null, now
      ),
    ]);
  }
}
```

---

## 5. Querying the Audit Log

```typescript
// src/repositories/audit-repository.ts
export interface AuditEvent {
  id: string;
  tenant_id: string;
  actor_id: string;
  actor_type: string;
  action: string;
  resource_type: string;
  resource_id: string;
  payload: string; // JSON string — parse in application layer
  ip_address: string | null;
  user_agent: string | null;
  created_at: number;
}

export class AuditRepository {
  constructor(
    private db: D1Database,
    private tenantId: string
  ) {}

  /** Full activity feed for a tenant, cursor-paginated */
  async tenantFeed(cursor?: number, limit = 50): Promise<AuditEvent[]> {
    const { results } = await this.db
      .prepare(
        `SELECT * FROM audit_events
         WHERE tenant_id = ?
           ${cursor ? 'AND created_at < ?' : ''}
         ORDER BY created_at DESC
         LIMIT ?`
      )
      .bind(...(cursor ? [this.tenantId, cursor, limit] : [this.tenantId, limit]))
      .all<AuditEvent>();
    return results;
  }

  /** History for a specific resource (e.g., one project) */
  async resourceHistory(resourceType: string, resourceId: string): Promise<AuditEvent[]> {
    const { results } = await this.db
      .prepare(
        `SELECT * FROM audit_events
         WHERE tenant_id = ?
           AND resource_type = ?
           AND resource_id = ?
         ORDER BY created_at ASC`
      )
      .bind(this.tenantId, resourceType, resourceId)
      .all<AuditEvent>();
    return results;
  }

  /** All actions by a specific actor */
  async actorHistory(actorId: string, limit = 100): Promise<AuditEvent[]> {
    const { results } = await this.db
      .prepare(
        `SELECT * FROM audit_events
         WHERE tenant_id = ? AND actor_id = ?
         ORDER BY created_at DESC
         LIMIT ?`
      )
      .bind(this.tenantId, actorId, limit)
      .all<AuditEvent>();
    return results;
  }

  /** Query payload JSON fields — e.g., find events where the project name changed */
  async findByPayloadField(
    action: string,
    jsonPath: string,
    value: string
  ): Promise<AuditEvent[]> {
    const { results } = await this.db
      .prepare(
        `SELECT * FROM audit_events
         WHERE tenant_id = ?
           AND action = ?
           AND json_extract(payload, ?) = ?
         ORDER BY created_at DESC
         LIMIT 100`
      )
      .bind(this.tenantId, action, jsonPath, value)
      .all<AuditEvent>();
    return results;
  }
}
```

---

## 6. Retention Purge (Compliance)

```typescript
// src/scheduled/audit-purge.ts
export async function purgeOldAuditEvents(
  db: D1Database,
  retentionDays: number
): Promise<number> {
  const cutoff = Math.floor(Date.now() / 1000) - retentionDays * 86_400;
  let total = 0;
  let batch: number;

  // Chunk deletes to avoid long-running statements
  do {
    const result = await db
      .prepare(
        `DELETE FROM audit_events
         WHERE id IN (
           SELECT id FROM audit_events
           WHERE created_at < ?
           LIMIT 1000
         )`
      )
      .bind(cutoff)
      .run();
    batch = result.meta.changes ?? 0;
    total += batch;
  } while (batch === 1000);

  return total;
}
```

```toml
# wrangler.toml
[triggers]
crons = ["0 4 * * 0"]  # Sunday 04:00 UTC — weekly audit purge
```

---

## Anti-Patterns

- **Updating audit rows**: Any `UPDATE` on `audit_events` breaks immutability. Never expose
  an update path — the repository layer should have no `update()` method for this table.
- **Deleting individual audit rows**: Only bulk retention purges (by age) are acceptable.
  Targeted row deletions allow covering tracks.
- **Storing PII in payload without encryption**: If the payload contains email addresses or
  names, ensure the table is covered by your encryption-at-rest policy and that purge/erasure
  is possible for GDPR compliance.
- **Skipping the audit write on errors**: Do not conditionally skip the audit record when
  the main operation fails. If the project delete fails, no audit record should be written
  either — which is why the `db.batch()` atomic pairing in section 4 matters.
- **Writing audit events outside the edge**: Sending audit events to a separate service
  (queue, external API) from within a Worker introduces latency and failure modes. Write
  directly to D1 with `db.batch()` for atomicity.

---

## Gotchas

- **`created_at` collisions**: If two events are inserted in the same second, cursor
  pagination on `created_at` can skip rows. Use `(created_at, id)` as the composite cursor
  for stable pagination:
  ```sql
  WHERE (created_at, id) < (?, ?)
  ORDER BY created_at DESC, id DESC
  ```
- **JSON extraction performance**: `json_extract(payload, '$.after.name')` is not indexed.
  For high-frequency payload field queries, consider a materialized column:
  ```sql
  ALTER TABLE audit_events ADD COLUMN resource_name TEXT
    GENERATED ALWAYS AS (json_extract(payload, '$.after.name')) VIRTUAL;
  CREATE INDEX idx_audit_resource_name ON audit_events(tenant_id, resource_name);
  ```
- **D1 row size limit**: D1 rows are capped at 1 MB. Keep payload JSON compact — avoid
  storing full file blobs; store references (IDs, URLs) instead.
- **Batch size in `logBatch()`**: D1 batch is limited to 100 statements per call. Split
  larger batches across multiple `db.batch()` calls.

---

## Verification

```typescript
// tests/audit-event-log.test.ts
import { env } from 'cloudflare:test';
import { AuditLogger } from '../src/lib/audit-logger';
import { AuditRepository } from '../src/repositories/audit-repository';

describe('audit event log', () => {
  const TENANT = 'tenant-a';
  const ACTOR = { id: 'user-1', type: 'user' as const };
  let logger: AuditLogger;
  let repo: AuditRepository;

  beforeEach(async () => {
    await env.DB.exec(`DELETE FROM audit_events`);
    logger = new AuditLogger(env.DB);
    repo = new AuditRepository(env.DB, TENANT);
  });

  it('logs an event and retrieves it', async () => {
    await logger.log({
      tenantId: TENANT,
      actor: ACTOR,
      resourceType: 'project',
      resourceId: 'proj-1',
      payload: { action: 'project.created', after: { name: 'Test' } },
    });

    const feed = await repo.tenantFeed();
    expect(feed).toHaveLength(1);
    expect(feed[0].action).toBe('project.created');
  });

  it('resource history is ordered ASC', async () => {
    for (const action of ['project.created', 'project.updated', 'project.deleted'] as const) {
      await logger.log({
        tenantId: TENANT,
        actor: ACTOR,
        resourceType: 'project',
        resourceId: 'proj-1',
        payload: action === 'project.updated'
          ? { action, before: {}, after: {} }
          : action === 'project.deleted'
          ? { action, before: {} }
          : { action, after: {} },
      });
    }

    const history = await repo.resourceHistory('project', 'proj-1');
    expect(history.map(e => e.action)).toEqual([
      'project.created',
      'project.updated',
      'project.deleted',
    ]);
  });
});
```

---

## Related

- `database-audit-logging.md` — generic audit logging theory across databases
- `audit-columns-pattern.md` — created_at / updated_at / created_by columns
- `d1-soft-delete-workers-middleware.md` — recording deleted_at alongside audit events
- `d1-row-level-security-tenant-id.md` — tenant scoping for the audit table itself
- `d1-batch-operations-performance.md` — optimizing `db.batch()` usage

---

## Sources

- Cloudflare D1 documentation — https://developers.cloudflare.com/d1/
- SQLite JSON functions — https://www.sqlite.org/json1.html
- OWASP Logging Cheat Sheet — https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html
- GDPR Article 30 (records of processing) — https://gdpr-info.eu/art-30-gdpr/
