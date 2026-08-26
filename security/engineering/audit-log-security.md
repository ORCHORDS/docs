# audit-log-security

**Issue:** Audit log security — integrity, confidentiality, retention
**Date:** 2026-08-09
**Status:** documented

## Symptom
You build an audit log. Every privileged action is logged.
A user asks "what happened on March 15?" You query the
log. The log is empty. An attacker deleted the log
entries. Or the log was modified. Or the log was
compromised.

## Root cause
**Audit logs are not "log everything; forget it."** They
have security requirements.

**Source:** NIST — Audit Logs:
https://csrc.nist.gov/publications/detail/sp/800-92/final

> "Audit logs are critical for the security of an
> organization. They provide a record of activities that
> can be used to detect, understand, and recover from
> attacks."

## The "audit log" properties

For a security audit log:
- **Confidentiality:** Only authorized users can read
- **Integrity:** Entries cannot be modified
- **Availability:** Entries are retained for the required
  period
- **Non-repudiation:** An actor cannot deny their actions

## The "append-only" pattern

For integrity, the log is append-only:
```sql
-- No UPDATE or DELETE allowed
CREATE TABLE audit_log (
  id TEXT PRIMARY KEY,
  -- ... columns
);

-- Database user has only INSERT + SELECT
GRANT INSERT, SELECT ON audit_log TO app_user;
-- No UPDATE, DELETE
```

The DB user doesn't have UPDATE/DELETE on the audit table.

## The "hash chain" pattern

For tamper detection, each entry includes the hash of the
previous:
```ts
async function writeAudit(event: AuditEvent, env: Env): Promise<void> {
  // 1. Get the last entry's hash
  const lastEntry = await env.DB!.prepare(
    `SELECT hash FROM audit_log ORDER BY timestamp DESC LIMIT 1`
  ).first<{ hash: string }>();

  // 2. Compute the new hash
  const data = JSON.stringify({ ...event, prevHash: lastEntry?.hash ?? '0' });
  const hash = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(data));
  const hashHex = Buffer.from(hash).toString('hex');

  // 3. Insert
  await env.DB!.prepare(
    `INSERT INTO audit_log (id, data, prev_hash, hash, timestamp) VALUES (?, ?, ?, ?, ?)`
  ).bind(
    crypto.randomUUID(),
    data,
    lastEntry?.hash ?? null,
    hashHex,
    new Date().toISOString(),
  ).run();
}
```

The hash chain detects tampering (modifying any entry
invalidates all subsequent hashes).

## The "signed log" pattern

For non-repudiation, sign each entry with an HSM key:
```ts
async function writeSignedAudit(event: AuditEvent, env: Env): Promise<void> {
  const data = JSON.stringify(event);
  const signature = await env.HSM.sign(data);  // HSM signs

  await env.DB!.prepare(
    `INSERT INTO audit_log (id, data, signature, timestamp) VALUES (?, ?, ?, ?)`
  ).bind(crypto.randomUUID(), data, signature, new Date().toISOString()).run();
}

async function verifyAudit(auditId: string, env: Env): Promise<boolean> {
  const entry = await env.DB!.prepare(`SELECT * FROM audit_log WHERE id = ?`).bind(auditId).first();
  if (!entry) return false;

  return env.HSM.verify(entry.data, entry.signature);  // HSM verifies
}
```

The HSM signs; only the HSM can sign. The signature is
verified before the entry is used.

## The "external storage" pattern

For an attacker-resistant log, store externally:
```ts
// 1. Log to the in-app table (for queries)
await env.DB!.prepare(`INSERT INTO audit_log ...`).run();

// 2. Also ship to an external service
await fetch('https://audit.example.com/v1/log', {
  method: 'POST',
  headers: { 'Authorization': `Bearer ${env.AUDIT_TOKEN}` },
  body: JSON.stringify({ ...event, timestamp: new Date().toISOString() }),
});
```

The external service is a copy; an attacker would need to
compromise both.

## The "log shipping" pattern

For shipping logs, use Logpush:
```toml
# wrangler.toml
[[unsafe.bindings]]
type = "logpush"
name = "AUDIT_LOG_DESTINATION"
destination = "r2"
dataset = "audit_logs"
```

CF's Logpush ships logs to R2 / Datadog / Splunk.

## The "retention" pattern

For retention, the rule depends on the standard:
- **GDPR:** "No longer than necessary" (depends on use)
- **HIPAA:** 6 years
- **PCI-DSS:** 1 year online + 3 months immediately available
- **SOX:** 7 years
- **SOC 2:** 1 year minimum
- **Financial:** 5-7 years

