# gdpr-article-17-erasure

**Issue:** Right to erasure (Article 17) — implementation gotchas
**Date:** 2026-08-09
**Status:** documented

## Symptom
A user in the EU requests account deletion. You delete the user
row. The audit log still references them. The backups still have
the data. The user complains to the DPA. You're fined.

## Root cause
GDPR Article 17 ("right to erasure" or "right to be forgotten")
requires erasure of personal data "without undue delay." But:
- **Audit logs** are records of the user's actions, not the user's
  data per se. Erasing them breaks the chain.
- **Backups** are snapshots; you can't selectively delete from a
  backup.
- **Anonymized data** is NOT personal data (recital 26: "data ...
  rendered anonymous ... should not be considered personal data").

**Source:** GDPR Article 17:
https://gdpr-info.eu/art-17-gdpr/

> "The data subject shall have the right to obtain from the
> controller the erasure of personal data concerning him or her
> without undue delay."

The exceptions (Article 17(3)) include:
- Compliance with a legal obligation
- Public interest in public health
- Archiving purposes in the public interest, scientific/historical
  research, or statistical purposes
- Establishment, exercise, or defence of legal claims

For most social platforms, the audit log is a "legal obligation"
(KYC, AML, financial records) — so it CAN be retained. But it
must be **anonymized** (the user's PII removed).

## Fix
Three-phase erasure:

### Phase 1: Soft delete (immediate)
```ts
// Mark as deleted, revoke sessions, invalidate auth
await env.DB.prepare(
  `UPDATE users SET deleted_at = ? WHERE id = ?`
).bind(now, userId).run();
await env.DB.prepare(
  `UPDATE sessions SET revoked_at = ? WHERE user_id = ? AND revoked_at IS NULL`
).bind(now, userId).run();
```

User can no longer log in. Their content is hidden from public
view (render-time check for `deleted_at IS NOT NULL`).

### Phase 2: Erasure (after 30-day grace)
```ts
// Null PII fields, preserve structural data for audit chain
await env.DB.prepare(
  `UPDATE users
   SET email = 'redacted-' || id || '@erased.local',
       display_name = 'Erased User',
       avatar_url = NULL,
       phone = NULL,
       oauth_id = NULL,
       erasure_at = ?
   WHERE id = ?`
).bind(now, userId).run();

// Anonymize the user's authored content (audit chain preserved)
await env.DB.prepare(
  `UPDATE posts SET author_display_name = 'Erased User', author_avatar_url = NULL
   WHERE user_id = ?`
).bind(userId).run();
```

### Phase 3: Audit log anonymization (after 90 days)
```ts
// Anonymize user references in audit metadata (keep the chain)
await env.DB.prepare(
  `UPDATE audit_log
   SET actor_id = 'erased-user',
       after_state = REPLACE(after_state, ?, '"actor_display_name":"Erased User"')
   WHERE actor_id = ?`
).bind(userId, userId).run();
```

The audit log row ID is preserved; the user_id is replaced with
a non-personal reference. The Merkle chain remains intact (you
didn't re-write any chain rows).

## What you CANNOT erase

- **The audit log row itself** (record of the erasure request,
  including the user's request timestamp — needed for compliance
  proof)
- **Backup copies older than your retention window** (they will
  age out automatically)
- **Financial transaction records** (tax law, AML law, etc.)
  — these have their own retention requirements (5-10 years)

## Verification
- **Test:** `test/gdpr-erasure.test.ts > complete erasure flow
  preserves audit chain` — passes
- **Live:** Erasure requests complete in <30 days (DPA-friendly)
- **Pen test:** Annual third-party GDPR review confirms Article 17
  compliance

## Gotchas
- **30-day grace is a UX choice, not legal.** Some apps use 7
  days, some 90. Document the choice in your T&S policy.
- **Public posts authored by the user** are a gray area. Some
  legal opinions say "they're still speech in the public record";
  others say "the user is the data subject, erase the data."
  Consult a lawyer for your jurisdiction.
- **The erasure date itself is audit data** and is kept.
- **Anonymized ≠ pseudonymized.** Anonymized data has no
  identifier back to the user; pseudonymized data has a token
  that could be reversed with a lookup table. GDPR applies to
  pseudonymized data; only true anonymization is out of scope.
- **Children's data** has a shorter timeline (most jurisdictions:
  erase immediately on request, no grace period).

## Related
- `soft-delete-pattern.md` (the technical pattern)
- `audit-chain-durable-object.md` (the audit chain)
- `compliance/region-matrix.md` (where GDPR applies)
- GDPR Article 17: https://gdpr-info.eu/art-17-gdpr/
- Recital 26 (anonymization): https://gdpr-info.eu/recitals/no-26/
