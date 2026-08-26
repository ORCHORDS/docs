# example project-audit-2026-08

**Issue:** Lessons from example project August 2026 codebase audit (30 findings, 12 PRs)
**Date:** 2026-08-09
**Repo:** example-org/example-repo at e2557bf7
**Author:** the platform team
**Status:** verified-live

## Symptom
Full codebase audit of a Cloudflare Workers + Next.js social platform revealed 30 findings across security, infrastructure, accessibility, and correctness. All resolved in a single audit sprint.

## Root cause
Rapid feature development without periodic security review. Multiple classes of bugs accumulated over months.

## Lessons Learned

### L1: timingSafeEqual length leak
`timingSafeEqual(a, b)` with an early `if (a.length !== b.length) return false` leaks the secret's length via timing side-channel. An attacker controlling one input can binary-search for the secret's length by measuring response time. Fix: pad both inputs to the same length via double-HMAC before comparing, so the comparison always runs in constant time regardless of input lengths. (PRs #1201, #1202)

### L2: Silent .catch(() => {}) hides production bugs
61 instances of `.catch(() => {})` across 24 backend files meant errors in push notifications, audit logging, R2 deletion, rate-limit recording, and badge cache invalidation were completely invisible. Fix: replace every silent catch with `.catch((err) => { console.error("[tag]", err); })` using descriptive tags per call site. (PR #<number>)

### L3: SELECT * leaks sensitive columns
`SELECT *` in data export endpoints leaked `passwordHash`, `twoFactorSecret`, `twoFactorBackupCodes`, biometric face-detection columns (`detectedFaces`, `faceCount`, `faceScannedAt`, `facesCleared`), and payment references. Fix: explicit column allowlists in every SELECT used for user-facing data. (PRs #1143, #1197)

### L4: Double /api/ prefix from client-side fetch
When frontend code constructs URLs as `${WORKER_URL}/api/endpoint` but WORKER_URL already includes `/api`, the actual request hits `/api/api/endpoint`. This was happening in 21+ frontend components. Fix: deduplicate WORKER_URL into a shared module and strip trailing `/api` if present. (PR #<number>)

### L5: postMessage wildcard origin
`postMessage(data, "*")` in iframe embed components broadcasts data to any parent frame, enabling data exfiltration via malicious embedding. Fix: derive target origin from `document.referrer` with `"*"` fallback only when referrer is empty. (PR #<number>)

### L6: localStorage-based API URL override enables XSS hijack
Allowing `localStorage` or `window.__example project_WORKER__` to override the API base URL means an XSS payload can redirect all API calls to an attacker-controlled server. Fix: API base URL exclusively from build-time env vars, never runtime-overridable. (PR #<number>)

### L7: Deploy gate checking single workflow
A deployment gate job that only verified one CI workflow (not all required ones) allowed deploys to proceed while other checks were still failing. Fix: gate verifies ALL required workflows passed on the same HEAD SHA. (PR #<number>)

### L8: Duplicate migration steps race against the same DB
Two deploy workflows (admin + functions) both ran D1 migrations, racing against the same database. Fix: single migration owner (deploy-functions), admin deploy removes its migration step. (PR #<number>)

### L9: SQL injection via string interpolation in LIMIT/OFFSET
Admin endpoints interpolated LIMIT/OFFSET values directly into SQL strings instead of using bound parameters. Fix: always use `.bind()` for any user-supplied value, even numeric ones. (PR #<number>)

### L10: Public endpoint auto-creates user rows
Public profile endpoint auto-created user rows for any arbitrary UID, allowing an attacker to pre-register UIDs. Fix: unknown UIDs return 404, no auto-create. (PR #<number>)

### L11: IDOR on order endpoints
Store order public endpoint had no auth and no owner check — anyone with an order ID could view full order details including line items. Fix: require auth + owner check (or guest order token). (PR #<number>)

### L12: GDPR data export unbounded queries
24+ SELECT queries in data export had no LIMIT clause — a user with millions of records could OOM the Worker. Fix: add LIMIT + truncation indicators to all export queries. (PR #<number>)

### L13: CI using --no-frozen-lockfile
All CI jobs used `pnpm install --no-frozen-lockfile`, allowing lockfile drift to pass CI silently. Fix: `--frozen-lockfile` in CI, `--no-frozen-lockfile` only in dev. (PR #<number>)

### L14: env.DB.batch() bundler bug (D1)
Cloudflare Pages Functions bundler (esbuild + Wrangler 4.x) silently strips the SQL field from D1PreparedStatement arguments to batch(). The batch executes with empty statements and silently no-ops. 48 call sites affected across money paths, referrals, store, user data. Fix: replace batch() with sequential .run() calls. (Issues #1151-#1196)

## Verification
- **CI:** All 12 PRs merged with green CI
- **Live:** Production deployment successful
- **Audit:** 30/30 findings resolved, tracked in #1141

## Gotchas
- The D1 batch() bug is specific to CF Pages Functions bundler, not Workers in general
- timingSafeEqual fixes must use double-HMAC, not just padding to max length
- Silent .catch() is the #1 source of invisible production bugs — log or don't catch
- SELECT * should never be used for user-facing data, even in internal APIs

## Related
- `cloudflare/d1-batch-bundler-bug.md`
- `security/owasp-top-10-2025.md`
- `security/owasp-api-top-10-2023.md`
- `patterns/feature-cookbook-rate-limiting.md`
