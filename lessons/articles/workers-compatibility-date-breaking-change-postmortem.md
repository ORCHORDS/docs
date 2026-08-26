# Workers Compatibility Date Breaking Change Postmortem

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

A Workers-based API service began returning 500 errors immediately after a
scheduled wrangler upgrade in a CI/CD pipeline. The deploy itself succeeded
and no application code had changed. The failure was traced to a new
compatibility date being set by the upgraded `wrangler` CLI, which activated
a runtime behavior change that broke an assumption in the application's URL
parsing logic.

---

## Context

Cloudflare Workers uses a "compatibility date" system to manage breaking
changes to the Workers runtime. When you set a `compatibility_date` in
`wrangler.toml`, the runtime enables all behaviors that were finalized on or
before that date. Advancing the date opts into accumulated behavior changes,
some of which are breaking.

The compatibility date is intended to give developers control over when they
adopt breaking changes. However, when the date is set automatically (by
`wrangler deploy` choosing "today" as a default or by a CI pipeline upgrading
wrangler and implicitly advancing the date), developers can be silently opted
into breaking changes without a code review.

---

## Timeline

| Time | Event |
|------|-------|
| T+0 | CI pipeline runs `npm update wrangler` as part of weekly dependency update |
| T+5m | `wrangler deploy` runs; `wrangler.toml` had no pinned `compatibility_date` |
| T+6m | `wrangler` CLI sets `compatibility_date` to today (its default behavior when unset) |
| T+6m | Workers runtime activates `url_standard` flag (part of the new date's enabled set) |
| T+7m | Production errors begin: `new URL(relativeUrl)` now throws instead of resolving |
| T+22m | On-call acknowledges alerts |
| T+45m | Root cause identified: compatibility date advanced, `url_standard` changed URL behavior |
| T+60m | Pinned previous compatibility date in `wrangler.toml`, redeployed, incident resolved |

---

## What Changed: `url_standard`

Prior to a certain compatibility date, `new URL("/path", undefined)` in
Workers behaved permissively — it resolved relative URLs against a default
base. After the `url_standard` flag was activated (matching the WHATWG URL
standard more closely), the same call throws `TypeError: Failed to construct
'URL': Invalid URL` when no valid base is provided.

The application code:

```typescript
// BROKE when url_standard was activated
function parseCallbackUrl(rawUrl: string): URL {
  // Assumed Workers would supply a default base for relative paths
  return new URL(rawUrl); // throws for "/callback" without a base
}
```

The fix requires an explicit base URL:

```typescript
function parseCallbackUrl(rawUrl: string, requestUrl: string): URL {
  return new URL(rawUrl, requestUrl); // correct: uses the request's URL as base
}
```

---

## Compatibility Flags System

Compatibility flags are named feature toggles associated with compatibility
dates. You can inspect which flags a given date activates in the Cloudflare
documentation or by running:

```
wrangler compatibility-flags --compatibility-date 2025-03-01
```

Some flags can also be enabled or disabled individually in `wrangler.toml`
regardless of the compatibility date, allowing incremental adoption:

```toml
# wrangler.toml
compatibility_date = "2024-09-23"

# Opt into a specific flag ahead of its date
compatibility_flags = ["nodejs_compat"]

# Opt OUT of a flag that your date would normally enable
# (only works for flags that support this)
# compatibility_flags = ["no_url_standard"]
```

---

## The Right Way to Manage Compatibility Dates

### 1. Always pin `compatibility_date` in `wrangler.toml`

```toml
# wrangler.toml
name = "my-worker"
main = "src/index.ts"
compatibility_date = "2024-09-23"  # pin explicitly; never let wrangler choose
```

Never rely on `wrangler deploy` to set the date automatically. The default
behavior (choosing today's date when unset) is convenient for new projects
but dangerous for established workers.

### 2. Advance the compatibility date deliberately, as a separate PR

Treat a compatibility date advance as a code change — review the list of
newly enabled flags, update any affected code, and merge as a dedicated PR
after validation in a staging environment.

```bash
# View what changes between two dates before upgrading
wrangler compatibility-flags --from 2024-09-23 --to 2025-03-01
```

### 3. Gate compatibility date advances behind an integration test suite

```typescript
// vitest — assert specific URL parsing behavior that breaks under url_standard
describe("URL parsing", () => {
  it("resolves relative callback URLs against the request base", () => {
    const requestUrl = "https://api.example.com/auth/start";
    const callback = parseCallbackUrl("/auth/callback", requestUrl);
    expect(callback.href).toBe("https://api.example.com/auth/callback");
  });

  it("throws on a relative URL with no base", () => {
    expect(() => new URL("/auth/callback")).toThrow();
  });
});
```

Run this suite against a Miniflare instance configured with the prospective
new compatibility date before advancing it in production.

### 4. Add the compatibility date to your CI environment variable, not hardcoded

This lets you test upcoming compat date changes in a branch without changing
the committed `wrangler.toml`:

```yaml
# .github/workflows/deploy.yml
- name: Deploy Worker
  run: wrangler deploy
  env:
    CLOUDFLARE_API_TOKEN: ${{ secrets.CF_API_TOKEN }}
    # Override compat date for compat-upgrade testing branches only
    # WRANGLER_COMPATIBILITY_DATE: "2025-06-01"
```

---

## Anti-patterns

- No `compatibility_date` in `wrangler.toml` — `wrangler` will choose today's
  date on every deploy, silently advancing the date with every CI run.
- Bundling `wrangler` upgrades with application code changes — makes it
  impossible to attribute failures to the wrangler version vs application code.
- Treating the compatibility date as a minor configuration detail not subject
  to code review.
- Not having an integration test suite that runs against the Workers runtime
  (Miniflare) and would catch behavior changes before production.
- Disabling compatibility flags globally to work around the system — this
  accumulates technical debt and makes future date advances even more disruptive.

---

## Gotchas

**The `nodejs_compat` flag is separate from the date system**: Node.js
compatibility APIs in Workers are enabled via `compatibility_flags =
["nodejs_compat"]` and are not automatically activated by advancing the date.
This flag has its own breaking changes between minor versions.

**Miniflare does not always mirror production compat flag behavior**:
Miniflare aims for parity but there can be lag between a new compatibility
flag landing in the production Workers runtime and being supported in the
Miniflare version your CI uses. Pin both the `wrangler` version and the
`miniflare` version in `package.json` when testing compatibility date changes.

**`wrangler dev` may use a different date than `wrangler deploy`**: If
`wrangler dev` is started without `--compatibility-date` it may default to
the date in `wrangler.toml`, or it may pick a different value depending on
the wrangler version. Always run `wrangler dev --compatibility-date
<pinned-date>` to match production.

**Some flags cannot be opted out of**: Once a flag is deemed stable by
Cloudflare, the ability to disable it may be removed. The window to opt out
is finite — plan compatibility date advances before opt-out is no longer
possible.

---

## Verification

1. Confirm `wrangler.toml` in every Workers project in the monorepo has an
   explicit `compatibility_date`. Add a lint rule or CI check:

   ```bash
   grep -rL "compatibility_date" workers/ | grep "wrangler.toml" \
     && echo "FAIL: missing compatibility_date" && exit 1
   ```

2. Add a changelog step to the "compatibility date upgrade" PR template that
   lists each newly enabled flag and the application code change (if any)
   required.

3. After advancing the date in staging, run the full integration test suite
   and a 15-minute canary with live traffic mirroring before advancing in
   production.

4. Subscribe to the Cloudflare Workers Changelog and the compatibility flags
   documentation page for updates.

---

## Related

- `workers-binding-version-drift-production-incident.md` — wrangler version drift
- `cloudflare-workers-engineering-onboarding.md` — Workers runtime fundamentals
- `dependency-default-change-needs-upgrade-path-test.md` — managing dep upgrades
- `always-test-rollback-before-deploying.md` — rollback discipline

---

## Sources

- Cloudflare Workers documentation: "Compatibility dates"
- Cloudflare Workers documentation: "Compatibility flags"
- Cloudflare changelog: "url_standard flag — Workers runtime update"
- wrangler CLI changelog: default compatibility date selection behavior
