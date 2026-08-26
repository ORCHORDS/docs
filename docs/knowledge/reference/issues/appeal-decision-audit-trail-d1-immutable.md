# Appeal Decision Audit Trail D1 Immutable

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

A user appeals a content removal and the decision is overturned. Later, a regulator or lawyer demands the complete decision history: who made the original removal, when, under what policy, who reviewed the appeal, what evidence was considered, and what the final outcome was. Without an immutable audit trail, the platform cannot demonstrate procedural compliance or defend against claims of arbitrary enforcement.

## Context

example project must comply with DSA Article 17 (statement of reasons) and Article 20 (internal complaint-handling). Both require that enforcement decisions and appeal outcomes are documented, explainable, and retained. D1 enforces immutability via insert-only tables — rows are never updated or deleted. A Worker validates the schema and writes the audit record on every state transition. R2 stores larger evidence blobs (screenshots, AI model outputs) referenced by D1 row IDs.

---

## Schema — Insert-Only Audit Table

```sql
-- Run via wrangler d1 execute example project-db
CREATE TABLE IF NOT EXISTS appeal_audit (
  id            TEXT    PRIMARY KEY,           -- ULID
  content_id    TEXT    NOT NULL,              -- post, comment, or account ID
  content_type  TEXT    NOT NULL CHECK (content_type IN ('post','comment','account')),
  event_type    TEXT    NOT NULL CHECK (event_type IN (
                  'content_removed','appeal_opened','appeal_acknowledged',
                  'evidence_submitted','decision_made','decision_overturned',
                  'appeal_closed','legal_hold_applied')),
  actor_id      TEXT    NOT NULL,              -- moderator or system ID (hashed)
  policy_ref    TEXT,                          -- e.g. "ToS § 4.2 – Hate Speech"
  rationale     TEXT,                          -- short human-readable reason
  outcome       TEXT CHECK (outcome IN ('upheld','overturned','partial','pending',NULL)),
  evidence_key  TEXT,                          -- R2 key for supporting blob, if any
  created_at    INTEGER NOT NULL               -- epoch ms, UTC
);

-- No UPDATE or DELETE ever touches this table.
-- Immutability is enforced at the application layer and should be audited periodically.
CREATE INDEX IF NOT EXISTS idx_appeal_audit_content ON appeal_audit (content_id, created_at);
CREATE INDEX IF NOT EXISTS idx_appeal_audit_actor   ON appeal_audit (actor_id, created_at);
```

## Writing Audit Records

Every enforcement action calls `writeAuditEvent`. The function never modifies existing rows.

```typescript
import { generateULID } from './ulid'; // deterministic ULID library

interface AuditEventInput {
  contentId:   string;
  contentType: 'post' | 'comment' | 'account';
  eventType:
    | 'content_removed' | 'appeal_opened'    | 'appeal_acknowledged'
    | 'evidence_submitted' | 'decision_made' | 'decision_overturned'
    | 'appeal_closed'   | 'legal_hold_applied';
  actorId:    string;
  policyRef?: string;
  rationale?: string;
  outcome?:   'upheld' | 'overturned' | 'partial' | 'pending';
  evidenceKey?: string; // R2 object key
}

async function writeAuditEvent(
  db: D1Database,
  event: AuditEventInput,
): Promise<string> {
  const id = generateULID();
  await db.prepare(
    `INSERT INTO appeal_audit
       (id, content_id, content_type, event_type, actor_id, policy_ref, rationale, outcome, evidence_key, created_at)
     VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`,
  ).bind(
    id,
    event.contentId,
    event.contentType,
    event.eventType,
    event.actorId,
    event.policyRef  ?? null,
    event.rationale  ?? null,
    event.outcome    ?? null,
    event.evidenceKey ?? null,
    Date.now(),
  ).run();
  return id;
}
```

## DSA Statement of Reasons Generator

DSA Article 17 requires a statement of reasons delivered to the user within a reasonable time. This function assembles one from the audit trail.

```typescript
interface StatementOfReasons {
  contentId:     string;
  removalReason: string;
  policyRef:     string;
  removedAt:     number;
  appealStatus:  string;
  appealOutcome?: string;
  contactEmail:  string;
}

async function buildStatementOfReasons(
  db: D1Database,
  contentId: string,
): Promise<StatementOfReasons | null> {
  const rows = await db.prepare(
    `SELECT event_type, policy_ref, rationale, outcome, created_at
     FROM appeal_audit
     WHERE content_id = ?
     ORDER BY created_at ASC`,
  ).bind(contentId).all<{
    event_type: string; policy_ref: string | null;
    rationale: string | null; outcome: string | null; created_at: number;
  }>();

  if (rows.results.length === 0) return null;

  const removal  = rows.results.find(r => r.event_type === 'content_removed');
  const decision = rows.results.findLast(r => r.event_type === 'decision_made' || r.event_type === 'decision_overturned');

  return {
    contentId,
    removalReason: removal?.rationale ?? 'Policy violation',
    policyRef:     removal?.policy_ref ?? 'Community Guidelines',
    removedAt:     removal?.created_at ?? 0,
    appealStatus:  decision ? 'decided' : 'pending',
    appealOutcome: decision?.outcome ?? undefined,
    contactEmail:  'appeals@example.com',
  };
}
```

