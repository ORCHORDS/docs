# gdpr-data-retention-policy

**Issue:** Defining and enforcing lawful data retention periods under GDPR Art. 5(1)(e) (storage limitation principle)
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
GDPR requires personal data to be kept "no longer than is necessary for the purposes for which the personal data are processed." Without an enforced retention schedule, data accumulates indefinitely, increasing breach impact, DSR scope, and regulatory exposure. Many SMB SaaS products have no automated deletion at all.

## Pattern / Solution
**Step 1 — Data inventory and classification**

Map every data store to a retention category:

| Category | Example data | Retention | Legal basis |
|---|---|---|---|
| Account data | Name, email | Duration of contract + 90 days | Contract (Art. 6(1)(b)) |
| Billing records | Invoices, amounts | 7 years | Legal obligation (Art. 6(1)(c)) |
| Activity logs | API call logs | 90 days | Legitimate interest |
| Support tickets | Messages, attachments | 3 years after closure | Legitimate interest |
| Marketing data | Email opens, clicks | Until consent withdrawn | Consent (Art. 6(1)(a)) |
| Backup copies | Full DB snapshots | 30-day rolling window | Operational necessity |

**Step 2 — Automated purge jobs**

```python
# Run nightly
def purge_expired_records():
    cutoffs = {
        "activity_logs":  datetime.now() - timedelta(days=90),
        "support_tickets": datetime.now() - timedelta(days=3*365),
        "marketing_data":  None,  # event-driven via consent withdrawal
    }
    for table, cutoff in cutoffs.items():
        if cutoff:
            rows = db.execute(
                f"DELETE FROM {table} WHERE created_at < %s RETURNING id",
                (cutoff,)
            )
            audit_log(f"purged {rows.rowcount} rows from {table}")
```

**Step 3 — Backup purge alignment**

Document that backups older than the rolling window are destroyed per schedule. Include this in DSR responses when relevant.

**Step 4 — Retention schedule as a versioned artifact**

Store the retention schedule in version control. Reference the current version in your privacy notice and DPA. Update it whenever a new data category is added.

## Gotchas
- Anonymisation is a valid alternative to deletion — but it must be irreversible. Pseudonymisation is not enough; the data remains personal.
- Financial records often have mandatory minimum retention under local tax law that overrides the GDPR minimisation principle.
- Deleting from primary DB does not delete from read replicas, caches, search indexes, or analytics warehouses — all must be included in the purge sweep.
- "Archiving in the public interest" and "scientific research" purposes allow longer retention with appropriate safeguards; do not use them as a blanket exemption.
- Communicate retention periods clearly in your privacy notice — vague terms like "as long as necessary" are increasingly rejected by DPAs.

## Related
- `gdpr-data-subject-rights-api.md`
- `gdpr-consent-management.md`
- `data-classification-policy.md`
- `audit-log-mandatory.md`
