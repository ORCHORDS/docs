# Cloudflare Pages Build Cache Stale Dependency Incident

Date: 2026-08-23 / Author: example.com / Status: production

---

## Incident Summary

On 2026-05-19 a Cloudflare Pages deployment of the marketing site shipped a broken
search widget to production. The widget had been patched in `package.json` two days
earlier to pin a dependency (`@algolia/autocomplete-js`) away from a broken `4.8.3`
release. The Pages build cache restored `node_modules` from a snapshot taken before
the pin, and the lockfile divergence check was not enforced on cache restore. Users
saw a JavaScript exception on every search interaction for 6 hours before the broken
build was detected and a cache-busting redeploy triggered.

---

## Context

- Cloudflare Pages project: `marketing-site` (Next.js 14, pnpm 9)
- Affected dependency: `@algolia/autocomplete-js@4.8.3` (broken upstream release)
- Correct pinned version: `@algolia/autocomplete-js@4.8.2`
- Build cache: enabled, keyed on `pnpm-lock.yaml` hash (at the time of the incident)
- Pages build minutes consumed by the stale-cache build: 2 min 11 sec (fast, because
  `node_modules` restored entirely from cache)
- Time to user-visible breakage: immediate on deployment
- Time to detection: 6 hours (low-traffic weekend)

---

## Timeline

**2026-05-17 14:00 UTC** — Team pins `@algolia/autocomplete-js` to `4.8.2` in
`package.json` to avoid the broken `4.8.3` release. `pnpm-lock.yaml` updated and
committed. A manual local build confirms the fix. PR merged.

**2026-05-17 14:10 UTC** — Pages deploys the fix successfully. Cache snapshot at this
point correctly contains `4.8.2`.

**2026-05-18 09:30 UTC** — An unrelated content-only commit triggers a Pages build.
Cache is restored from the 2026-05-17 14:10 snapshot. Build completes in 2 min 11 sec.
Deployment is green. **No problem yet** — cache was taken after the pin was in place.

**2026-05-18 23:45 UTC** — A Pages infrastructure cache eviction rotates the build
cache bucket for the project, removing the post-pin snapshot. The new cache baseline
is rebuilt from the pre-pin snapshot stored in a secondary cache tier. (This is the
unobserved event that set up the incident.)

**2026-05-19 08:12 UTC** — A routine copy-update commit triggers a Pages build. The
build cache restores `node_modules` from the pre-pin baseline (which contains
`4.8.3`). The lockfile hash comparison passes because the cache key is computed
from the lockfile path, not the lockfile content hash, due to a Pages project
configuration bug (see Root Cause below).

**2026-05-19 08:17 UTC** — Deployment succeeds. `4.8.3` is live.

**2026-05-19 14:22 UTC** — First user error report via support email. Engineer
investigates, identifies the `4.8.3` regression in browser console logs.

**2026-05-19 14:31 UTC** — Engineer triggers a cache-purge redeploy
(`Clear build cache and retry`) from the Pages dashboard.

**2026-05-19 14:38 UTC** — Clean build installs `4.8.2` from lockfile. Deployment
succeeds. Search widget works correctly.

---

## Root Cause

The Pages project had been created in early 2025 when the pnpm cache key was
configured as a path glob (`pnpm-lock.yaml`) rather than a content hash. A subsequent
Pages platform update changed the default cache key strategy to use SHA-256 of the
lockfile content, but **existing projects were not migrated** — they retained their
old path-glob cache keys.

The path-glob key matched any build that had a `pnpm-lock.yaml` file present, meaning
the cache was always considered valid regardless of lockfile content. When the
secondary cache tier replayed a pre-pin baseline, the stale `node_modules` were
restored without any mismatch being detected.

Secondary root cause: There was no post-install verification step (e.g., `pnpm ls
@algolia/autocomplete-js` checked against an expected version) in the Pages build
configuration.

---

## Fix (Immediate)

From the Pages dashboard:

1. Navigate to the project → Settings → Builds & deployments.
2. Click **Clear build cache**.
3. Trigger a new deployment.

The clean build ran `pnpm install` from scratch, resolving exactly the versions in the
lockfile, and installed `4.8.2`.

---

## Fix (Structural)

### 1. Migrate cache key to content hash

In `wrangler.toml` (or Pages build settings), set the cache key explicitly:

```toml
[build]
cache_dir = "node_modules"
# Content hash of the lockfile, not path match
```

Until Pages exposes explicit cache-key configuration, use a build script wrapper that
includes a `node_modules/.cache-manifest` file containing the lockfile SHA:

