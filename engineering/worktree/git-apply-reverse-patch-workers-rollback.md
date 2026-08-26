# Git Apply Reverse Patch: Surgical Rollback for Workers Deployments

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

Production is down. The offending change is buried inside a commit that also includes unrelated refactors—`git revert` would revert all of it, and a new commit touching files unrelated to the incident could introduce noise or trigger downstream CI jobs. `git format-patch` + `git apply --reverse` lets you generate a patch for exactly the changed lines you want to undo, apply it surgically to the working tree without creating any extra commit history, then immediately `wrangler deploy` the undone artifact.

## Context

`git apply --reverse` reads a unified diff (patch file) and applies its inverse: additions become deletions, deletions become additions, and context lines stay as anchors. Unlike `git revert`, it operates on the working tree only—no commit is created until you choose to make one. This makes it ideal for incident response where you want to validate the rollback locally or in a test environment before committing and pushing. The approach also works across cherry-picked commits or changes that have been squashed.

---

## Step 1 — Identify the Offending Commit and Generate a Patch

```bash
#!/usr/bin/env bash
set -euo pipefail

# Identify the bad commit via git log
git log --oneline --since="2 hours ago" workers/api/src/

# Generate a patch for that specific commit
BAD_COMMIT="a3f9c2b"
git format-patch -1 "$BAD_COMMIT" -o /tmp/rollback-patches/

# Or generate a patch for only specific files within that commit:
git diff "${BAD_COMMIT}^" "$BAD_COMMIT" -- \
  workers/api/src/handlers/payments.ts \
  workers/api/src/middleware/auth.ts \
  > /tmp/rollback-patches/targeted-rollback.patch

echo "Patch generated:"
cat /tmp/rollback-patches/targeted-rollback.patch | head -40
```

## Step 2 — Dry-Run the Reverse Application

Always check with `--check` before mutating the working tree. This verifies the patch applies cleanly given the current state of the files:

```bash
#!/usr/bin/env bash
PATCH=/tmp/rollback-patches/targeted-rollback.patch

# --check: test application without writing files
git apply --reverse --check "$PATCH"
EXIT=$?

if [[ $EXIT -ne 0 ]]; then
  echo "Reverse patch does not apply cleanly."
  echo "The file may have diverged further since the bad commit."
  echo "Options:"
  echo "  1. Use --3way to attempt a three-way merge: git apply --reverse --3way $PATCH"
  echo "  2. Manually edit the file and skip git apply"
  exit 1
fi

echo "Reverse patch applies cleanly — proceeding."
```

## Step 3 — Apply Reverse Patch and Stage

```bash
#!/usr/bin/env bash
PATCH=/tmp/rollback-patches/targeted-rollback.patch

# Apply the reverse patch to the working tree
git apply --reverse "$PATCH"

# Review the diff before staging
git diff

# Stage only the rolled-back files (not any unrelated local changes)
git add workers/api/src/handlers/payments.ts
git add workers/api/src/middleware/auth.ts

git status
```

## Step 4 — Validate Locally Before Deploying

Run the Worker in a local Miniflare environment against the rolled-back code before touching production:

```typescript
// scripts/smoke-test-rollback.ts
import { execSync } from "child_process";

const endpoints = [
  { path: "/health", expectedStatus: 200 },
  { path: "/api/payments/ping", expectedStatus: 200 },
  { path: "/api/auth/verify", expectedStatus: 401 }, // unauthenticated should 401
];

async function runSmokeTests(baseUrl: string): Promise<void> {
  const failures: string[] = [];

  for (const { path, expectedStatus } of endpoints) {
    const res = await fetch(`${baseUrl}${path}`);
    if (res.status !== expectedStatus) {
      failures.push(
        `${path}: expected ${expectedStatus}, got ${res.status}`
      );
    }
  }

  if (failures.length > 0) {
    console.error("Smoke test failures after rollback:");
    failures.forEach((f) => console.error(" ", f));
    process.exit(1);
  }

  console.log(`All ${endpoints.length} smoke tests passed.`);
}

// Start Miniflare in the background, then test
const server = execSync(
  "npx wrangler dev --port 8788 &",
  { shell: "/bin/bash", encoding: "utf8" }
);

await new Promise((r) => setTimeout(r, 3000)); // wait for Wrangler to boot
await runSmokeTests("http://localhost:8788");
```

## Step 5 — Commit the Rollback and Deploy

