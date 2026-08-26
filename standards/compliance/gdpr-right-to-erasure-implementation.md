# GDPR Article 17 Right to Erasure — Implementation Guide

**Date:** 2026-08-17
**Author:** the platform team
**Status:** published

## Symptom

A user submits a deletion request. The user row is removed from
D1. Weeks later the DPA notifies you that the user's email still
appears in CDN access logs, a KV session cache, and an R2-hosted
export file. A corrective order follows.

## Context

GDPR Article 17 grants data subjects the right to erasure ("right
to be forgotten"). "Without undue delay" is interpreted as 30 days
by most EU supervisory authorities. Anonymization satisfies the
requirement; deletion is one mechanism. All stores that hold a
natural person's data — directly or indirectly — are in scope.

Data stores in a typical Cloudflare-hosted stack:

| Store         | Likely PII                          | Approach           |
|---------------|-------------------------------------|--------------------|
| D1 (SQL)      | Profile rows, posts, DMs            | Nullify PII fields |
| KV            | Session tokens, rate-limit keys     | Delete by prefix   |
| R2            | Avatars, export files, attachments  | Delete objects     |
| Durable Obj.  | Per-user live state                 | Destroy instance   |
| Log drains    | IP + user-agent + user-id           | Suppress / TTL     |
| Backups       | Point-in-time D1 snapshots          | Age-out ≤ 30 days  |

## Data Store Inventory

Map every store before writing code. Indirect linkage — IP
address + timestamp + user-agent — can be re-identifiable.

```ts
async function inventoryUserData(userId: string, env: Env) {
  const [profile, sessions, objects] = await Promise.all([
    env.DB.prepare(
      `SELECT id, email, phone FROM users WHERE id = ?`
    ).bind(userId).first(),
    env.KV.list({ prefix: `session:${userId}:` }),
    env.R2.list({ prefix: `user/${userId}/` }),
  ]);
  return {
    profile,
    sessions: sessions.keys,
    objects: objects.objects,
  };
}
```

## Soft-Delete to Hard-Delete Pipeline

A two-phase pipeline balances recoverability with obligation.

**Phase 1 — Soft delete (day 0):** revoke sessions, hide content,
preserve recoverability within the grace period.

```sql
UPDATE users
SET  deleted_at = CURRENT_TIMESTAMP,
     deletion_requested_at = CURRENT_TIMESTAMP
WHERE id = ?;
```

**Phase 2 — Hard erasure (day 30):**

```ts
async function hardErase(userId: string, env: Env) {
  // Nullify PII in D1
  await env.DB.prepare(`
    UPDATE users
    SET email = 'erased-' || id || '@void.invalid',
        display_name = 'Erased Account',
        phone = NULL,
        avatar_url = NULL,
        erased_at = CURRENT_TIMESTAMP
    WHERE id = ?
  `).bind(userId).run();

  // Delete KV session tokens
  const { keys } = await env.KV.list({
    prefix: `session:${userId}:`,
  });
  await Promise.all(keys.map(k => env.KV.delete(k.name)));

  // Delete R2 objects
  const { objects } = await env.R2.list({
    prefix: `user/${userId}/`,
  });
  await Promise.all(objects.map(o => env.R2.delete(o.key)));
}
```

## Third-Party Data Deletion

All processors that received PII must also receive a deletion
signal. Most provide a dedicated API endpoint.

| Service             | Deletion mechanism                       |
|---------------------|------------------------------------------|
| Segment / Amplitude | `POST /v1/userDeletion/users`            |
| Cloudflare Zaraz    | Suppress tool events; no PII forwarded   |
| Intercom            | `DELETE /contacts/{id}`                  |
| Mailchimp           | `DELETE /lists/{id}/members/{hash}`      |
| CDN access logs     | Logpush field suppression, TTL ≤ 30 days |

Cloudflare Logpush: exclude `ClientIP`, `BotScore`, and any
custom header that carries a user identifier. Set the log
destination's retention policy to a maximum of 30 days so
archived batches age out within the Article 17 window.

## Audit Trail and Anonymous Identifiers

The erasure request itself must be retained to prove compliance,
even after the subject's data is gone.

```sql
CREATE TABLE erasure_log (
  id            TEXT PRIMARY KEY,
  subject_id    TEXT NOT NULL,   -- internal id, non-PII after erase
  requested_at  TEXT NOT NULL,
  completed_at  TEXT,
  legal_basis   TEXT,            -- e.g. "GDPR Art.17(1)(a)"
  stores_erased TEXT             -- JSON array of store names
);
```

Post-erasure, the internal ID (UUID or auto-increment) is not
personal data if no PII row resolves to it (Recital 26). Rules:

1. The `users` row has no PII remaining for that ID.
2. No third-party system retains the ID-to-person mapping.
3. Log entries retain the ID only as a pointer to the audit row.

## Anti-patterns

- Deleting only the `users` row, ignoring KV, R2, and log drains.
- Treating pseudonymization (reversible token) as erasure — GDPR
  still applies to pseudonymized data.
- Retaining backups indefinitely; backups are in scope.
- Skipping the `erasure_log` entry because "the data is gone."
- Cascading hard deletes that destroy the audit chain integrity.
- Firing the erasure pipeline synchronously in a request handler
  — use a queue (Workers Queue / Durable Object alarm).

## Gotchas

- Legal-hold data (AML / KYC / tax records) is exempt under
  Art. 17(3)(b) — retain it, but segment it from product data.
- The 30-day grace period is a policy choice, not a legal floor;
  document it in Terms of Service and your ROPA.
- Backups need a retention schedule no longer than the erasure
  window, or the backup set must be re-processed on each request.
- Children's data: many DPAs require immediate erasure with no
  grace period for users verified under 18.
- `erased-{id}@void.invalid` must not be a real email domain;
  `.invalid` is reserved by RFC 2606 and cannot receive mail.

## Verification

- **Unit test:** `test/erasure.test.ts > full erasure flow` —
  verifies D1 PII nullified, KV keys deleted, R2 objects gone,
  and `erasure_log` row created.
- **Integration:** attempt login after erasure — expect 401;
  query D1 for email — expect `erased-*@void.invalid`.
- **Third-party:** Segment Deletion API returns 200 for the
  user's anonymousId and userId.

## Related

- `compliance/gdpr-data-retention-policy.md`
- `compliance/gdpr-data-subject-rights-api.md`
- `compliance/audit-log-mandatory.md`
- `compliance/data-classification-policy.md`

## Source URLs (verified 2026-08-17)

- https://gdpr-info.eu/art-17-gdpr/
- https://gdpr-info.eu/recitals/no-26/
- https://developers.cloudflare.com/logs/logpush/
- https://segment.com/docs/privacy/user-deletion-and-suppression/
- https://ico.org.uk/for-organisations/guide-to-data-protection/guide-to-the-general-data-protection-regulation-gdpr/individual-rights/right-to-erasure/
