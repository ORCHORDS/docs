# ENISA Data Minimization Guidelines — Cloudflare Workers Implementation

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

Your engineering team is asked to demonstrate that the platform applies data minimization in a
technically verifiable way, not just as a policy statement. Legal references the **ENISA
Guidelines on Data Minimization** (published 2023, updated 2024) and expects you to map each
recommended technique to specific code in your Cloudflare Workers + D1 stack.

---

## Context

The European Union Agency for Cybersecurity (**ENISA**) published a set of technical guidelines
on data minimization under GDPR Article 5(1)(c). The guidelines identify four implementation
families:

| Family | Core idea |
|---|---|
| **Collection minimization** | Collect only what is strictly necessary at the time of collection |
| **Retention minimization** | Delete or anonymise data at the earliest moment it is no longer required |
| **Processing minimization** | Limit the spread of personal data within processing pipelines |
| **Disclosure minimization** | Reduce what is revealed in API responses, logs, and analytics |

These are not ENISA-specific inventions — they operationalize GDPR Article 5(1)(c). But the
guidelines provide concrete implementation patterns that DPAs (notably in Germany, France, and
the Netherlands) cite during audits as the expected standard.

---

## Family 1 — Collection Minimization

### Principle

Never capture a field unless there is a documented, purpose-tied reason for it. "We might need
it later" is not a valid reason.

### Implementation: Schema-level enforcement with purpose annotations

```sql
-- Every column in a user-data table must have a documented purpose
CREATE TABLE IF NOT EXISTS users (
  id           INTEGER PRIMARY KEY AUTOINCREMENT,
  -- Purpose: account authentication (required)
  email        TEXT    NOT NULL,
  -- Purpose: billing address for EU VAT (required if B2B EU)
  vat_number   TEXT,
  -- Purpose: product analytics (optional — collected only with analytics consent)
  locale       TEXT,
  -- Purpose: NONE — removed 2025-09-01 (was: A/B test cohort, no longer needed)
  -- cohort_id removed
  created_at   TEXT    NOT NULL
);

-- Companion table: purpose registry forces teams to justify every attribute
CREATE TABLE IF NOT EXISTS data_attribute_registry (
  id                INTEGER PRIMARY KEY AUTOINCREMENT,
  table_name        TEXT    NOT NULL,
  column_name       TEXT    NOT NULL,
  processing_purpose TEXT   NOT NULL,
  legal_basis       TEXT    NOT NULL,
  minimum_necessary INTEGER NOT NULL DEFAULT 1, -- 1 = confirmed minimal, 0 = under review
  added_at          TEXT    NOT NULL,
  removed_at        TEXT,           -- NULL = still active
  UNIQUE (table_name, column_name)
);
```

### Implementation: Collector function with allow-list

```typescript
// workers/collect.ts
// Explicit allow-list approach: any field not listed is stripped before persistence

const ALLOWED_FIELDS_BY_PURPOSE: Record<string, Set<string>> = {
  account_creation: new Set(["email", "password_hash", "locale"]),
  billing:          new Set(["email", "vat_number", "country_code"]),
  analytics:        new Set(["locale", "plan_tier", "created_at"]),
};

export function minimizePayload(
  rawPayload: Record<string, unknown>,
  purposes: string[]
): Record<string, unknown> {
  const allowed = new Set<string>();
  for (const purpose of purposes) {
    const fields = ALLOWED_FIELDS_BY_PURPOSE[purpose];
    if (fields) fields.forEach((f) => allowed.add(f));
  }

  const minimized: Record<string, unknown> = {};
  for (const [key, value] of Object.entries(rawPayload)) {
    if (allowed.has(key)) {
      minimized[key] = value;
    }
    // Silently drop fields not in the allow-list — do NOT log their values
  }
  return minimized;
}
```

---

## Family 2 — Retention Minimization

### Principle

Data that has served its purpose is a liability. Automate deletion or anonymization using
Cloudflare Cron Triggers against D1.

### Retention policy table

```sql
CREATE TABLE IF NOT EXISTS retention_policy (
  id             INTEGER PRIMARY KEY AUTOINCREMENT,
  table_name     TEXT    NOT NULL,
  purpose        TEXT    NOT NULL,
  retention_days INTEGER NOT NULL,
  action         TEXT    NOT NULL DEFAULT 'anonymise',  -- 'delete' | 'anonymise' | 'archive'
  UNIQUE(table_name, purpose)
);

-- Example policies
INSERT OR IGNORE INTO retention_policy (table_name, purpose, retention_days, action) VALUES
  ('users',       'account_active',    3650, 'anonymise'),
  ('audit_log',   'security',          2555, 'archive'),
  ('consent_log', 'consent_evidence',  1825, 'archive'),
  ('analytics',   'product_analytics',  365, 'delete'),
  ('session_log', 'auth',               90,  'delete');
```

