# Cloudflare Pages Build Watch-Path Optimization

Date: 2026-08-23 / Author: example.com / Status: production

## Symptom / Use-case

Every commit to the monorepo triggers a full Pages build even when only unrelated packages
changed. Build minutes are consumed unnecessarily, preview environments stack up, and
developers lose time waiting for deploys that cannot possibly affect the Pages app. You need
path-scoped triggers so builds fire only when the Pages source tree — or an explicit
dependency of it — actually changed.

---

## Context

Cloudflare Pages has no first-class "watch paths" knob in the dashboard equivalent to GitHub
Actions' `paths:` filter. The guard must be implemented at the CI layer: a pre-build job
inspects the git diff and either allows or short-circuits the subsequent `wrangler pages deploy`
step. When the repository is managed with a package manager aware of workspaces (npm, pnpm,
Turborepo), the diff check can also walk the dependency graph so changes to a shared library
still trigger the Pages build even though the library lives outside the Pages source tree.

Relevant primitives:
- `git diff --name-only HEAD~1..HEAD` — files changed in the latest push.
- `turbo run build --filter=web --dry=json` — Turborepo dry-run to surface the affected
  package graph without building anything.
- GitHub Actions `paths:` / `paths-ignore:` — coarse pre-filter before the watch-path script
  runs; cuts Actions minutes for trivially unrelated changes (docs, infra).

---

## 1. Baseline: coarse GitHub Actions `paths:` filter

```yaml
# .github/workflows/pages-deploy.yml
on:
  push:
    branches: [main]
    paths:
      - "apps/web/**"
      - "packages/ui/**"
      - "packages/api-client/**"
      - "wrangler.toml"
      - "package.json"
      - "pnpm-lock.yaml"
  workflow_dispatch:
```

This eliminates the majority of spurious builds at zero cost. It is not sufficient on its own
because it cannot understand the workspace dependency graph.

---

## 2. Fine-grained diff check script (TypeScript)

```typescript
// scripts/should-build-pages.ts
import { execSync } from "node:child_process";
import { readFileSync } from "node:fs";

/** Directories whose changes must trigger a Pages rebuild. */
const WATCH_PATHS: RegExp[] = [
  /^apps\/web\//,
  /^packages\/ui\//,
  /^packages\/api-client\//,
  /^wrangler\.toml$/,
  /^package\.json$/,
  /^pnpm-lock\.yaml$/,
];

function changedFiles(base: string, head: string): string[] {
  return execSync(`git diff --name-only ${base}...${head}`)
    .toString()
    .trim()
    .split("\n")
    .filter(Boolean);
}

function shouldBuild(): boolean {
  const base = process.env.GITHUB_BASE_SHA ?? "HEAD~1";
  const head = process.env.GITHUB_HEAD_SHA ?? "HEAD";
  const files = changedFiles(base, head);

  console.log(`Checking ${files.length} changed file(s) against watch paths…`);

  return files.some((f) => WATCH_PATHS.some((rx) => rx.test(f)));
}

const build = shouldBuild();
// Write result to GITHUB_OUTPUT so downstream jobs can gate on it.
const output = process.env.GITHUB_OUTPUT;
if (output) {
  const { appendFileSync } = await import("node:fs");
  appendFileSync(output, `should_build=${build}\n`);
}

process.exit(build ? 0 : 0); // always exit 0; the boolean is the gate
```

---

## 3. Turborepo dependency-graph awareness

```typescript
// scripts/turbo-affected-pages.ts
import { execSync } from "node:child_process";

interface TurboDryResult {
  tasks: Array<{ taskId: string; package: string }>;
}

function isWebAffected(): boolean {
  try {
    const raw = execSync(
      "pnpm turbo run build --filter=web --dry=json 2>/dev/null",
      { encoding: "utf-8" }
    );
    const result: TurboDryResult = JSON.parse(raw);
    // If any task in the web package shows up, something in its graph changed.
    return result.tasks.some((t) => t.package === "web");
  } catch {
    // If turbo fails, default to building (safe path).
    console.warn("turbo dry-run failed; defaulting to build=true");
    return true;
  }
}

const affected = isWebAffected();
console.log(`web package affected by current diff: ${affected}`);

if (process.env.GITHUB_OUTPUT) {
  const fs = await import("node:fs");
  fs.appendFileSync(process.env.GITHUB_OUTPUT, `turbo_affected=${affected}\n`);
}
```

---