```bash
#!/usr/bin/env bash
BAD_COMMIT="a3f9c2b"
TIMESTAMP=$(date -u +"%Y-%m-%dT%H:%M:%SZ")

# Commit with a clear incident reference in the message
git commit -m "revert(api): rollback payments handler to pre-${BAD_COMMIT} state

Incident: INC-2847 — payments handler returning 500 after ${BAD_COMMIT}
Rolled back via git apply --reverse on targeted patch (payments.ts, auth.ts only).
Unrelated refactors in ${BAD_COMMIT} (metrics.ts, types.ts) are retained.

Rollback-Of: ${BAD_COMMIT}
Rolled-Back-At: ${TIMESTAMP}"

# Deploy immediately to production
wrangler deploy --env production

# Tag the rollback for post-incident reference
git tag "rollback/inc-2847/$(date -u +%Y%m%dT%H%M%S)" HEAD
git push origin HEAD --tags
```

## Scripted Rollback Pipeline (GitHub Actions)

For teams that want an on-demand rollback trigger without manual SSH:

```yaml
# .github/workflows/emergency-rollback.yml
name: Emergency Rollback
on:
  workflow_dispatch:
    inputs:
      bad_commit:
        description: "SHA of the commit to reverse"
        required: true
      target_files:
        description: "Space-separated list of files to patch (leave blank for full commit)"
        required: false
      environment:
        description: "Wrangler environment to deploy to"
        default: "production"

jobs:
  rollback:
    runs-on: ubuntu-latest
    environment: ${{ inputs.environment }}
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0

      - name: Generate reverse patch
        run: |
          FILES="${{ inputs.target_files }}"
          if [[ -n "$FILES" ]]; then
            git diff "${{ inputs.bad_commit }}^" "${{ inputs.bad_commit }}" \
              -- $FILES > /tmp/rollback.patch
          else
            git format-patch -1 "${{ inputs.bad_commit }}" \
              --stdout > /tmp/rollback.patch
          fi

      - name: Apply reverse patch
        run: |
          git apply --reverse --check /tmp/rollback.patch
          git apply --reverse /tmp/rollback.patch

      - name: Commit rollback
        run: |
          git config user.email "ci@example.com"
          git config user.name "Emergency Rollback Bot"
          git add -u
          git commit -m "emergency revert: reverse patch of ${{ inputs.bad_commit }}"

      - name: Deploy
        env:
          CLOUDFLARE_API_TOKEN: ${{ secrets.CLOUDFLARE_API_TOKEN }}
        run: |
          npm ci
          wrangler deploy --env ${{ inputs.environment }}
```

---

## Anti-patterns

- **Using `git apply --reverse` as a substitute for proper testing.** The reverse patch repairs lines of code but not database state, KV namespace values, or D1 schema migrations. Always pair with a data-layer rollback plan.
- **Reversing a patch on a file that has changed further since the bad commit.** Without `--3way`, Git will reject a patch that doesn't match the context lines exactly. Use `--3way` to get a merge-conflict view rather than a hard failure.
- **Committing reverse patches directly to `main` without a PR.** In non-incident scenarios, a reverse-patch commit should go through normal review. Only bypass for declared P0/P1 incidents with postmortem tracking.
- **Losing the patch file after incident resolution.** Store the patch in the postmortem artifact: attach it to the incident ticket or add it to `.github/incident-patches/`.

## Gotchas

- `git format-patch -1` generates a patch with email headers. `git diff` generates a raw unified diff. `git apply` accepts both, but `--signoff` only works with the `format-patch` format.
- If the bad commit was squash-merged, `git format-patch -1 <merge-commit>` patches the squash result, not individual changes. Use `git diff <merge-commit>^..<merge-commit>` with `--` path filters for targeted rollback.
- `git apply --reverse` does not stage files. You must `git add` affected files before committing. Use `git apply --reverse --index` to apply and stage in one step.
- On Windows CI runners, line endings (CRLF vs LF) can cause `--check` to fail even though the patch is semantically correct. Add `--ignore-whitespace` with caution—it may mask real conflicts.

## Verification

```bash
# 1. Confirm the reverse patch leaves no leftover conflict markers
grep -r "<<<<<<\|>>>>>>" workers/api/src/ && echo "CONFLICTS FOUND" || echo "Clean"

# 2. Run type-check on the rolled-back files
npx tsc --noEmit

# 3. Run unit tests for the affected modules
npx vitest run workers/api/src/handlers/payments.test.ts

# 4. Verify deployment reached production
wrangler deployments list --env production | head -3
```

## Related

- `git-revert-safe-rollback-workers-production.md`
- `git-format-patch-review-workers-email-workflow.md`
- `wrangler-rollback-git-tag-workflow.md`
- `git-tag-semantic-versioning-workers-deploy-gates.md`
- `github-actions-wrangler-deploy-pipeline.md`

## Sources

- Git documentation: `git-apply(1)`, `git-format-patch(1)`
- Cloudflare Workers: Rollback with Wrangler https://developers.cloudflare.com/workers/configuration/versions-and-deployments/rollbacks/
- Pro Git Book: "Generating a Patch with git format-patch"
