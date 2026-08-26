# audit-log-as-product

**Issue:** Audit log design — what to log, retention, search
**Date:** 2026-08-09
**Status:** documented

## Symptom
You build a feature. You add a console.log when it runs.
A year later, a customer asks "what happened to my account
on March 15?" You grep your logs. You find nothing useful.
The data you need wasn't logged.

## Root cause
**Logs are afterthoughts.** Most teams add logs during
development, then never look at them again. By the time
you need them, the data you need isn't there.

**Source:** OWASP — Logging:
https://owasp.org/www-project-application-security-verification-standard/

> "Logging is an important aspect of application security.
> ... Without proper logging, security incidents may go
> undetected."

## The "audit log vs debug log" distinction

### Debug log
- **What:** Developer-facing; for debugging
- **Format:** Free-form text
- **Volume:** High (every request, every query)
- **Retention:** Days (cost of storage)
- **Use:** Find a bug; understand what happened

### Audit log
- **What:** Compliance-facing; for accountability
- **Format:** Structured (JSON, with required fields)
- **Volume:** Lower (state changes, auth events)
- **Retention:** Months to years (compliance)
- **Use:** Prove what happened; forensically analyze a
  breach; support compliance audits

This entry is about **audit log** (the compliance kind).

## The "what to log" checklist

For every feature, the audit log should capture:
- [ ] **Who:** userId, tenantId, IP, user-agent
- [ ] **What:** action (create, read, update, delete, login,
  logout, etc.)
- [ ] **When:** ISO 8601 timestamp (UTC)
- [ ] **Where:** resource type, resource ID
- [ ] **Why:** the reason (if the action is privileged)
- [ ] **Result:** success, failure, error code
- [ ] **From where:** the request ID (for correlation)

```ts
await writeAudit(env, {
  userId: ctx.user.id,
  tenantId: ctx.tenant.id,
  action: 'user.deleted',
  resourceType: 'user',
  resourceId: 'u_123',
  reason: 'GDPR Article 17 erasure request',
  result: 'success',
  ip: ctx.request.headers.get('cf-connecting-ip'),
  userAgent: ctx.request.headers.get('user-agent'),
  requestId: ctx.requestId,
  timestamp: new Date().toISOString(),
});
```

## The "what NOT to log" list

❌ **Passwords** (plain or hashed)
❌ **API keys / tokens** (any kind)
❌ **Credit card numbers** (PCI-DSS violation)
❌ **SSN, passport, government IDs** (PII)
❌ **PII (email, phone, name) in plaintext** (hash or omit)
❌ **Free-form user input** (XSS risk in a log viewer)
❌ **Health data, financial data** (special category under GDPR)

For GDPR, "personal data" in logs requires a legal basis
(consent, contract, etc.). Most apps log a `userId` (a
pseudonym) and avoid PII.

## The "structured audit log" format

```ts
interface AuditEvent {
  // Required
  timestamp: string;     // ISO 8601
  action: string;        // e.g. "user.deleted"
  actorId: string;       // Who did it
  resourceType: string;  // What was acted on
  resourceId: string;    // Specific resource

  // Optional
  actorIp?: string;
  actorUserAgent?: string;
  reason?: string;       // Why
  result?: 'success' | 'failure';
  errorCode?: string;
  requestId?: string;    // For correlation
  tenantId?: string;     // For multi-tenant
  metadata?: Record<string, unknown>;
}
```

This is the shape stored in the audit table / D1 / DO.

## The "audit log" storage

### D1 table
```sql
CREATE TABLE audit_log (
  id TEXT PRIMARY KEY,
  timestamp TEXT NOT NULL,
  action TEXT NOT NULL,
  actor_id TEXT NOT NULL,
  resource_type TEXT NOT NULL,
  resource_id TEXT NOT NULL,
  actor_ip TEXT,
  actor_user_agent TEXT,
  reason TEXT,
  result TEXT,
  error_code TEXT,
  request_id TEXT,
  tenant_id TEXT,
  metadata TEXT,  -- JSON
  created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX idx_audit_timestamp ON audit_log(timestamp);
CREATE INDEX idx_audit_actor ON audit_log(actor_id);
CREATE INDEX idx_audit_resource ON audit_log(resource_type, resource_id);
```

