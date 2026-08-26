# select-star-data-leak

**Issue:** SELECT * in user-facing endpoints leaks sensitive columns
**Date:** 2026-08-09
**Repo:** example-org/example-repo at 72d0ff5e
**Author:** the platform team
**Status:** fixed (72d0ff5e, b8b0615b)

## Symptom
GDPR data export endpoint returned `passwordHash`, `twoFactorSecret`, `twoFactorBackupCodes`, biometric face-detection columns (`detectedFaces`, `faceCount`, `faceScannedAt`, `facesCleared`), and raw `paymentRef` strings from payment providers.

## Root cause
`SELECT * FROM posts` and `SELECT * FROM store_orders` in user-facing data export handlers. When new sensitive columns were added to the schema (biometrics, 2FA secrets), the export automatically included them because `SELECT *` returns everything.

## Fix
Explicit column allowlists for every user-facing SELECT:

```ts
// BEFORE
const { results } = await env.DB.prepare('SELECT * FROM posts WHERE uid = ?1').bind(uid).all();

// AFTER
const { results } = await env.DB.prepare(
  `SELECT id, title, body, createdAt, updatedAt, visibility, mediaUrl
   FROM posts WHERE uid = ?1 LIMIT ?2`
).bind(uid, limit).all<PostExportRow>();
```

## Verification
- **Test:** Data export response does not contain passwordHash, twoFactorSecret, detectedFaces, faceCount, faceScannedAt, facesCleared
- **CI:** PRs #1143, #1197 green

## Gotchas
- `SELECT *` is safe for internal/admin queries but NEVER for user-facing endpoints
- Adding a column to a table silently adds it to all `SELECT *` queries — no code change triggers a review
- Row-level typing (e.g. `D1Result<PostExportRow>`) helps catch this at compile time — the type won't have the sensitive columns
- GDPR exports specifically should NEVER include authentication secrets, even if the user "owns" them

## Related
- `lessons/example project-audit-2026-08.md`
- `security/owasp-api-top-10-2023.md` (Broken Object Property Level Authorization)
