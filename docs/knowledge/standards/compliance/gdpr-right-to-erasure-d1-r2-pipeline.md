# GDPR Right to Erasure — Cascade Deletion Pipeline Across D1 and R2

**Project:** example project (example.com) — 21+ anonymous social platform
**Author:** example.com
**Scope:** EU/US users, GDPR Article 17, Cloudflare D1 + R2 deletion pipeline, mobile UX
**Last reviewed:** 2025-08

---

## 1. Regulatory Basis

GDPR Article 17 grants data subjects the **right to erasure** ("right to be forgotten") in
circumstances including: withdrawal of consent, objection under Article 21, unlawful processing,
or the data is no longer necessary for its original purpose.

For example project, the most common triggers are:
1. User deletes their account.
2. User withdraws consent previously given as the lawful basis.
3. Regulatory or judicial erasure order.

Article 17(3) exempts certain processing from the erasure duty, including:
- Freedom of expression and information (Art. 17(3)(a)) — relevant for user-generated public posts
  in some analyses, but less applicable for a private social platform.
- Compliance with a legal obligation (Art. 17(3)(b)) — e.g., DMCA hold, fraud investigation.
- Establishment, exercise, or defence of legal claims (Art. 17(3)(e)).

An anonymisation approach — replacing personal data with irreversible pseudonyms — satisfies
Article 17 where full deletion is technically infeasible without breaking referential integrity.
EDPB Guidelines 05/2014 confirm anonymised data is outside GDPR scope.

---

## 2. Data Inventory Before Building the Pipeline

Before writing deletion Workers, map every location where user data resides:

| Store              | Data types                                         | Deletion method            |
|--------------------|----------------------------------------------------|----------------------------|
| D1: `users`        | email hash, session token, profile fields          | Hard delete row            |
| D1: `posts`        | content text, media refs, metadata                 | Tombstone (content cleared)|
| D1: `consent_audit`| consent records (pseudonymous)                    | Retain (legal obligation)  |
| D1: `dmca_notices` | if user is claimant or subject                     | Retain if active legal hold|
| D1: `age_verify`   | verification method, timestamp                     | Hard delete row            |
| R2: `uploads/live` | user-uploaded media (images, video, audio)         | Object delete              |
| R2: `uploads/raw`  | pre-publish originals                              | Object delete              |
| R2: `wam-quarantine`| DMCA-held media                                  | Retain during dispute      |
| KV: `consent:{id}` | TCF consent record                                 | KV delete                  |
| KV: `age_verified` | age verification token                             | KV delete                  |
| KV: `session:{id}` | session data                                       | KV delete                  |
| Edge cache         | CDN-cached public profile assets                   | Cache purge via API        |

---

## 3. Deletion Pipeline Architecture

The pipeline is orchestrated by a single **Deletion Worker** that receives an erasure request,
validates it, creates a Durable Object job record, and fans out to sub-tasks.

```
User / Admin API → Deletion Worker
                        │
                        ▼
              D1: erasure_requests (create record, status = 'queued')
                        │
              ┌─────────┼──────────────────────┐
              ▼         ▼                      ▼
        D1 sub-task  R2 sub-task           KV sub-task
        (clear PII   (delete all           (delete all
        in tables)   media objects)        KV entries)
              │         │                      │
              └─────────┼──────────────────────┘
                        ▼
              D1: erasure_requests (status = 'completed', completed_at)
              D1: erasure_audit (append-only tombstone)
                        │
                        ▼
              Notify user (if email not yet erased)
              Purge CDN edge cache
```

### 3.1 Erasure Request Validation

Before executing any deletion, validate:

```typescript
async function validateErasureRequest(
  env: Env,
  userId: string,
  requestorId: string,
  requestSource: 'user-self' | 'admin' | 'dsar-api'
): Promise<{ valid: boolean; reason?: string }> {
  if (requestSource === 'user-self' && userId !== requestorId) {
    return { valid: false, reason: 'requestor-mismatch' };
  }

  // Check for active legal hold (DMCA, fraud investigation, court order)
  const hold = await env.D1.prepare(
    'SELECT id FROM legal_holds WHERE user_id = ? AND lifted_at IS NULL LIMIT 1'
  ).bind(userId).first();

  if (hold) {
    return { valid: false, reason: 'legal-hold-active' };
  }

  return { valid: true };
}
```

### 3.2 D1 Deletion Worker