Configure the retention per your compliance requirements.

## The "PII in audit log" pattern

For PII, be careful:
- ❌ Don't log: passwords, credit cards, full SSN
- ✅ Do log: user ID (hashed if possible), action, timestamp

For GDPR, the audit log may contain personal data. A legal
basis is required (e.g. "legitimate interest" for security
logs).

## The "encryption at rest" pattern

For sensitive audit logs, encrypt:
```ts
async function writeEncryptedAudit(event: AuditEvent, env: Env): Promise<void> {
  const ciphertext = await encrypt(JSON.stringify(event), env.AUDIT_KEY);
  await env.DB!.prepare(
    `INSERT INTO audit_log (id, encrypted_data, timestamp) VALUES (?, ?, ?)`
  ).bind(crypto.randomUUID(), ciphertext, new Date().toISOString()).run();
}
```

The audit log is encrypted; only authorized readers can
decrypt.

## The "access control" pattern

For access, only authorized users can read:
```sql
-- Only admins can read
GRANT SELECT ON audit_log TO admin_user;
GRANT INSERT ON audit_log TO app_user;
```

The audit log is read-only for app users; only admins
can read.

## The "alerting" pattern

For alerts, monitor the log:
- **Failed logins > N per minute:** Possible attack
- **Admin actions out of hours:** Possible breach
- **Mass deletes:** Possible data exfiltration
- **Log tampering (hash mismatch):** Possible compromise

```ts
if (await isHashChainValid(env) === false) {
  await pageOncall('Audit log tampering detected', { ... });
}
```

The log integrity is monitored.

## The "compliance" report

For compliance, generate reports:
```ts
async function generateAuditReport(startDate: string, endDate: string, env: Env): Promise<Report> {
  // 1. All admin actions
  const adminActions = await env.DB!.prepare(`
    SELECT * FROM audit_log
    WHERE action LIKE 'admin.%'
      AND timestamp BETWEEN ? AND ?
  `).bind(startDate, endDate).all();

  // 2. All failed logins
  const failedLogins = await env.DB!.prepare(`
    SELECT * FROM audit_log
    WHERE action = 'user.login.failed'
      AND timestamp BETWEEN ? AND ?
  `).bind(startDate, endDate).all();

  // 3. All PII access
  const piiAccess = await env.DB!.prepare(`
    SELECT * FROM audit_log
    WHERE resource_type = 'user.pii'
      AND timestamp BETWEEN ? AND ?
  `).bind(startDate, endDate).all();

  return { adminActions, failedLogins, piiAccess };
}
```

The report is the compliance evidence.

## The "audit log" anti-patterns

### 1. Log to local file
- **Issue:** An attacker can modify the file
- **Fix:** Log to a DB + external service

### 2. No integrity protection
- **Issue:** An attacker can modify the log
- **Fix:** Hash chain or signed entries

### 3. PII in the log
- **Issue:** GDPR / privacy issue
- **Fix:** Hash user IDs; minimize PII

### 4. No retention
- **Issue:** Old logs pile up; new logs push them out
- **Fix:** Configure retention per compliance

### 5. No access control
- **Issue:** Anyone can read the log
- **Fix:** Restrict to admins

### 6. No alerting
- **Issue:** Suspicious activity goes unnoticed
- **Fix:** Alert on anomalies

## Verification
- **Test:** Audit log captures the action
- **Test:** Audit log is append-only
- **Test:** Tampering is detected
- **Audit:** Quarterly review of audit logs
- **Pen test:** Annual security review

## Gotchas
- **The "log everything" anti-pattern.** Logging too much
  includes PII; logs grow unbounded.
- **The "no integrity" anti-pattern.** An attacker can
  modify logs.
- **The "no retention" anti-pattern.** Logs grow
  unbounded; old logs are lost.
- **The "no alert" anti-pattern.** Suspicious activity
  goes unnoticed.
- **The "audit log is in the same DB" anti-pattern.** An
  attacker who compromises the DB can modify the logs.

## Related
- `audit-log-as-product.md`
- `audit-log-mandatory.md`
- `gdpr-article-17-erasure.md`
- `compliance/audit-log-mandatory.md`
- `encryption-at-rest-detail.md`
- NIST: https://csrc.nist.gov/publications/detail/sp/800-92/final
- AWS: https://docs.aws.amazon.com/prescriptive-guidance/latest/aws-security-incident-response-guide/auditing.html
