# GitHub Merge Queue: Workers Deploy Coordination

Date: 2026-08-23 / Author: example.com / Status: production

## Symptom / Use-case

A team enables GitHub's merge queue to guarantee that every commit to `main` has passed CI
against the latest tip. The existing Workers deploy workflow triggers on `push` to `main`, which
fires after the queue merges its batch — correct in isolation, but the deploy runs outside the
merge queue's validation context. Alternatively, teams put the production Workers deploy inside
the merge group check, causing Cloudflare API hiccups to block all merges site-wide.

## Context

GitHub's merge queue fires workflows under two distinct events:

- `merge_group` — a temporary branch `gh-readonly-queue/main/pr-N-sha-X` is created; CI runs to
  validate the candidate batch before it lands on `main`.
- `push` to `main` — fires after the queue's commit lands; the code is already merged.

The right place for a Workers deploy depends on blast radius:

- **Staging deploy** → inside `merge_group`, gated by the `staging` environment. Failure ejects
  the PR from the queue; no human intervention needed.
- **Production deploy** → after `push` to `main`, optionally behind an environment approval. A
  Cloudflare API error delays the deploy but does not block merges.

## Workflow Structure

```yaml
# .github/workflows/ci.yml
name: CI
on:
  pull_request:
  merge_group:
    types: [checks_requested]

jobs:
  typecheck:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with: { node-version: 22, cache: pnpm }
      - run: pnpm install --frozen-lockfile
      - run: pnpm tsc --noEmit

  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with: { node-version: 22, cache: pnpm }
      - run: pnpm install --frozen-lockfile
      - run: pnpm vitest run

  deploy-staging:
    needs: [typecheck, test]
    # Only deploy to staging inside the merge queue, not on plain PRs.
    if: github.event_name == 'merge_group'
    runs-on: ubuntu-latest
    environment: staging
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with: { node-version: 22, cache: pnpm }
      - run: pnpm install --frozen-lockfile
      - name: Deploy to staging
        id: deploy
        run: pnpm tsx scripts/deploy-staging.ts
        env:
          CLOUDFLARE_API_TOKEN: ${{ secrets.CF_STAGING_API_TOKEN }}
      - name: Rollback on failure
        if: failure() && steps.deploy.conclusion == 'failure'
        run: |
          git checkout HEAD^
          pnpm install --frozen-lockfile=false
          pnpm wrangler deploy --env staging
        env:
          CLOUDFLARE_API_TOKEN: ${{ secrets.CF_STAGING_API_TOKEN }}
```

```yaml
# .github/workflows/deploy-production.yml
name: Deploy Production
on:
  push:
    branches: [main]

jobs:
  deploy:
    runs-on: ubuntu-latest
    environment: production   # triggers approval gate if configured
    concurrency:
      group: deploy-production
      cancel-in-progress: false   # never cancel an in-flight production deploy
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with: { node-version: 22, cache: pnpm }
      - run: pnpm install --frozen-lockfile
      - run: pnpm wrangler deploy --env production
        env:
          CLOUDFLARE_API_TOKEN: ${{ secrets.CF_PROD_API_TOKEN }}
```

## Detecting Merge-Group Context in Deploy Scripts

When the staging deploy runs inside a merge group, `GITHUB_REF` points to the temporary branch.
Extract the originating PR number to tag the deployed Worker build.

```typescript
// scripts/deploy-staging.ts
import { execSync } from "node:child_process";

const ref = process.env.GITHUB_REF ?? "";
// Format: refs/heads/gh-readonly-queue/main/pr-42-sha-abc123
const prMatch = ref.match(/\/pr-(\d+)-/);
const prNumber = prMatch?.[1] ?? "unknown";
const sha = (process.env.GITHUB_SHA ?? "").slice(0, 7);

const cmd = [
  "pnpm wrangler deploy",
  "--env staging",
  `--var BUILD_PR:${prNumber}`,
  `--var BUILD_SHA:${sha}`,
].join(" ");

console.log(`Deploying staging from merge-group for PR #${prNumber} @ ${sha}`);
execSync(cmd, { stdio: "inherit" });
```

## Configuring Required Checks for the Merge Queue

Register the required status checks via the rulesets API so only merge-group runs can satisfy them.

```typescript
// scripts/configure-merge-queue-ruleset.ts
const TOKEN = process.env.GITHUB_TOKEN!;
const OWNER = process.env.OWNER!;
const REPO = process.env.REPO!;

// GitHub Actions app fixed integration_id
const ACTIONS_APP_ID = 15368;