```typescript
async function erasePiiFromD1(env: Env, userId: string, jobId: string): Promise<void> {
  // 1. Tombstone user profile (retain pseudonymous ID for referential integrity)
  await env.D1.prepare(`
    UPDATE users SET
      email_hash    = NULL,
      display_name  = '[deleted]',
      bio           = NULL,
      avatar_r2_key = NULL,
      deleted_at    = datetime('now'),
      deletion_job  = ?
    WHERE id = ?
  `).bind(jobId, userId).run();

  // 2. Clear post content but retain tombstone rows for thread continuity
  await env.D1.prepare(`
    UPDATE posts SET
      body          = '[removed]',
      media_r2_key  = NULL,
      deleted_at    = datetime('now'),
      deletion_job  = ?
    WHERE uploader_id = ?
      AND deleted_at IS NULL
  `).bind(jobId, userId).run();

  // 3. Hard-delete rows that serve no referential or legal purpose
  await env.D1.prepare('DELETE FROM age_verify WHERE user_id = ?').bind(userId).run();
  await env.D1.prepare('DELETE FROM push_tokens WHERE user_id = ?').bind(userId).run();
  await env.D1.prepare('DELETE FROM user_sessions WHERE user_id = ?').bind(userId).run();

  // 4. Retain consent_audit (legal obligation — proof of consent)
  // Retain dmca_notices if user was subject of active notice
  // These are explicitly NOT deleted.
}
```

### 3.3 R2 Deletion Worker

List and delete all R2 objects belonging to the user. R2 does not support user-scoped queries
natively — maintain a D1 index of R2 keys per user.

```typescript
async function eraseR2Objects(env: Env, userId: string, jobId: string): Promise<void> {
  // Fetch all R2 keys belonging to this user from D1 index
  const rows = await env.D1.prepare(
    'SELECT r2_key, bucket FROM r2_object_index WHERE user_id = ? AND deleted_at IS NULL'
  ).bind(userId).all();

  for (const row of rows.results as { r2_key: string; bucket: string }[]) {
    if (row.bucket === 'quarantine') {
      // Do not delete quarantined content — may be under DMCA hold
      continue;
    }

    const bucket = row.bucket === 'live' ? env.R2_LIVE : env.R2_RAW;
    await bucket.delete(row.r2_key);

    await env.D1.prepare(`
      UPDATE r2_object_index SET deleted_at = datetime('now'), deletion_job = ?
      WHERE r2_key = ? AND user_id = ?
    `).bind(jobId, row.r2_key, userId).run();
  }
}
```

### 3.4 KV Deletion Worker

```typescript
async function eraseKvEntries(env: Env, userId: string, sessionIds: string[]): Promise<void> {
  // Delete consent record
  await env.CONSENT_KV.delete(`consent:${userId}`);

  // Delete all known session entries
  for (const sid of sessionIds) {
    await env.AGE_GATE_KV.delete(`age_verified:${sid}`);
    await env.SESSION_KV.delete(`session:${sid}`);
  }

  // Note: KV does not support prefix scans efficiently.
  // Maintain a D1 table (kv_key_index) listing all KV keys per user.
}
```

### 3.5 CDN Cache Purge

After D1 and R2 deletion, purge any cached profile or media URLs:

