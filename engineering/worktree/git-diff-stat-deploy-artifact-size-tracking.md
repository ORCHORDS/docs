# git diff --stat Deploy Artifact Size Tracking for Cloudflare Workers

Date: 2026-08-23
Author: example.com
Status: production

---

## Symptom / Use-case

A Cloudflare Worker silently grows past the 1 MB compressed script limit (3 MB for paid plans) during routine feature work. The CI pipeline only catches the violation at deploy time, after the PR is merged. Teams need a lightweight way to track Worker bundle size as a first-class diff metric alongside code changes — before the Wrangler deploy step runs.

---

## Context

Wrangler bundles each Worker entry-point with esbuild, emitting a `.js` file (or `.wasm` + `.js` pair) under `.wrangler/dist/`. `git diff --stat` reports line and byte deltas between two refs. By capturing the built artifact, committing a size manifest, and diffing that manifest on each PR, teams get artifact size visibility in the same place as code review — the pull-request diff — with no external tooling required.

This pattern pairs naturally with GitHub Actions `wrangler build` dry-runs, `git diff --stat`, and `git notes` for historical size annotation.

---

## Build and Capture a Size Manifest

Run `wrangler build` (no deploy) to emit artifacts, then write a size manifest:

```typescript
// scripts/capture-sizes.ts
import { execSync } from "node:child_process";
import { readdirSync, statSync, writeFileSync } from "node:fs";
import { join } from "node:path";

const distDir = ".wrangler/dist";

interface SizeEntry {
  file: string;
  bytes: number;
  kb: string;
}

function captureSizes(dir: string): SizeEntry[] {
  return readdirSync(dir)
    .filter((f) => f.endsWith(".js") || f.endsWith(".wasm"))
    .map((f) => {
      const full = join(dir, f);
      const bytes = statSync(full).size;
      return { file: f, bytes, kb: (bytes / 1024).toFixed(2) };
    })
    .sort((a, b) => a.file.localeCompare(b.file));
}

const entries = captureSizes(distDir);
const manifest = { generated: new Date().toISOString(), workers: entries };
writeFileSync("worker-sizes.json", JSON.stringify(manifest, null, 2));
console.table(entries);
```

```bash
npx tsx scripts/capture-sizes.ts
# worker-sizes.json is now a tracked file in the repository root
```

---

## GitHub Actions: Build, Diff, and Gate

```yaml
# .github/workflows/size-check.yml
name: Worker Size Check

on:
  pull_request:
    branches: [main]

jobs:
  size-gate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0           # need base branch for diff

      - uses: actions/setup-node@v4
        with:
          node-version: 22

      - run: npm ci

      - name: Build Workers
        run: npx wrangler build
        env:
          CLOUDFLARE_API_TOKEN: ${{ secrets.CF_API_TOKEN }}

      - name: Capture new sizes
        run: npx tsx scripts/capture-sizes.ts

      - name: Show size diff
        run: |
          git diff --stat HEAD worker-sizes.json
          git diff HEAD worker-sizes.json

      - name: Enforce 1 MB limit (paid plan: 3 MB)
        run: |
          node -e "
            const { workers } = require('./worker-sizes.json');
            const LIMIT = 1_000_000;  // 1 MB uncompressed heuristic
            const over = workers.filter(w => w.bytes > LIMIT);
            if (over.length) {
              console.error('Workers exceeding size limit:');
              over.forEach(w => console.error(\`  \${w.file}: \${w.kb} KB\`));
              process.exit(1);
            }
            console.log('All Workers within size limit.');
          "
```

---

## Reading git diff --stat Output for Artifacts

`git diff --stat` gives a quick byte-level story when the manifest changes:

```bash
# On a PR branch, after building:
git diff origin/main -- worker-sizes.json

# Example output interpretation:
# -  "bytes": 284123,     # was 277 KB on main
# +  "bytes": 391042,     # now 382 KB — ~37% growth, investigate

# Summarised view:
git diff --stat origin/main -- worker-sizes.json
# worker-sizes.json | 4 ++--
# 1 file changed, 2 insertions(+), 2 deletions(-)
```

Use `git diff --word-diff=plain` to surface only the numeric changes without line noise:

```bash
git diff --word-diff=plain origin/main -- worker-sizes.json
# "bytes": [-284123-]{+391042+},
```

---

## Annotating Historical Sizes with git notes

Store a size snapshot against every deploy commit without touching the commit message:

```bash
# After a successful deploy:
SIZES=$(jq -c '.workers' worker-sizes.json)
git notes --ref=worker-sizes add -m "$SIZES" HEAD

# Later, audit size growth across releases:
git log --notes=worker-sizes --format="%h %s%n%N" v1.0.0..v2.0.0
```

Push notes to the remote so CI can read them:

```bash
git push origin refs/notes/worker-sizes
# Fetch in CI:
git fetch origin refs/notes/worker-sizes:refs/notes/worker-sizes
```

---

## Tracking Size per Worker in a Monorepo

When a monorepo hosts multiple Workers under `apps/`, generate one manifest per Worker and concatenate:

```typescript
// scripts/capture-all-sizes.ts
import { execSync } from "node:child_process";
import { existsSync, readdirSync, statSync, writeFileSync } from "node:fs";
import { join } from "node:path";

const appsDir = "apps";
const results: Record<string, number> = {};

for (const app of readdirSync(appsDir)) {
  const dist = join(appsDir, app, ".wrangler", "dist");
  if (!existsSync(dist)) continue;
  for (const f of readdirSync(dist).filter((f) => f.endsWith(".js"))) {
    const key = `${app}/${f}`;
    results[key] = statSync(join(dist, f)).size;
  }
}

writeFileSync(
  "worker-sizes.json",
  JSON.stringify({ generated: new Date().toISOString(), sizes: results }, null, 2)
);
```

---

## Anti-patterns

- **Committing built artifacts directly** — `.wrangler/dist/` should stay in `.gitignore`. Only the human-readable JSON manifest belongs in version control.
- **Using compressed (gzip) size as the tracked metric in the manifest** — Wrangler's limit applies to the uncompressed script; track raw bytes and add a note about the compression ratio separately.
- **Running the size check only on `main`** — by that point the PR is merged. Always run it on `pull_request` events so authors get feedback before merge.
- **Storing one global manifest for all environments** — Workers differ by environment (staging minifies differently than production). Tag the manifest with `WRANGLER_ENV`.

---

## Gotchas

- `wrangler build` respects `wrangler.toml` `[build]` steps but does not require a live Cloudflare account — set `CLOUDFLARE_ACCOUNT_ID` to any string to skip the auth check in dry-run mode on older Wrangler versions.
- esbuild's output size is deterministic given the same input and version, but Wrangler may produce slightly different output across Wrangler versions due to bundler upgrades — pin Wrangler in `package.json`.
- `git diff --stat` counts diff lines, not bytes. For large binary-ish JSON diffs use `git diff --no-color | wc -c` or parse the manifest programmatically.
- Workers using `import` of WASM modules have the `.wasm` file counted separately; both files together count toward the Worker's compressed limit.

---

## Verification

```bash
# 1. Build Workers locally
npx wrangler build

# 2. Capture sizes
npx tsx scripts/capture-sizes.ts

# 3. Confirm manifest was created
cat worker-sizes.json

# 4. Simulate a PR diff against main
git diff origin/main -- worker-sizes.json

# 5. Run the gate script
node -e "
  const { workers } = require('./worker-sizes.json');
  const over = workers.filter(w => w.bytes > 1_000_000);
  console.log(over.length ? 'FAIL' : 'PASS', over);
"
```

---

## Related

- `github-actions-wrangler-deploy-pipeline.md`
- `workers-d1-migration-ci-pipeline.md`
- `git-notes-collaborative-annotations-workflow.md`
- `monorepo-wrangler-selective-deploy.md`
- `performance-budget-workflow.md`

---

## Sources

- Cloudflare Workers limits: https://developers.cloudflare.com/workers/platform/limits/
- Wrangler CLI reference: https://developers.cloudflare.com/workers/wrangler/commands/#build
- git-diff documentation: https://git-scm.com/docs/git-diff
- git-notes documentation: https://git-scm.com/docs/git-notes