```bash
# build-with-cache-check.sh
EXPECTED_HASH=$(sha256sum pnpm-lock.yaml | awk '{print $1}')
ACTUAL_HASH=$(cat node_modules/.lockfile-hash 2>/dev/null || echo "")

if [ "$EXPECTED_HASH" != "$ACTUAL_HASH" ]; then
  rm -rf node_modules
  pnpm install --frozen-lockfile
  echo "$EXPECTED_HASH" > node_modules/.lockfile-hash
fi
```

### 2. Add a post-install version assertion for critical dependencies

```bash
# In your Pages build command:
pnpm install --frozen-lockfile
INSTALLED=$(pnpm ls @algolia/autocomplete-js --json | jq -r '.[0].dependencies["@algolia/autocomplete-js"].version')
EXPECTED="4.8.2"
if [ "$INSTALLED" != "$EXPECTED" ]; then
  echo "ERROR: expected $EXPECTED but found $INSTALLED"
  exit 1
fi
```

### 3. Always use `--frozen-lockfile` (`--ci` for npm, `--frozen-lockfile` for pnpm)

This causes the installer to fail if the lockfile and `package.json` diverge, rather
than silently resolving a different version. If the cache has pre-install state,
`--frozen-lockfile` will still run and revalidate against the lockfile on first use.

---

## Prevention

- **Audit Pages projects created before 2025-Q3 for legacy path-glob cache keys.**
  Older projects may be silently using path-match cache strategies.
- **Treat dependency pins as critical-path changes.** After pinning a dependency,
  add a regression test or build assertion that checks the exact installed version.
- **Do not rely on build cache correctness alone for security or stability pins.**
  The cache can be evicted, replayed, or stale; the installed version must be verified
  at build time.
- **Enable Dependabot or Renovate alerts** for the pinned range so that when the
  upstream broken release is eventually yanked or superseded, the pin can be lifted
  with a clear signal.

---

## Anti-patterns

- **Assuming Pages build cache is always consistent with the current lockfile:** Cache
  eviction, secondary tier replays, and legacy cache key strategies can all introduce
  staleness.
- **Path-glob cache keys without content-hash fallback:** A file existing at a path
  is not the same as that file having a specific content.
- **Security/stability pins with no verification step:** The pin in `package.json` is
  intent; what matters is what was actually installed.
- **Low-traffic deployments as health checks:** A deployment passing Pages health
  checks does not mean user-visible functionality works. Browser-layer JS errors
  require real user monitoring or synthetic tests with browser execution.

---

## Gotchas

- Pages "Clear build cache" from the dashboard is a soft clear — it marks the current
  cache for eviction but does not guarantee the secondary tier is also cleared
  immediately. If the first redeploy after clearing still shows old dependencies,
  trigger a second manual deploy.
- `pnpm install --frozen-lockfile` will fail if `package.json` changes that are not
  reflected in the lockfile exist (e.g., a manual `package.json` edit without running
  `pnpm install` locally). This is the correct behaviour — do not disable it.
- Pages build logs show "Restored cache" as a single line with no content-hash
  verification detail. You cannot tell from the log whether the restored cache matches
  the current lockfile without adding your own verification step.
- Cache keys in Pages are per-project, not per-branch. A cache poisoned on the main
  branch may affect preview deployments from feature branches.

---

## Verification

1. After deploying the structural fix, trigger a build and confirm the build log
   shows `pnpm install` running (not "All packages are up-to-date").
2. Add a Pages integration test that checks `window.__ALGOLIA_AUTOCOMPLETE_VERSION__`
   (or equivalent) matches the expected pinned value.
3. Run a synthetic monitor against the search widget endpoint every 5 minutes. Alert
   on any JavaScript error in the response.
4. Confirm all Pages projects have been audited for legacy path-glob cache keys.
   Document the audit results in the ops wiki.

---

## Related

- `pages-deploy-rollback-cache-invalidation-gap.md`
- `pages-functions-workers-routes-conflict-incident.md`
- `platform-migration-vercel-to-cloudflare-pages.md`
- `cache-invalidation-is-harder-than-caching.md`
- `third-party-api-changes-break-silent-integrations.md`

---

## Sources

- Cloudflare Pages build configuration: https://developers.cloudflare.com/pages/configuration/build-configuration/
- pnpm `--frozen-lockfile` documentation: https://pnpm.io/cli/install#--frozen-lockfile
- Internal incident ticket INC-2026-061 (restricted)
- Algolia autocomplete-js 4.8.3 regression: GitHub issue (upstream, now closed)
