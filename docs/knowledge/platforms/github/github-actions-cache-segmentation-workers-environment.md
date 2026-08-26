# GitHub Actions Cache Segmentation by Workers Environment

- **Date:** 2026-08-23
- **Author:** example.com
- **Status:** production

## Symptom / Use-case

You run CI for multiple Cloudflare Workers environments (preview, staging,
production) and see stale build artifacts crossing environment boundaries:
a production build is restored from a staging cache key, causing mismatched
compatibility dates or environment-specific bindings to bleed across deploys.

## Context

GitHub Actions cache keys are global within a repository. When a Workers
project uses per-environment `wrangler.toml` config (different
`compatibility_date`, different KV/D1 bindings, different routes), build
outputs are not interchangeable. Cache keys must encode the environment name
alongside the lock-file hash so each environment maintains an isolated cache
slot.

## Base Cache Key Pattern

```yaml
# .github/workflows/workers-deploy.yml
name: Workers Deploy

on:
  push:
    branches: [main, staging, "preview/**"]

jobs:
  deploy:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        environment: [preview, staging, production]
        exclude:
          - environment: production
            # Only deploy production from main
    env:
      WORKERS_ENV: ${{ matrix.environment }}

    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-node@v4
        with:
          node-version: "20"

      - name: Restore npm cache (environment-scoped)
        uses: actions/cache@v4
        with:
          path: node_modules
          key: npm-${{ matrix.environment }}-${{ runner.os }}-${{ hashFiles('package-lock.json') }}
          restore-keys: |
            npm-${{ matrix.environment }}-${{ runner.os }}-
            npm-${{ matrix.environment }}-

      - run: npm ci
```

## Build Cache Segmentation

```yaml
      - name: Restore Workers build cache
        uses: actions/cache@v4
        with:
          path: |
            .wrangler/
            dist/
          key: workers-build-${{ matrix.environment }}-${{ hashFiles('wrangler.toml','src/**','package-lock.json') }}
          restore-keys: |
            workers-build-${{ matrix.environment }}-

      - name: Build for environment
        run: npm run build -- --env ${{ matrix.environment }}

      - name: Deploy to Workers
        run: npx wrangler deploy --env ${{ matrix.environment }}
        env:
          CLOUDFLARE_API_TOKEN: ${{ secrets.CF_API_TOKEN }}
```

## Dynamic Cache Key via Script

```typescript
// scripts/cache-key.ts  (run via tsx in CI to generate composite key)
import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";
import { execSync } from "node:child_process";

const env = process.argv[2] ?? "preview";
const lockHash = createHash("sha256")
  .update(readFileSync("package-lock.json"))
  .digest("hex")
  .slice(0, 16);

// Include wrangler env-specific config hash
const wranglerEnvHash = createHash("sha256")
  .update(execSync(`npx wrangler whoami --env ${env}`, { encoding: "utf8" }))
  .digest("hex")
  .slice(0, 8);

console.log(`workers-${env}-${lockHash}-${wranglerEnvHash}`);
```

```yaml
      - name: Compute cache key
        id: ckey
        run: echo "key=$(npx tsx scripts/cache-key.ts ${{ matrix.environment }})" >> "$GITHUB_OUTPUT"

      - uses: actions/cache@v4
        with:
          path: dist/
          key: ${{ steps.ckey.outputs.key }}
```

## Preventing Cross-environment Cache Poisoning

```yaml
      - name: Validate build output matches environment
        run: |
          ENV="${{ matrix.environment }}"
          COMPAT=$(node -e "
            const toml = require('fs').readFileSync('wrangler.toml','utf8');
            const m = toml.match(/\[env\.$ENV\][^\[]*compatibility_date\s*=\s*\"([^\"]+)\"/s);
            console.log(m ? m[1] : '');
          ")
          echo "Expected compatibility_date for $ENV: $COMPAT"
          # Verify the built output declares the same date
          grep -q "$COMPAT" dist/worker.js || {
            echo "ERROR: compatibility_date mismatch in built output"
            exit 1
          }
        env:
          ENV: ${{ matrix.environment }}
```

## Cache Eviction Strategy

```yaml
      # Force-bust when environment config changes
      - name: Bust cache if env config changed
        if: contains(github.event.head_commit.modified, 'wrangler.toml')
        run: echo "CACHE_BUST=$(date +%s)" >> "$GITHUB_ENV"

      - uses: actions/cache@v4
        with:
          path: dist/
          key: workers-${{ matrix.environment }}-${{ env.CACHE_BUST || hashFiles('src/**') }}
```

## Anti-patterns

- **Sharing a single cache key across all environments** — a production build restored into a preview deploy may include production-only secrets references or incompatible binding names.
- **Using only `hashFiles('package-lock.json')` as the key** — two environments with the same deps but different `compatibility_date` values will share a cache entry and produce wrong builds.
- **Caching `.wrangler/` across environments** — the `.wrangler/` directory stores deploy receipts and asset manifests that are environment-specific. Isolate or exclude it.
- **No `restore-keys` fallback** — without a partial restore key, a new PR with a minor dep bump forces a full `npm ci` on every environment.

## Gotchas

- GitHub Actions cache keys are immutable once written; a cache hit on an exact key will never update. Always use a content-addressed component (`hashFiles`) so the key changes when content changes.
- Cache size limit is 10 GB per repository across all branches. Per-environment segmentation multiplies cache slots — prune unused branches' caches via the GitHub UI or `gh cache delete`.
- `restore-keys` matches are prefix-ordered: the most specific surviving prefix wins. Order your `restore-keys` from most to least specific.
- Matrix jobs run in parallel; if two environments race to write to the same partial restore key, the first writer wins — subsequent writes are silently dropped.

## Verification

```bash
# List all cache entries and confirm per-environment isolation
gh cache list --repo MY_ORG/MY_REPO \
  | grep "workers-build-" \
  | awk '{print $1, $2}' \
  | sort

# Expected output: separate entries per environment
# workers-build-preview-...   2.1 MB
# workers-build-staging-...   2.1 MB
# workers-build-production-...  2.2 MB
```

## Related

- `github-actions-cache-invalidation-workers-builds.md`
- `github-actions-cache-dependencies.md`
- `github-actions-environments.md`

## Sources

- https://docs.github.com/en/actions/writing-workflows/choosing-what-your-workflow-does/caching-dependencies-to-speed-up-workflows
- https://developers.cloudflare.com/workers/wrangler/environments/
