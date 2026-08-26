# GitHub Actions Workers Bundle Size Regression Check

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

A Cloudflare Workers deployment silently grows in bundle size — the Worker exceeds the 1 MB compressed script limit, cold-start latency increases, or a dependency bloat goes unnoticed until production. You want CI to block PRs that cause size regressions above a defined threshold.

## Context

Wrangler outputs bundle size data after every build. The Worker script limit is 1 MB (compressed) for Bundled usage model and 5 MB for Unbound/Workers Paid. `wrangler deploy --dry-run` (and `wrangler deploy --outdir`) emit the final gzipped bundle size to stdout. Capturing and diffing that figure on every PR catches regressions before merge.

---

## 1. Build and Capture Bundle Size

```yaml
# .github/workflows/bundle-size.yml
name: Bundle Size Check

on:
  pull_request:
    branches: [main]

jobs:
  bundle-size:
    runs-on: ubuntu-latest
    permissions:
      pull-requests: write
      contents: read

    steps:
      - uses: actions/checkout@v4
        with: { fetch-depth: 0 }

      - uses: actions/setup-node@v4
        with:
          node-version: '22'
          cache: 'pnpm'

      - run: pnpm install --frozen-lockfile

      - name: Build PR branch
        run: |
          pnpm wrangler deploy --dry-run --outdir dist-pr #<number>>&1 | tee build-pr.log
          grep -oP 'Total Upload: \K[0-9.]+ [KM]iB' build-pr.log > size-pr.txt || \
            du -sh dist-pr/*.js | awk '{print $1}' > size-pr.txt
```

## 2. Measure Baseline on Main

```yaml
      - name: Checkout main for baseline
        run: |
          git stash --include-untracked
          git checkout origin/main -- .
          pnpm install --frozen-lockfile --silent
          pnpm wrangler deploy --dry-run --outdir dist-main 2>&1 | tee build-main.log
          grep -oP 'Total Upload: \K[0-9.]+ [KM]iB' build-main.log > size-main.txt || \
            du -sh dist-main/*.js | awk '{print $1}' > size-main.txt
          git checkout HEAD -- .
          git stash pop || true
```

## 3. Compare and Enforce Threshold

```typescript
// scripts/check-bundle-size.ts
import { readFileSync } from 'fs';

function parseKiB(s: string): number {
  const [num, unit] = s.trim().split(' ');
  if (unit?.includes('M')) return parseFloat(num) * 1024;
  return parseFloat(num);
}

const pr   = parseKiB(readFileSync('size-pr.txt', 'utf8'));
const main = parseKiB(readFileSync('size-main.txt', 'utf8'));
const delta = pr - main;
const pct   = ((delta / main) * 100).toFixed(1);

const THRESHOLD_KIB  = 10;   // absolute KiB increase limit
const THRESHOLD_PCT  = 5;    // percent increase limit
const HARD_LIMIT_KIB = 900;  // never exceed (compressed 1MB = ~900 KiB gzip)

console.log(`Main: ${main.toFixed(1)} KiB | PR: ${pr.toFixed(1)} KiB | Delta: ${delta >= 0 ? '+' : ''}${delta.toFixed(1)} KiB (${pct}%)`);

if (pr > HARD_LIMIT_KIB) {
  console.error(`FAIL: Bundle ${pr.toFixed(1)} KiB exceeds hard limit ${HARD_LIMIT_KIB} KiB`);
  process.exit(1);
}
if (delta > THRESHOLD_KIB && parseFloat(pct) > THRESHOLD_PCT) {
  console.error(`FAIL: Bundle grew by ${delta.toFixed(1)} KiB (${pct}%) — both thresholds exceeded`);
  process.exit(1);
}
console.log('PASS: Bundle size within acceptable limits');
```

## 4. Run Comparison in CI

```yaml
      - name: Compare bundle sizes
        run: npx tsx scripts/check-bundle-size.ts

      - name: Post size comment on PR
        if: always()
        uses: actions/github-script@v7
        with:
          script: |
            const fs = require('fs');
            const pr   = fs.readFileSync('size-pr.txt', 'utf8').trim();
            const main = fs.readFileSync('size-main.txt', 'utf8').trim();
            const body = [
              '## Bundle Size Report',
              `| Branch | Size |`,
              `|--------|------|`,
              `| \`main\` | ${main} |`,
              `| This PR | ${pr} |`,
            ].join('\n');
            const { data: comments } = await github.rest.issues.listComments({
              owner: context.repo.owner, repo: context.repo.repo,
              issue_number: context.issue.number,
            });
            const existing = comments.find(c => c.body.startsWith('## Bundle Size Report'));
            if (existing) {
              await github.rest.issues.updateComment({
                owner: context.repo.owner, repo: context.repo.repo,
                comment_id: existing.id, body,
              });
            } else {
              await github.rest.issues.createComment({
                owner: context.repo.owner, repo: context.repo.repo,
                issue_number: context.issue.number, body,
              });
            }
```

## 5. Cache Baseline to Avoid Re-building Main on Every Run

```yaml
      - name: Restore cached main bundle size
        id: cache-main
        uses: actions/cache@v4
        with:
          path: size-main.txt
          key: bundle-main-${{ hashFiles('pnpm-lock.yaml', 'src/**', 'wrangler.toml') }}-${{ github.sha }}
          restore-keys: bundle-main-

      - name: Build main baseline (if not cached)
        if: steps.cache-main.outputs.cache-hit != 'true'
        run: |
          git fetch origin main --depth=1
          # … same baseline build as step 2 …
```

---

## Anti-patterns

- Comparing `wrangler build` output file sizes without gzip — the platform limit is compressed size; raw `.js` comparisons will underestimate by 40–60%.
- Setting the threshold to 0 KiB — any import of a tree-shaken package will fail CI on minor version bumps.
- Not caching the baseline — rebuilding `main` from scratch on every PR doubles build time and wastes runner minutes.
- Checking only total size — for Workers with multiple entrypoints or Durable Objects, check each output chunk separately.

## Gotchas

- `wrangler deploy --dry-run` still requires `CLOUDFLARE_API_TOKEN` to resolve bindings; use a read-only token or pass `--compatibility-date` and stub bindings.
- Wrangler's "Total Upload" log line format has changed across versions — pin the Wrangler version in `package.json` or parse `dist/*.js` directly as a fallback.
- Workers with Durable Objects emit separate `.js` files; the migration chunk is included in the reported total but rarely changes.
- `git stash` can fail on a clean checkout — guard with `|| true` to avoid blocking the workflow.

## Verification

```bash
# Locally reproduce the check
pnpm wrangler deploy --dry-run --outdir dist-pr #<number>>&1 | grep 'Total Upload'
# Should print: Total Upload: 312.45 KiB / gzip: 88.12 KiB
```

The CI job should appear as a required status check named `bundle-size` in branch protection rules so it blocks merges when the threshold is exceeded.

## Related

- `github-actions-cache-wrangler-build-optimization.md`
- `github-actions-cloudflare-deploy-workflow.md`
- `github-actions-artifact-size-audit.md`
- `github-actions-wasm-build-caching-workers.md`

## Sources

- https://developers.cloudflare.com/workers/platform/limits/#worker-size
- https://developers.cloudflare.com/workers/wrangler/commands/#deploy
- https://github.com/actions/cache