## Evidence Attachment via R2

Large evidence blobs (AI model output JSON, screenshots) are stored in R2; only the key is recorded in D1.

```typescript
async function attachEvidence(
  r2: R2Bucket,
  db: D1Database,
  contentId: string,
  actorId: string,
  evidenceBlob: ArrayBuffer,
  mimeType: string,
): Promise<string> {
  const evidenceKey = `evidence/${contentId}/${Date.now()}-${crypto.randomUUID()}`;
  await r2.put(evidenceKey, evidenceBlob, {
    httpMetadata: { contentType: mimeType },
    customMetadata: { contentId, uploadedBy: actorId },
  });

  await writeAuditEvent(db, {
    contentId,
    contentType: 'post',
    eventType:   'evidence_submitted',
    actorId,
    rationale:   `Evidence blob: ${evidenceKey}`,
    evidenceKey,
  });

  return evidenceKey;
}
```

## Audit Trail Export for Regulators

Produces a JSON-L export of all events for a given content ID, suitable for submission to a regulator or court.

```typescript
async function exportAuditTrail(
  db: D1Database,
  contentId: string,
): Promise<string> {
  const rows = await db.prepare(
    `SELECT * FROM appeal_audit WHERE content_id = ? ORDER BY created_at ASC`,
  ).bind(contentId).all();

  // JSON Lines format — one record per line, human-readable and machine-parseable
  return rows.results.map(r => JSON.stringify(r)).join('\n');
}
```

## Integrity Verification via Row Hash Chain

Optional: each row stores a SHA-256 of `(previous_hash || id || created_at || event_type || actor_id)` to detect post-hoc tampering.

```typescript
async function verifyChainIntegrity(
  db: D1Database,
  contentId: string,
): Promise<{ valid: boolean; brokenAt?: string }> {
  const rows = await db.prepare(
    `SELECT id, event_type, actor_id, created_at, chain_hash, prev_hash
     FROM appeal_audit WHERE content_id = ? ORDER BY created_at ASC`,
  ).bind(contentId).all<{
    id: string; event_type: string; actor_id: string;
    created_at: number; chain_hash: string; prev_hash: string | null;
  }>();

  let prevHash = '';
  for (const row of rows.results) {
    const payload = `${prevHash}|${row.id}|${row.created_at}|${row.event_type}|${row.actor_id}`;
    const hash = Array.from(
      new Uint8Array(await crypto.subtle.digest('SHA-256', new TextEncoder().encode(payload))),
    ).map(b => b.toString(16).padStart(2, '0')).join('');

    if (hash !== row.chain_hash) {
      return { valid: false, brokenAt: row.id };
    }
    prevHash = hash;
  }
  return { valid: true };
}
```

---

## Anti-patterns

- Using `UPDATE` to change the outcome of an existing row — violates immutability; always insert a new `decision_overturned` event instead.
- Storing moderator real names in `actor_id` — use a pseudonymous internal ID; real names are resolved server-side only for authorized personnel.
- Deleting evidence blobs from R2 when content is reinstated — the evidence must be retained for the duration of the legal obligation (typically 6–18 months under DSA).
- Combining the appeal workflow table and the audit table — workflow state is mutable; the audit log is not. Keep them separate.

## Gotchas

- D1 has no `SERIAL` / auto-increment that is globally unique across WAL checkpoints. Use ULIDs (lexicographically sortable) as primary keys.
- D1 `INTEGER` stores up to 64-bit signed integers. Epoch ms values fit comfortably.
- The `chain_hash` integrity scheme requires that the `chain_hash` column be populated at insert time by the Worker — D1 has no stored procedures or triggers.
- R2 object keys are case-sensitive. Normalise to lowercase to avoid key collisions.

## Verification

```bash
# Insert a test removal event and confirm it appears
wrangler d1 execute example project-db --command \
  "SELECT id, event_type, policy_ref, created_at FROM appeal_audit ORDER BY created_at DESC LIMIT 5"

# Confirm no UPDATE/DELETE statements have touched the table (check D1 WAL)
wrangler d1 execute example project-db --command \
  "SELECT COUNT(*) as total FROM appeal_audit WHERE content_id = '<test_id>'"

# Export audit trail for a content ID
curl -s https://example.com/internal/audit/export?contentId=<test_id> \
  -H "Authorization: Bearer $INTERNAL_TOKEN"
```

---

## Related

- `platform-audit-log-immutable-d1-workers.md`
- `content-appeal-escalation-workflow-durable-objects.md`
- `legal-hold-evidence-preservation-d1-r2.md`
- `automated-dispute-resolution-d1-appeals-workflow.md`
- `account-suspension-appeals-worker-workflow.md`
- `right-to-erasure-gdpr-ccpa-deletion-workflow-d1-r2.md`

## Sources

- DSA Article 17 (statement of reasons) — https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:32022R2065
- DSA Article 20 (internal complaint-handling) — https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:32022R2065
- Cloudflare D1 docs — https://developers.cloudflare.com/d1/
- Cloudflare R2 docs — https://developers.cloudflare.com/r2/