### Cron Worker — automated purge

```typescript
// workers/retention-cron.ts
export default {
  async scheduled(_event: ScheduledEvent, env: Env, _ctx: ExecutionContext) {
    const policies = await env.DB.prepare(
      "SELECT * FROM retention_policy"
    ).all<{ table_name: string; purpose: string; retention_days: number; action: string }>();

    for (const policy of policies.results) {
      const cutoff = new Date();
      cutoff.setDate(cutoff.getDate() - policy.retention_days);

      if (policy.action === "delete") {
        const res = await env.DB.prepare(`
          DELETE FROM ${policy.table_name}
          WHERE created_at < ?
        `).bind(cutoff.toISOString()).run();
        await logRetentionRun(env, policy, res.meta.changes ?? 0, "deleted");
      } else if (policy.action === "anonymise") {
        const res = await env.DB.prepare(`
          UPDATE ${policy.table_name}
          SET    email     = 'anon-' || id || '@anon.invalid',
                 full_name = NULL,
                 ip_address = NULL
          WHERE  created_at < ?
          AND    anonymised_at IS NULL
        `).bind(cutoff.toISOString()).run();
        await logRetentionRun(env, policy, res.meta.changes ?? 0, "anonymised");
      }
    }
  },
};

async function logRetentionRun(
  env: Env,
  policy: { table_name: string; purpose: string },
  rowsAffected: number,
  action: string
): Promise<void> {
  await env.DB.prepare(`
    INSERT INTO retention_run_log (table_name, purpose, action, rows_affected, ran_at)
    VALUES (?, ?, ?, ?, ?)
  `).bind(
    policy.table_name,
    policy.purpose,
    action,
    rowsAffected,
    new Date().toISOString()
  ).run();
}
```

---

## Family 3 — Processing Minimization

### Principle

Restrict which internal systems and service roles can access personal data. Use column-level
access controls and function-level data masking.

### Masked data access by role

```typescript
// workers/data-access.ts
type AccessRole = "support_l1" | "support_l2" | "billing" | "admin" | "analytics";

interface UserRecord {
  id: number;
  email: string;
  full_name: string | null;
  vat_number: string | null;
  plan_tier: string;
}

const FIELD_VISIBILITY: Record<AccessRole, (keyof UserRecord)[]> = {
  support_l1:  ["id", "plan_tier"],                              // cannot see PII
  support_l2:  ["id", "email", "plan_tier"],                    // can see email only
  billing:     ["id", "email", "vat_number"],                   // billing fields
  analytics:   ["id", "plan_tier"],                             // no PII ever
  admin:       ["id", "email", "full_name", "vat_number", "plan_tier"],
};

export function applyRoleMask(
  record: UserRecord,
  role: AccessRole
): Partial<UserRecord> {
  const visible = new Set(FIELD_VISIBILITY[role]);
  const masked: Partial<UserRecord> = {};
  for (const key of Object.keys(record) as (keyof UserRecord)[]) {
    if (visible.has(key)) {
      masked[key] = record[key] as never;
    }
  }
  return masked;
}
```

### Pseudonymization for analytics pipelines

```typescript
// workers/pseudonymize.ts
// Replace direct identifiers with stable but non-reversible tokens for analytics

export async function pseudonymizeUserId(
  rawId: string,
  salt: string
): Promise<string> {
  const data = new TextEncoder().encode(rawId + salt);
  const hashBuffer = await crypto.subtle.digest("SHA-256", data);
  return Array.from(new Uint8Array(hashBuffer))
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("")
    .slice(0, 16); // 64-bit pseudonym — short enough to handle, long enough to be non-guessable
}
```

---

## Family 4 — Disclosure Minimization

### Principle

API responses and logs should not expose personal data unless the requesting party is authorised
and has a specific need.

### Response scrubber middleware

```typescript
// workers/response-scrubber.ts
// Strip PII from any field not in the explicit disclosure allow-list before sending

const DISCLOSURE_ALLOW_LIST = new Set([
  "id", "plan_tier", "created_at", "locale", "status",
]);

export function scrubResponse(obj: Record<string, unknown>): Record<string, unknown> {
  const scrubbed: Record<string, unknown> = {};
  for (const [key, value] of Object.entries(obj)) {
    if (DISCLOSURE_ALLOW_LIST.has(key)) {
      scrubbed[key] = value;
    } else {
      scrubbed[key] = "[REDACTED]";
    }
  }
  return scrubbed;
}
```

