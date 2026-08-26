# Wrangler CI Deploy Dry-Run Validation Gate

Date: 2026-08-23
Author: example.com
Status: production

## Symptom / Use-case

A Cloudflare Workers deploy reaches production with broken environment variable
bindings, missing KV namespace references, or an incompatible compatibility date,
because no CI step validated the wrangler configuration before the actual
`wrangler deploy` ran. For example project / example.com, a bad production push can
expose anonymous posts under the wrong account binding or break D1 migrations
mid-flight with no early warning.

## Context

Wrangler 3.x ships `--dry-run` and `--outdir` flags that compile the Worker bundle,
resolve all binding references, and validate the `wrangler.toml` schema without
pushing anything to the Cloudflare edge. This makes it safe to run in pull-request
CI as a blocking gate before a human or automation approves the real deploy. The
validation touches compatibility dates, service bindings, D1 databases, KV
namespaces, secrets (by name only), and Durable Object class exports.

## Section 1 — wrangler.toml schema and binding audit

Every `wrangler.toml` environment block must declare all runtime bindings explicitly.
Missing bindings silently resolve to `undefined` at runtime, which is particularly
dangerous for anonymous-post platforms where D1 or KV bindings gate write access.

```toml
# wrangler.toml (example project production)
name = "example project-api"
compatibility_date = "2026-07-01"
main = "src/index.ts"

[[d1_databases]]
binding = "DB"
database_name = "example project-prod"
database_id = "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"

[[kv_namespaces]]
binding = "SESSIONS"
id = "aaaabbbbccccddddeeeeffffgggghhhh"

[vars]
ENVIRONMENT = "production"
ANON_POST_EXPIRY_HOURS = "48"

[[unsafe.bindings]]   # feature flag store
type = "plain_text"
name = "FEATURE_FLAGS"
text = ""             # populated via Workers secret at runtime
```

Add a CI step that lints the toml before dry-run to catch typos:

```bash
# Install toml-lint or use python toml parser as lightweight check
python3 -c "import tomllib, sys; tomllib.loads(open('wrangler.toml').read()); print('TOML valid')"
```

## Section 2 — dry-run gate in GitHub Actions

The dry-run step compiles the full bundle and writes it to a temp directory. Exit
code non-zero means the gate blocks the deploy job.

```yaml
# .github/workflows/deploy.yml
name: Deploy example project API

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

jobs:
  validate:
    name: Dry-run validation gate
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-node@v4
        with:
          node-version: "20"
          cache: "npm"

      - run: npm ci

      - name: Wrangler dry-run (no deploy)
        env:
          CLOUDFLARE_API_TOKEN: ${{ secrets.CF_API_TOKEN }}
          CLOUDFLARE_ACCOUNT_ID: ${{ secrets.CF_ACCOUNT_ID }}
        run: |
          npx wrangler deploy --dry-run --outdir dist/dry-run
          echo "DRY_RUN_SIZE=$(du -sh dist/dry-run | cut -f1)" >> "$GITHUB_STEP_SUMMARY"

      - name: Verify bundle output exists
        run: |
          test -f dist/dry-run/index.js || (echo "ERROR: bundle missing" && exit 1)
          echo "Bundle OK: $(wc -c < dist/dry-run/index.js) bytes"

      - name: Upload dry-run artifact for diff inspection
        uses: actions/upload-artifact@v4
        with:
          name: dry-run-bundle-${{ github.sha }}
          path: dist/dry-run/
          retention-days: 7

  deploy:
    name: Deploy to Cloudflare
    needs: validate
    runs-on: ubuntu-latest
    if: github.ref == 'refs/heads/main'
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: "20"
          cache: "npm"
      - run: npm ci
      - name: Deploy
        env:
          CLOUDFLARE_API_TOKEN: ${{ secrets.CF_API_TOKEN }}
          CLOUDFLARE_ACCOUNT_ID: ${{ secrets.CF_ACCOUNT_ID }}
        run: npx wrangler deploy
```

## Section 3 — bundle size and compatibility date validation

Beyond just checking the build succeeds, add explicit guards around bundle size
regressions and compatibility date drift. A compatibility date too far in the past
may enable deprecated runtime behaviors that break anonymous post hashing logic.