### R2 (for cold storage)
For long retention, export to R2:
```ts
// Periodic job: export old audit log to R2
const oldLogs = await env.DB!.prepare(`
  SELECT * FROM audit_log WHERE timestamp < datetime('now', '-90 days')
`).all();
await env.AUDIT_BUCKET!.put(`audit/${year}/${month}/${day}.jsonl`,
  JSON.stringify(oldLogs.results));
await env.DB!.prepare(`
  DELETE FROM audit_log WHERE timestamp < datetime('now', '-90 days')
`).run();
```

### External service
For higher volume, use a managed audit log service:
- **Cloudflare Logpush** → R2 / Datadog
- **AWS CloudTrail** (for AWS)
- **Splunk / Datadog / Honeycomb** (for search)

## The "tamper-proof" requirement

For compliance, the audit log must be tamper-proof. Options:

1. **Append-only:** The log is append-only; no UPDATE or
   DELETE
2. **Signed entries:** Each entry is signed with an HSM key
3. **External storage:** Logs are shipped to an external
   service the operator can't modify
4. **Hash chain:** Each entry includes the hash of the
   previous; tampering is detectable

For most apps, **append-only** is sufficient. The DB
permissions don't include UPDATE/DELETE on the audit table.

For more sensitive (financial, health), use **hash chain** or
**external storage** (see `audit-chain-durable-object.md`).

## The "search" pattern

The audit log must be searchable. Common queries:
- "All actions by user X in the last 30 days"
- "All actions on resource Y"
- "All failed logins from IP Z"
- "All admin actions in the last year"

```ts
// Indexes make these fast
CREATE INDEX idx_audit_actor_timestamp ON audit_log(actor_id, timestamp);
CREATE INDEX idx_audit_resource_timestamp ON audit_log(resource_type, resource_id, timestamp);
```

For more complex queries, use a search service (Algolia,
ElasticSearch).

## The "retention" rules

- **GDPR:** Personal data can be retained "no longer than
  necessary." For audit logs, this is typically 1-7 years,
  depending on the industry.
- **HIPAA:** 6 years
- **PCI-DSS:** 1 year (online), 3 months (immediately
  available)
- **SOX:** 7 years
- **SOC 2:** 1 year minimum

Configure the retention per your compliance requirements.

## The "cost" consideration

Audit logs are write-heavy. At 1M events/day, the cost adds
up:
- **D1:** $1 per million writes = $30/month for 1M/day
- **R2:** $4.50 per million PUTs = $135/month for 1M/day
- **Logpush to Datadog:** ~$0.10 per GB = varies

For high-volume apps, use batch writes (insert every N
seconds, not every event).

## Verification
- **Test:** `test/audit.test.ts > every privileged action is
  logged` — passes
- **Live:** Audit log is queried periodically (e.g. daily
  compliance report)
- **Audit:** Annual review of what's logged + retention

## Gotchas
- **The audit log is a SPOF.** If it's down, you can't log
  the action. The user request should still succeed.
  Failed log writes should not block the request.
- **The "PII in logs" risk** is huge. One leak and you're
  under GDPR / CCPA. Hash or omit PII.
- **The "log volume" surprises teams.** 1M users × 1
  action/day = 1M log entries. Budget for storage.
- **The "who watches the watcher" question.** The audit
  log itself is a target. Use append-only or signed logs.
- **The "log search" performance.** Searching 1M log entries
  is slow without indexes. Indexes are mandatory.

## Related
- `audit-chain-durable-object.md`
- `audit-log-mandatory.md` (compliance requirement)
- `gdpr-article-17-erasure.md` (when to delete audit data)
- `structured-logging.md` (debug log)
- OWASP: https://owasp.org/www-project-application-security-verification-standard/
- GDPR: https://gdpr-info.eu/