### Log scrubbing in Workers

```typescript
// workers/logger.ts
// Never log PII; replace known-sensitive field patterns with tokens

const PII_PATTERNS: [RegExp, string][] = [
  [/\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b/gi, "[EMAIL]"],
  [/\b\d{4}[- ]?\d{4}[- ]?\d{4}[- ]?\d{4}\b/g,    "[CARD]"],
  [/\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b/g,      "[IP]"],
  [/\bBearer [A-Za-z0-9\-._~+/]+=*\b/g,            "[TOKEN]"],
];

export function scrubLog(message: string): string {
  let clean = message;
  for (const [pattern, replacement] of PII_PATTERNS) {
    clean = clean.replace(pattern, replacement);
  }
  return clean;
}

export function log(env: Env, level: "info" | "warn" | "error", message: string): void {
  const clean = scrubLog(message);
  consolelevel;
}
```

---

## Audit Evidence

ENISA guidelines recommend maintaining demonstrable evidence of minimization:

```sql
-- Data minimization audit trail
CREATE TABLE IF NOT EXISTS minimization_audit (
  id             INTEGER PRIMARY KEY AUTOINCREMENT,
  event_type     TEXT NOT NULL,  -- 'collection_drop'|'retention_purge'|'disclosure_scrub'
  table_name     TEXT,
  field_name     TEXT,
  rows_affected  INTEGER,
  reason         TEXT,
  performed_at   TEXT NOT NULL
);
```

---

## Anti-patterns

- **Minimizing only at collection.** ENISA guidelines cover all four families. Collecting
  minimally but then retaining forever or logging freely violates the spirit and letter of
  Article 5(1)(c).
- **Hard-coding allow-lists in multiple files.** Maintain a single source of truth (the
  `data_attribute_registry` table or a config file) that generates allow-lists at build time.
- **Pseudonymizing with a static, repo-committed salt.** The salt must be a secret stored in
  Wrangler secrets, not in source code.
- **Using `SELECT *` in production queries.** Always enumerate only the columns you need.

---

## Gotchas

- `crypto.subtle.digest` in Cloudflare Workers is available and FIPS-compliant. Do not use
  MD5 for pseudonymization — use SHA-256 or better.
- ENISA guidelines are not legally binding on their own, but DPAs in DE, FR, NL treat them as
  the expected technical standard and cite non-compliance in enforcement decisions.
- Anonymization is irreversible by design. If downstream processes may need re-identification,
  use pseudonymization and store the mapping key in a separate, access-controlled table.
- Cloudflare's `CF-Connecting-IP` header is a personal datum. Apply log scrubbing before any
  persistent storage.

---

## Verification

```bash
# 1. Check that retention cron is wired up
grep "crons" wrangler.toml

# 2. Verify retention_policy table has rows
wrangler d1 execute <DB> --command "SELECT * FROM retention_policy"

# 3. Confirm no SELECT * in Worker source
grep -rn "SELECT \*" workers/ && echo "FAIL: SELECT * found" || echo "PASS"

# 4. Check scrubLog strips email
node -e "
const { scrubLog } = require('./workers/logger');
console.assert(
  !scrubLog('user@example.com logged in').includes('@'),
  'Email not scrubbed'
);
console.log('scrubLog test passed');
"

# 5. Verify data_attribute_registry is complete
wrangler d1 execute <DB> --command \
  "SELECT table_name, column_name FROM data_attribute_registry WHERE minimum_necessary=0"
```

---

## Related

- `data-minimization-workers-d1-pii-redaction.md`
- `gdpr-data-retention-policy.md`
- `data-retention-automated-deletion-workers.md`
- `privacy-by-design-checklist.md`
- `privacy-enhancing-technologies-pets.md`
- `nist-privacy-framework-version-and-profile-governance.md`

---

## Sources

- ENISA Guidelines on Data Minimization (2023): https://www.enisa.europa.eu/
- GDPR Article 5(1)(c) — data minimisation principle
- EDPB Guidelines 4/2019 on Article 25 (Data Protection by Design and by Default)
- Cloudflare Workers crypto API: https://developers.cloudflare.com/workers/runtime-apis/web-crypto/
- Cloudflare D1 documentation: https://developers.cloudflare.com/d1/
