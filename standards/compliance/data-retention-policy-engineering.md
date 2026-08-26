# Data Retention Policies — Engineering Implementation and Compliance

**Date:** 2026-08-16
**Author:** the platform team
**Status:** published

## Symptom

Your database stores user data indefinitely — every account, message,
log entry, and analytics event since launch. Storage costs grow linearly
with no ceiling. GDPR deletion requests take weeks to fulfill because
data is scattered across dozens of tables, caches, backups, and
third-party services. Legal asks "how long do we keep X?" and
engineering has no documented answer. A compliance audit reveals that
you retain personal data far longer than your privacy policy states.

## Context

Data retention policies define how long data is stored and when it must
be deleted. They are required by GDPR (Article 5(1)(e) — storage
limitation principle), CCPA, HIPAA, PCI DSS, and most data protection
regulations. In 2026, enforcement is active: the Irish DPC fined Meta
€1.2 billion for inadequate retention practices, and the FTC has ordered
companies to delete data collected beyond stated retention periods.
Engineering implementation of retention policies requires automated
deletion pipelines, backup rotation, cross-service data mapping, and
audit logging of deletions.

## Retention categories

| Data type | Retention period | Regulation | Rationale |
|---|---|---|---|
| User account data | Duration of account + 30 days | GDPR Art. 17 | Deletion on account closure |
| Transaction records | 7 years | Tax law, PCI DSS | Financial audit requirements |
| Server logs | 90 days | Internal policy | Debugging, incident investigation |
| Analytics events | 26 months | GDPR guidance | Google Analytics default |
| Payment card data | Until transaction settled | PCI DSS 4.0 | Minimize cardholder data |
| Support tickets | 3 years | Business need | Dispute resolution |
| Audit logs | 7 years | SOC 2, DORA | Compliance evidence |
| Marketing consent | Duration of consent + 3 years | GDPR Art. 7 | Prove consent was given |
| Session tokens | 24 hours - 30 days | Security best practice | Minimize session hijack window |
| Backups | 90 days (rolling) | DR policy | Balance recovery vs. retention |

## Architecture

```
Data Retention Pipeline:

┌─────────────┐     ┌──────────────┐     ┌────────────┐
│ Data Catalog │────►│ Retention    │────►│ Deletion   │
│ (what data   │     │ Policy       │     │ Executor   │
│  where)      │     │ Engine       │     │            │
└─────────────┘     └──────────────┘     └────────────┘
                           │                    │
                    ┌──────┴──────┐      ┌──────┴──────┐
                    │ Schedule    │      │ Audit Log   │
                    │ (daily/     │      │ (what was   │
                    │  weekly)    │      │  deleted)   │
                    └─────────────┘      └─────────────┘
```

## Implementation patterns

### Database-level TTL

```sql
-- PostgreSQL: partition by month, drop old partitions
CREATE TABLE events (
    id         BIGINT GENERATED ALWAYS AS IDENTITY,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    event_type TEXT NOT NULL,
    payload    JSONB
) PARTITION BY RANGE (created_at);

-- Create monthly partitions
CREATE TABLE events_2026_08 PARTITION OF events
    FOR VALUES FROM ('2026-08-01') TO ('2026-09-01');

-- Drop partitions older than 90 days (fast, no row-by-row delete)
DROP TABLE events_2026_05;
```

```javascript
// MongoDB: TTL index (automatic deletion)
db.sessions.createIndex(
  { createdAt: 1 },
  { expireAfterSeconds: 86400 } // Delete after 24 hours
);

// Redis: key-level TTL
await redis.set('session:abc123', data, 'EX', 86400);
```

### Application-level retention job

```python
import schedule
from datetime import datetime, timedelta

def enforce_retention():
    cutoffs = {
        'server_logs': timedelta(days=90),
        'analytics_events': timedelta(days=26 * 30),
        'support_tickets': timedelta(days=3 * 365),
        'deleted_accounts': timedelta(days=30),
    }

    for table, retention in cutoffs.items():
        cutoff_date = datetime.utcnow() - retention
        count = db.execute(
            f"DELETE FROM {table} WHERE created_at < %s RETURNING id",
            [cutoff_date]
        )
        audit_log.record(
            action='retention_delete',
            table=table,
            cutoff=cutoff_date,
            rows_deleted=count,
        )

schedule.every().day.at("03:00").do(enforce_retention)
```

