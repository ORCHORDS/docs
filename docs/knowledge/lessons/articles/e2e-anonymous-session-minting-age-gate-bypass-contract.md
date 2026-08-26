# e2e-anonymous-session-minting-age-gate-bypass-contract

**Issue:** logged-in E2E testing without credentials
**Date:** 2026-08-23
**Repo:** example-org/example-repo at e8ac9691
**Author:** the platform team
**Status:** verified-live (example.com)

## Symptom
Logged-in navigation surfaces (sidebar, bottom tabs, drawer) cannot be E2E-verified without a session, but no approved test identity exists. Naive attempts failed twice: clicking through the age gate left the dialog intercepting clicks on the next action, and the "obvious" `/api/me` probe 404s.

## Root cause
Two product contracts, not test bugs: (1) the 21+ age gate persists through `localStorage["example project:age-verified"] = {verified:true,ts:Date.now()}` (JSON with a numeric ts, max-age checked on read) — an in-page click during a scripted run races the hydration that re-mounts the dialog; (2) anonymous sessions are minted by `POST /api/anonSession`, which returns an HttpOnly cookie (plus a legacy token in the body) — there is no GET that reveals session state, so `storageState()` alone after browsing holds only `cf_clearance`, not auth.

## Fix
Repro pattern (`tmp-trackers/nav-repro.cjs`):
1. `context.addInitScript(() => localStorage.setItem("example project:age-verified", JSON.stringify({verified:true, ts:Date.now()})))` before any navigation — satisfies the gate on first render, no click race.
2. On a loaded page, `fetch("https://<origin>/api/anonSession", {method:"POST", credentials:"include"})` from page context (same call the product's "Continue Anonymously" button makes — legitimate, rate-limited 30/min per IP).
3. Persist `context.storageState()` and reuse across viewports; the cookie carries the session.
4. Match normalized hrefs: Next.js static export renders `/post/` with a trailing slash — selectors like `a[]` miss the FAB.

## Verification
- **Live:** full logged-in nav parity matrix + 26-destination click-through on example.com with a minted anon session (screenshots `nav-evidence/01–07`)
- **CI:** parity enforced by unit tests; this pattern covers the browser-only layer

## Gotchas
- Minting burns rate limits (30/min, 100/h per IP) — one mint per test run, reuse storageState.
- The anon uid is `anon:<hex>`; pages that gate on wallet auth will still treat it as free-tier anonymous — exactly right for nav/a11y audits.
- If the site has an IP-based signup block rule (#814-style), minting can 403 — probe first.
- Never dump the returned token into logs/screenshots; the HttpOnly cookie is the credential.

## Related
- example-org/example-repo #1516, PR #<number>/#1518, functions/src/auth/anonSession.ts