```typescript
async function purgeCdnCache(env: Env, userId: string): Promise<void> {
  const urls = await getPublicUrlsForUser(env, userId); // fetch from D1 before erasure
  const response = await fetch(
    `https://api.cloudflare.com/client/v4/zones/${env.CF_ZONE_ID}/purge_cache`,
    {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${env.CF_API_TOKEN}`,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ files: urls }),
    }
  );
  if (!response.ok) {
    throw new Error(`CDN purge failed: ${response.status}`);
  }
}
```

---

## 4. Audit Log Tombstones

GDPR Article 17 requires the platform to demonstrate erasure occurred. Maintain an append-only
audit log in D1 that cannot be modified after insertion.

```sql
CREATE TABLE erasure_audit (
  id              TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
  job_id          TEXT NOT NULL,
  user_id         TEXT NOT NULL,           -- pseudonymous; retained post-erasure as proof
  requestor       TEXT NOT NULL,           -- 'user-self' | 'admin' | 'dsar-api'
  request_source  TEXT NOT NULL,
  requested_at    TEXT NOT NULL,
  d1_completed_at TEXT,
  r2_completed_at TEXT,
  kv_completed_at TEXT,
  cdn_purged_at   TEXT,
  completed_at    TEXT,
  failure_reason  TEXT,
  retained_data   TEXT NOT NULL DEFAULT '[]' -- JSON list of retained tables/reasons
);

-- This table must NEVER have an UPDATE or DELETE applied to it.
-- Enforce via D1 row-level triggers when available, or application-layer policy.
```

The `retained_data` field explains any lawful retention exceptions, e.g.:
```json
[
  { "table": "consent_audit", "reason": "GDPR Art. 7 proof of consent" },
  { "table": "dmca_notices", "reason": "DMCA 512 legal claim — notice active" }
]
```

---

## 5. Handling Partial Failures

The pipeline must be idempotent. If a sub-task fails, it should be retryable without re-deleting
already-deleted data.

```typescript
async function runErasurePipeline(env: Env, jobId: string, userId: string): Promise<void> {
  const job = await getJob(env, jobId);

  if (!job.d1_completed_at) {
    await erasePiiFromD1(env, userId, jobId);
    await markJobStep(env, jobId, 'd1_completed_at');
  }

  if (!job.r2_completed_at) {
    await eraseR2Objects(env, userId, jobId);
    await markJobStep(env, jobId, 'r2_completed_at');
  }

  if (!job.kv_completed_at) {
    const sessionIds = await getSessionIds(env, userId); // D1 query before D1 erase
    await eraseKvEntries(env, userId, sessionIds);
    await markJobStep(env, jobId, 'kv_completed_at');
  }

  if (!job.cdn_purged_at) {
    await purgeCdnCache(env, userId);
    await markJobStep(env, jobId, 'cdn_purged_at');
  }

  await markJobComplete(env, jobId);
}
```

---

## 6. SLA and Timing

GDPR Article 12(3) requires the controller to act on an erasure request **without undue delay
and at the latest within one month** of receipt, extendable by two further months where necessary
due to complexity.

For example project:
- **Target SLA**: complete deletion within 72 hours of verified request.
- **Legal hold deferral**: notify user within 30 days if erasure is deferred due to a legal hold,
  explaining the legal basis and expected duration.
- **Confirmation**: send a deletion confirmation to the user's last known contact (email or
  in-app notification) upon completion.

---

## 7. Mobile-Initiated Deletion UX

### 7.1 In-App Flow

The mobile app must provide a clear, accessible deletion path per GDPR Article 7(3):

```
Settings → Privacy → Delete Account
  │
  ├── Explain what will be deleted (content, profile, media)
  ├── Explain what will be retained (legal holds, anonymised analytics)
  ├── Offer data export (Art. 20 portability) before deletion
  ├── Require re-authentication (biometric or password) to confirm
  └── Submit deletion request → API POST /api/user/delete
```

### 7.2 Pending State UX

After submitting the request:
- App displays a "Deletion in progress" state with estimated completion time.
- User is logged out immediately.
- App polls `GET /api/user/deletion-status` (unauthenticated, using a deletion token issued
  at request time) to show progress.
- On completion: app shows confirmation screen and clears all local storage.

### 7.3 Mobile Local Data Clearing

The app must also clear locally-stored data on deletion:
- Keychain entries (tokens, session IDs)
- Local SQLite / Core Data cache
- Push notification token (deregister from APNs/FCM before server-side deletion)
- Cached media files in the app's document directory

---

## 8. Checklist

- [ ] Data inventory completed — all user data locations mapped
- [ ] Legal hold check before any erasure execution
- [ ] D1 PII tombstoning (content cleared, row retained for referential integrity)
- [ ] D1 hard-delete for rows with no referential or legal purpose
- [ ] R2 object deletion for all live/raw buckets; quarantine objects skipped if under hold
- [ ] KV entry deletion for consent, session, and age-verification records
- [ ] CDN cache purge after content removed from R2
- [ ] Append-only `erasure_audit` table with retained-data JSON field
- [ ] Idempotent pipeline with per-step completion flags
- [ ] 72-hour SLA target; 30-day maximum per GDPR Art. 12(3)
- [ ] Mobile UI: re-authentication gate before deletion confirmed
- [ ] Mobile: local keychain, cache, and push token cleared on deletion
- [ ] Data portability export offered before deletion (GDPR Art. 20)
- [ ] Consent audit records explicitly retained (legal obligation exemption documented)

---

## 9. References

- GDPR Articles 5, 12, 17, 20, 21
- EDPB Guidelines 05/2018 on the Right to Erasure
- EDPB Guidelines 01/2022 on Data Subject Rights (Art. 15–22)
- Cloudflare D1 — SQL API and batch statements
- Cloudflare R2 — Object delete and list operations
- Cloudflare KV — Key expiry and delete operations
- Cloudflare Cache Purge API — `/zones/{id}/purge_cache`
- ICO Guidance on the Right to Erasure (UK GDPR)