### Cross-service deletion (GDPR right to erasure)

```
User requests account deletion:

1. Primary database
   □ Soft-delete user record (mark as deleted)
   □ Start 30-day grace period (allow recovery)
   □ After grace period: hard-delete or anonymize

2. Related services
   □ Analytics: delete or anonymize user events
   □ Email service: remove from all lists
   □ Payment processor: delete saved cards (API call)
   □ CDN: purge user-uploaded content
   □ Search index: remove user from search results
   □ Message queues: purge pending messages with user ID

3. Backups
   □ Cannot delete from existing backups (impractical)
   □ Document in privacy policy: "retained in backups
     for up to 90 days after deletion"
   □ Ensure retention policy rotates backups within window

4. Audit trail
   □ Log that deletion was performed
   □ Retain deletion audit log (without personal data)
   □ Deletion receipt with timestamp and scope
```

## Anonymization vs. deletion

```
Deletion:
  → Removes data entirely
  → Required when no legal basis to retain
  → Simplest approach

Anonymization:
  → Replaces identifiable data with non-reversible values
  → Retains aggregate/statistical value
  → GDPR: properly anonymized data is not personal data
  → Must be truly irreversible (pseudonymization is not enough)

Example:
  Before: { user: "jane@example.com", country: "DE", purchases: 5 }
  After:  { user: "anon_a1b2c3", country: "DE", purchases: 5 }

  Anonymized data retains analytical value (purchases by country)
  without identifying the individual.
```

## Anti-patterns

- **No retention policy** — storing all data indefinitely. This
  violates GDPR storage limitation, increases storage costs linearly,
  and creates unbounded liability. Define retention periods for every
  data category.
- **Manual deletion** — relying on support staff to manually delete
  data on request. This is slow, error-prone, and does not scale.
  Automate retention enforcement with scheduled jobs.
- **Deleting from production but not backups** — claiming data is
  deleted while it persists in backups for years. Document backup
  retention in your privacy policy and ensure backup rotation aligns
  with retention periods.
- **Pseudonymization as anonymization** — replacing names with IDs
  while keeping a mapping table. This is pseudonymization (still
  personal data under GDPR), not anonymization. True anonymization
  must be irreversible.

## Gotchas

- **Foreign key constraints** — deleting a user record that is
  referenced by orders, invoices, and audit logs fails on foreign
  key constraints. Design schemas for deletion: use soft deletes,
  cascade deletes, or nullify references.
- **Legal holds** — litigation or regulatory investigation can
  require preserving data that would otherwise be deleted. Implement
  a legal hold mechanism that pauses retention deletion for specific
  records.
- **Backup restoration restores deleted data** — if you restore
  from a backup, previously deleted data reappears. Post-restoration
  procedures must re-run deletion jobs to re-delete data that was
  removed after the backup was taken.
- **Third-party data processors** — your retention policy must
  extend to third-party services (analytics, CRM, email marketing).
  Include data deletion requirements in Data Processing Agreements
  (DPAs) and verify compliance.

## Verification

- Every data category has a documented retention period.
- Automated deletion jobs run on schedule (daily or weekly).
- Deletion is audited with tamper-evident logs.
- GDPR deletion requests complete within 30 days.
- Backup rotation aligns with retention periods.
- Anonymization is verified as irreversible.
- Third-party DPAs include deletion obligations.

## Related

- `documentation/categories/compliance/soc2-type-ii-audit-preparation.md`
- `documentation/categories/compliance/dora-digital-operational-resilience.md`
- `documentation/categories/database/zero-downtime-schema-migrations.md`

## Source URLs (verified 2026-08-16)

- Data Retention Best Practices for GDPR Compliance 2026 — https://www.privasee.io/post/data-retention-best-practices
- Data Retention Policy Implementation Guide — https://www.enzuzo.com/blog/data-retention-policy
- Engineering Data Retention at Scale — https://engineeringblog.yelp.com/2022/04/data-retention-at-scale.html
- Data Retention Requirements by Regulation — https://www.varonis.com/blog/data-retention