## 4. GitHub Actions job that wires both checks

```yaml
jobs:
  gate:
    runs-on: ubuntu-latest
    outputs:
      should_build: ${{ steps.check.outputs.should_build }}
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 2          # need HEAD~1 for diff

      - uses: pnpm/action-setup@v4
      - uses: actions/setup-node@v4
        with:
          node-version: 22
          cache: pnpm

      - run: pnpm install --frozen-lockfile

      - id: check
        env:
          GITHUB_BASE_SHA: ${{ github.event.before }}
          GITHUB_HEAD_SHA: ${{ github.sha }}
        run: pnpm tsx scripts/should-build-pages.ts

  deploy:
    needs: gate
    if: needs.gate.outputs.should_build == 'true'
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: pnpm/action-setup@v4
      - run: pnpm install --frozen-lockfile
      - run: pnpm turbo run build --filter=web
      - run: pnpm wrangler pages deploy apps/web/dist --project-name=my-pages-project
        env:
          CLOUDFLARE_API_TOKEN: ${{ secrets.CF_API_TOKEN }}
```

---

## 5. Handling `workflow_dispatch` and force-deploy

Manual triggers should always build regardless of the diff:

```typescript
// scripts/should-build-pages.ts  (addition)
function shouldBuild(): boolean {
  if (process.env.GITHUB_EVENT_NAME === "workflow_dispatch") {
    console.log("Manual dispatch — forcing build.");
    return true;
  }
  // …rest of diff logic
}
```

Add a `force_deploy` input to `workflow_dispatch` for on-call engineers who need to re-deploy
without changing code:

```yaml
on:
  workflow_dispatch:
    inputs:
      force_deploy:
        description: "Deploy even if nothing in watch paths changed"
        type: boolean
        default: false
```

---

## Anti-patterns

- **Skipping `fetch-depth`**: `git diff HEAD~1` silently fails when the checkout is shallow
  (depth 1). Always set `fetch-depth: 2` or use `fetch-depth: 0` and pass explicit SHAs.
- **Hard-coding `HEAD~1`**: squash merges and force-pushes shift the reference. Use
  `github.event.before` and `github.sha` from the event payload instead.
- **Watching only `apps/web/`**: if a shared `packages/design-tokens` changes without touching
  `apps/web/`, the build is skipped but should have run. Add Turborepo awareness or enumerate
  all transitive deps in `WATCH_PATHS`.
- **Dropping the `workflow_dispatch` bypass**: operators lose the ability to force a re-deploy
  during an incident.

---

## Gotchas

- `git diff --name-only A...B` (three dots) compares `A` against the merge-base, not `A`
  directly. On `push` events you normally want two-dot `A..B` to see exactly what landed.
- Turborepo's `--dry=json` output schema can change across versions; pin `turbo` in
  `package.json` and test the script after upgrades.
- If `pnpm-lock.yaml` changes but nothing in `WATCH_PATHS` does, you still want a build because
  a transitive dep update may have affected the bundle. Include the lockfile in `WATCH_PATHS`.

---

## Verification

```bash
# Simulate a diff where only docs changed — expect should_build=false
GITHUB_BASE_SHA=HEAD~1 GITHUB_HEAD_SHA=HEAD \
  git diff --name-only HEAD~1..HEAD   # confirm only docs/* files

pnpm tsx scripts/should-build-pages.ts
# => Checking 3 changed file(s) against watch paths…
# => should_build=false (written to GITHUB_OUTPUT)

# Simulate a web change — expect should_build=true
touch apps/web/src/index.ts
git add -A && git commit -m "chore: trigger test"
GITHUB_BASE_SHA=HEAD~1 GITHUB_HEAD_SHA=HEAD pnpm tsx scripts/should-build-pages.ts
# => should_build=true
```

---

## Related

- `cloudflare-pages-build-cache-optimization.md`
- `cloudflare-pages-build-matrix-strategy.md`
- `monorepo-deploy-pipeline-turborepo.md`
- `wrangler-pages-direct-upload-ci.md`

---

## Sources

- Cloudflare Pages docs — Build configuration: https://developers.cloudflare.com/pages/configuration/build-configuration/
- Turborepo `--filter` and `--dry` flags: https://turbo.build/repo/docs/reference/run
- GitHub Actions `paths:` trigger filter: https://docs.github.com/en/actions/writing-workflows/workflow-syntax-for-github-actions#onpushpull_requestpull_request_targetpathspaths-ignore