```bash
#!/usr/bin/env bash
# scripts/validate-bundle.sh
set -euo pipefail

BUNDLE="dist/dry-run/index.js"
MAX_BYTES=2097152   # 2 MiB uncompressed Workers limit hint

SIZE=$(wc -c < "$BUNDLE")
echo "Bundle size: ${SIZE} bytes"

if [ "$SIZE" -gt "$MAX_BYTES" ]; then
  echo "ERROR: Bundle exceeds ${MAX_BYTES} bytes (got ${SIZE})"
  exit 1
fi

# Validate compatibility_date is within last 12 months
COMPAT_DATE=$(grep 'compatibility_date' wrangler.toml | head -1 | grep -oP '\d{4}-\d{2}-\d{2}')
COMPAT_EPOCH=$(date -d "$COMPAT_DATE" +%s)
CUTOFF_EPOCH=$(date -d "12 months ago" +%s)

if [ "$COMPAT_EPOCH" -lt "$CUTOFF_EPOCH" ]; then
  echo "WARNING: compatibility_date ${COMPAT_DATE} is more than 12 months old"
  echo "Consider bumping to current date after testing."
fi

echo "Validation passed."
```

## Section 4 — rollback

The dry-run gate itself cannot be rolled back — it is read-only. If a dry-run
passes but the subsequent real deploy breaks production, revert using wrangler
versions:

```bash
# List recent deployed versions
npx wrangler versions list

# Roll back to the last known-good version
npx wrangler rollback --message "dry-run gate passed but runtime regression detected"

# Re-run the dry-run on the reverted commit to confirm the gate catches it
git checkout <last-good-sha>
npx wrangler deploy --dry-run --outdir dist/dry-run-revert
```

For persistent failures, disable the failing PR branch deploy and open an incident
ticket referencing the dry-run artifact diff.

## Anti-patterns

- Running `wrangler deploy` directly in the PR CI job without a prior dry-run gate
- Using `--dry-run` without `--outdir` — the output is discarded and size checks
  cannot run
- Treating a passing dry-run as proof of runtime correctness — it only validates
  the bundle and binding declarations, not runtime logic
- Committing `dist/dry-run/` to the repo — always `.gitignore` the dry-run output
  directory
- Skipping the dry-run gate on hotfix branches "because it's urgent" — this is
  exactly when regressions slip through

## Gotchas

- `--dry-run` does not resolve secret values; it validates that secret *names*
  match what is declared in `wrangler.toml`. A secret that exists in Cloudflare
  but is missing from the toml `[vars]` / `[[unsafe.bindings]]` will still fail
  at runtime even if the dry-run passes.
- The `CLOUDFLARE_API_TOKEN` is still required for dry-run so wrangler can resolve
  binding IDs (KV namespace IDs, D1 database IDs) against the account.
- Dry-run bundles produced by different wrangler versions may differ in size even
  with identical source — pin wrangler version in `package.json` to get stable
  comparisons.
- Pages Functions projects use `wrangler pages deploy --dry-run` (different
  subcommand); Workers and Pages must each have their own gate.

## Verification

1. Introduce a deliberate typo in a KV binding name in `wrangler.toml` — the
   dry-run should exit non-zero.
2. Import a module that does not exist — the bundle step should fail.
3. Set `compatibility_date` to a date in the future — wrangler should warn or
   error depending on the version.
4. Check that the `deploy` job in GitHub Actions does NOT run when `validate`
   fails — confirm via the Actions UI that the job is skipped, not just failed.

## Related

- `/documentation/categories/deploy/wrangler-config-validation-pre-deploy-ci-hook.md`
- `/documentation/categories/deploy/wrangler-publish-dry-run-diff-preview.md`
- `/documentation/categories/deploy/deploy-gate-antipatterns.md`
- `/documentation/categories/deploy/workers-bundle-analysis-regression-ci.md`

## Sources

- https://developers.cloudflare.com/workers/wrangler/commands/#deploy
- https://developers.cloudflare.com/workers/configuration/compatibility-dates/
- https://developers.cloudflare.com/workers/platform/limits/#worker-size
- https://github.com/cloudflare/workers-sdk/blob/main/packages/wrangler/CHANGELOG.md
