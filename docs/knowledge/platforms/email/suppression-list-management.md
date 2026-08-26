# suppression-list-management

**Issue:** Maintaining a central suppression list to prevent sending to opted-out or bounced addresses
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Different teams or services send to the same address after an unsubscribe or hard bounce because suppression data is siloed.

## Pattern / Solution
Central suppression table schema:
```sql
CREATE TABLE suppressions (
  id          BIGSERIAL PRIMARY KEY,
  email       TEXT NOT NULL,
  email_hash  TEXT GENERATED ALWAYS AS (encode(sha256(lower(email)::bytea), 'hex')) STORED,
  reason      TEXT NOT NULL, -- 'hard_bounce', 'soft_bounce_max', 'complaint', 'unsubscribe', 'manual'
  source      TEXT,          -- 'sendgrid_webhook', 'user_request', 'admin'
  created_at  TIMESTAMPTZ DEFAULT now(),
  expires_at  TIMESTAMPTZ    -- NULL = permanent
);
CREATE UNIQUE INDEX ON suppressions (lower(email));
CREATE INDEX ON suppressions (email_hash);
```

Pre-send check:
```python
def is_suppressed(email: str, db) -> bool:
    return db.execute(
        "SELECT 1 FROM suppressions WHERE lower(email) = lower(%s) AND (expires_at IS NULL OR expires_at > now())",
        (email,)
    ).fetchone() is not None
```

Sync with ESP suppressions:
- Pull from SendGrid global unsubscribes API daily
- Pull from AWS SES suppression list daily
- Push your list to each ESP to avoid double-sending

## Gotchas
- Email addresses should be stored lowercased or compared case-insensitively; `User@Domain.com` and `user@domain.com` are the same mailbox
- Store the hash alongside the plaintext if you need to match FBL reports that only provide hashed addresses
- Suppression lists should be shared across all sending domains and services in your organization

## Related
- `bounce-handling-hard-soft.md`
- `complaint-rate-monitoring.md`
- `unsubscribe-handling-rfc.md`