async function createRuleset(): Promise<void> {
  const res = await fetch(
    `https://api.github.com/repos/${OWNER}/${REPO}/rulesets`,
    {
      method: "POST",
      headers: {
        Authorization: `Bearer ${TOKEN}`,
        "Content-Type": "application/json",
        "X-GitHub-Api-Version": "2022-11-28",
      },
      body: JSON.stringify({
        name: "merge-queue-required-checks",
        target: "branch",
        enforcement: "active",
        conditions: {
          ref_name: { include: ["refs/heads/main"], exclude: [] },
        },
        rules: [
          {
            type: "required_status_checks",
            parameters: {
              strict_required_status_checks_policy: false,
              required_status_checks: [
                { context: "typecheck",       integration_id: ACTIONS_APP_ID },
                { context: "test",            integration_id: ACTIONS_APP_ID },
                { context: "deploy-staging",  integration_id: ACTIONS_APP_ID },
              ],
            },
          },
          {
            type: "merge_queue",
            parameters: {
              check_response_timeout_minutes: 60,
              grouping_strategy: "ALLGREEN",
              max_entries_to_build: 5,
              max_entries_to_merge: 3,
              min_entries_to_merge: 1,
              min_entries_to_merge_wait_minutes: 5,
            },
          },
        ],
      }),
    }
  );

  if (!res.ok) throw new Error(`${res.status}: ${await res.text()}`);
  const ruleset = (await res.json()) as { id: number; name: string };
  console.log(`Created ruleset "${ruleset.name}" id=${ruleset.id}`);
}

await createRuleset();
```

## Handling Merge-Queue Transient Failures

The merge queue does not retry failed checks automatically; the PR must be re-added. Post a PR
comment when `deploy-staging` fails so the author knows to re-queue.

```typescript
// scripts/notify-queue-failure.ts
const TOKEN = process.env.GITHUB_TOKEN!;
const OWNER = process.env.GITHUB_REPOSITORY_OWNER!;
const REPO = process.env.GITHUB_REPOSITORY!.split("/")[1];

// Extract PR number from the merge-group ref
const ref = process.env.GITHUB_REF ?? "";
const prMatch = ref.match(/\/pr-(\d+)-/);
const prNumber = prMatch?.[1];
if (!prNumber) {
  console.log("Not in a merge group; skipping notification");
  process.exit(0);
}

await fetch(
  `https://api.github.com/repos/${OWNER}/${REPO}/issues/${prNumber}/comments`,
  {
    method: "POST",
    headers: {
      Authorization: `Bearer ${TOKEN}`,
      "Content-Type": "application/json",
      "X-GitHub-Api-Version": "2022-11-28",
    },
    body: JSON.stringify({
      body:
        `The merge queue staging deploy failed for this PR. ` +
        `Please re-add it to the queue once the issue is resolved.\n\n` +
        `**Workflow run:** ${process.env.GITHUB_SERVER_URL}/${OWNER}/${REPO}/actions/runs/${process.env.GITHUB_RUN_ID}`,
    }),
  }
);
console.log(`Posted failure comment on PR #${prNumber}`);
```

Add this as an `if: failure()` step in `deploy-staging`:

```yaml
      - name: Notify queue failure
        if: failure()
        run: pnpm tsx scripts/notify-queue-failure.ts
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
```

## Anti-patterns

- Making the production Workers deploy a required merge-queue check — a Cloudflare API blip
  blocks every merge until the API recovers.
- Triggering the production deploy on `merge_group` — the temporary branch is deleted after
  merging; the deployed Worker code is correct but the deploy source no longer exists in git.
- A single workflow on both `pull_request` and `merge_group` that skips the deploy with a
  complex `if` — easy to get wrong; keep PR validation and merge-group deploy in separate jobs.
- Setting `strict_required_status_checks_policy: true` in the merge queue ruleset — forces the
  queue to rebuild every PR against the absolute latest `main` on each new push, defeating
  batching.

## Gotchas

- The `merge_group` event is a separate trigger type. A workflow that lists only `pull_request`
  in its `on:` block never runs inside the merge queue and cannot satisfy merge-queue required
  checks.
- `GITHUB_REF` inside a merge group is `refs/heads/gh-readonly-queue/<base>/<details>`, not
  `refs/heads/main`. Code that checks `ref === 'refs/heads/main'` will not match.
- Required check names in the ruleset must exactly match the job `name:` field (or `id` if `name`
  is omitted) as reported by GitHub Actions, including case sensitivity.
- The merge queue does not retry failed checks. A transient Cloudflare API error that fails
  `deploy-staging` requires the PR author to manually re-add the PR to the queue.

## Verification

```bash
# Confirm required checks on the merge-queue ruleset
gh api repos/:owner/:repo/rulesets \
  --jq '.[] | select(.name == "merge-queue-required-checks") | .rules'

# List active merge-queue entries
gh api repos/:owner/:repo/merge-queue \
  --jq '.entries[].pull_request.number'

# Confirm staging Worker is on the expected SHA after a queue merge
pnpm wrangler deployments list --env staging | head -5
```

## Related

- `github-merge-queue-mechanics.md`
- `github-branch-protection-merge-queue.md`
- `github-environments-approval-gates.md`
- `github-actions-concurrency-groups-workers-deploy-queue.md`
- `github-branch-protection-ruleset-workers-ci-checks.md`

## Sources

- https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/configuring-pull-request-merges/managing-a-merge-queue
- https://docs.github.com/en/actions/writing-workflows/choosing-when-your-workflow-runs/events-that-trigger-workflows#merge_group
- https://developers.cloudflare.com/workers/wrangler/commands/#deploy
