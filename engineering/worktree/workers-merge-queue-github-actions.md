# Merge Queue Setup for High-Velocity Cloudflare Workers Teams with GitHub Actions

Date: 2026-08-24
Author: example.com
Status: production

---

## Symptom / Use-case

Your Workers team has 5+ developers all targeting `main`. PRs stack up, CI runs against stale base commits, and two PRs that both pass CI individually break `main` when they land in the wrong order. Manual serialization ("wait for mine to merge first") is error-prone and blocks velocity. You need a system that queues PRs, merges them in order, re-runs CI against the queue state, and handles failures without blocking the rest of the queue.

## Context

GitHub's native merge queue (generally available since 2023) addresses this by:

1. When a PR is approved and its CI passes, a developer adds it to the merge queue instead of merging directly.
2. GitHub creates a temporary "queue branch" rebased on top of the current queue state.
3. CI runs against that queue branch.
4. If CI passes, GitHub merges automatically; if it fails, only the failing PR is ejected.

For Cloudflare Workers teams this is particularly valuable because:
- `wrangler deploy --dry-run` in CI catches `wrangler.toml` conflicts before production
- Durable Object migration conflicts surface during queue CI, not post-merge
- Batched merges reduce total CI minutes (GitHub can merge multiple PRs in one batch)

## Solution

### 1. Enable merge queue in branch protection

Via GitHub CLI:

```bash
# Enable merge queue on main branch
# Note: the merge queue options are in the ruleset API (newer) not the classic protection API

# First, check current rulesets
gh api repos/example-org/example-repo/rulesets

# Create a ruleset with merge queue enabled
gh api \
  --method POST \
  repos/example-org/example-repo/rulesets \
  --field name='main-protection' \
  --field target='branch' \
  --field enforcement='active' \
  --field conditions='{"ref_name":{"include":["refs/heads/main"],"exclude":[]}}' \
  --field rules='[
    {"type":"merge_queue","parameters":{
      "merge_method":"squash",
      "min_entries_to_merge":1,
      "max_entries_to_merge":5,
      "min_entries_to_merge_wait_minutes":5,
      "grouping_strategy":"ALLGREEN",
      "check_response_timeout_minutes":60
    }},
    {"type":"required_status_checks","parameters":{
      "required_status_checks":[
        {"context":"typecheck"},
        {"context":"lint"},
        {"context":"test"},
        {"context":"dry-run-deploy"}
      ],
      "strict_required_status_checks_policy":false
    }},
    {"type":"pull_request","parameters":{
      "required_approving_review_count":1,
      "dismiss_stale_reviews_on_push":true,
      "require_code_owner_review":false,
      "require_last_push_approval":true
    }}
  ]'
```

### 2. CI workflow that runs in merge queue context

The merge queue creates branches named `gh-readonly-queue/main/pr-<N>-<sha>`. CI must run on these branches:

```yaml
# .github/workflows/ci.yml
name: CI

on:
  pull_request:
    branches: [main]
  merge_group:              # <-- this trigger fires in the merge queue
    types: [checks_requested]

jobs:
  typecheck:
    name: TypeScript
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with: { node-version: '22', cache: 'npm' }
      - run: npm ci
      - run: npx tsc --noEmit

  lint:
    name: ESLint
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with: { node-version: '22', cache: 'npm' }
      - run: npm ci
      - run: npx eslint . --max-warnings 0

  test:
    name: Vitest
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with: { node-version: '22', cache: 'npm' }
      - run: npm ci
      - run: npx vitest run --reporter=verbose --coverage

      - name: Upload coverage
        uses: actions/upload-artifact@v4
        if: always()
        with:
          name: coverage-${{ github.sha }}
          path: coverage/

  dry-run-deploy:
    name: Wrangler dry-run
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with: { node-version: '22', cache: 'npm' }
      - run: npm ci
      - run: npx wrangler deploy --dry-run --outdir dist/
        env:
          CLOUDFLARE_API_TOKEN: ${{ secrets.CF_API_TOKEN }}
          CLOUDFLARE_ACCOUNT_ID: ${{ secrets.CF_ACCOUNT_ID }}

      - name: Check bundle size
        run: |
          BUNDLE_SIZE=$(stat -c%s dist/index.js 2>/dev/null || stat -f%z dist/index.js)
          MAX_SIZE=$((1 * 1024 * 1024))  # 1MB
          if [ "$BUNDLE_SIZE" -gt "$MAX_SIZE" ]; then
            echo "Bundle size ${BUNDLE_SIZE} bytes exceeds limit ${MAX_SIZE} bytes"
            exit 1
          fi
          echo "Bundle size: ${BUNDLE_SIZE} bytes (OK)"
```

### 3. Auto-deploy on merge to main

```yaml
# .github/workflows/deploy-staging.yml
name: Deploy to Staging

on:
  push:
    branches: [main]

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-node@v4
        with: { node-version: '22', cache: 'npm' }

      - run: npm ci

      - name: Deploy to staging
        run: npx wrangler deploy --env staging
        env:
          CLOUDFLARE_API_TOKEN: ${{ secrets.CF_API_TOKEN }}
          CLOUDFLARE_ACCOUNT_ID: ${{ secrets.CF_ACCOUNT_ID }}

      - name: Smoke test staging
        run: |
          sleep 5  # propagation delay
          STATUS=$(curl -s -o /dev/null -w "%{http_code}" https://api-gateway-staging.<account>.workers.dev/healthz)
          if [ "$STATUS" != "200" ]; then
            echo "Smoke test failed: HTTP $STATUS"
            exit 1
          fi
          echo "Smoke test passed: HTTP $STATUS"
```

### 4. Priority queue for hotfixes

GitHub merge queue does not natively support priority. Implement priority by labeling PRs and using a separate workflow to bypass the standard queue wait:

```yaml
# .github/workflows/hotfix-fast-track.yml
name: Hotfix Fast-Track

on:
  pull_request:
    types: [labeled]
    branches: [main]

jobs:
  fast-track:
    if: github.event.label.name == 'priority:hotfix'
    runs-on: ubuntu-latest
    steps:
      - name: Add to merge queue immediately
        uses: actions/github-script@v7
        with:
          script: |
            // Add merge queue entry via GraphQL
            const mutation = `
              mutation EnableAutoMerge($pullRequestId: ID!) {
                enablePullRequestAutoMerge(input: {
                  pullRequestId: $pullRequestId,
                  mergeMethod: SQUASH
                }) {
                  pullRequest { number, title }
                }
              }
            `;
            const pr = await github.graphql(mutation, {
              pullRequestId: context.payload.pull_request.node_id
            });
            console.log('Fast-tracked:', JSON.stringify(pr));
```

### 5. Merge queue failure handling

```typescript
// scripts/monitor-merge-queue.ts
// Poll for merge queue failures and post Slack notifications

import { Octokit } from '@octokit/rest';

const octokit = new Octokit({ auth: process.env.GITHUB_TOKEN });

interface QueueEntry {
  url: string;
  headSha: string;
  pr: { number: number; title: string; user: string };
}

async function checkMergeQueueFailures(
  owner: string,
  repo: string
): Promise<void> {
  // List recent failed check runs on merge queue branches
  const { data: branches } = await octokit.repos.listBranches({ owner, repo });
  const queueBranches = branches.filter((b) =>
    b.name.startsWith('gh-readonly-queue/')
  );

  for (const branch of queueBranches) {
    const { data: checkRuns } = await octokit.checks.listForRef({
      owner,
      repo,
      ref: branch.commit.sha,
    });

    const failures = checkRuns.check_runs.filter(
      (run) => run.conclusion === 'failure'
    );

    if (failures.length > 0) {
      console.log(
        `Merge queue failure on ${branch.name}:`,
        failures.map((f) => f.name)
      );
      // Post to Slack webhook here
    }
  }
}

checkMergeQueueFailures('orchords', 'api-gateway').catch(console.error);
```

### 6. Merge queue metrics tracking

```yaml
# .github/workflows/queue-metrics.yml
name: Merge Queue Metrics

on:
  schedule:
    - cron: '0 9 * * 1-5'   # Weekday mornings
  workflow_dispatch:

jobs:
  metrics:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Collect merge queue stats
        uses: actions/github-script@v7
        with:
          script: |
            const since = new Date();
            since.setDate(since.getDate() - 7);

            // Count PRs merged via merge queue in last 7 days
            const { data: prs } = await github.rest.pulls.list({
              owner: 'orchords',
              repo: 'api-gateway',
              state: 'closed',
              sort: 'updated',
              direction: 'desc',
              per_page: 100
            });

            const merged = prs.filter(pr =>
              pr.merged_at &&
              new Date(pr.merged_at) > since
            );

            const avgTimeToMerge = merged.reduce((sum, pr) => {
              const created = new Date(pr.created_at).getTime();
              const mergedAt = new Date(pr.merged_at!).getTime();
              return sum + (mergedAt - created);
            }, 0) / (merged.length || 1);

            const hours = Math.round(avgTimeToMerge / 3_600_000);

            core.summary
              .addHeading('Weekly Merge Queue Metrics', 2)
              .addTable([
                [{data: 'Metric', header: true}, {data: 'Value', header: true}],
                ['PRs merged (7d)', String(merged.length)],
                ['Avg time to merge', `${hours}h`],
              ])
              .write();
```

## Implementation Details

- The `merge_group` trigger in CI is what makes GitHub Actions aware of merge queue context. Without it, the required status checks never get a result for the queue branch and the merge queue stalls indefinitely.
- `grouping_strategy: ALLGREEN` means GitHub only batches PRs when all queued entries have passing CI. `HEADGREEN` allows batching as soon as the head of the queue passes — faster but risks merging a later PR without its CI results.
- `max_entries_to_merge: 5` caps the batch size. A batch of 5 means a single bad PR can block up to 4 others; lower this for critical repositories.
- `min_entries_to_merge_wait_minutes: 5` gives late arrivals a window to join the current batch before it runs, reducing total CI invocations.
- The Wrangler dry-run in CI is especially important in the merge queue context: two PRs might each modify `wrangler.toml` in compatible ways individually but conflict when combined in a batch.

## Anti-patterns

- **Not adding `merge_group` trigger**: the merge queue creates a synthetic branch; without this trigger, CI never runs on it and required checks are never satisfied.
- **Setting `max_entries_to_merge` too high**: batches of 10+ make failure diagnosis hard — which PR in the batch broke CI?
- **Using `merge_group` trigger without required status checks**: the queue runs CI but nothing gates on the result; PRs merge regardless.
- **Bypassing the queue with direct pushes to `main`**: defeats the purpose; enforce `allow_force_pushes: false` and `restrictions` so even admins must go through the queue.

## Gotchas

- GitHub merge queues are only available on public repositories or repositories on GitHub Team / Enterprise plans.
- If a required check is renamed in CI (e.g. job `test` renamed to `vitest`), the branch protection rule still requires the old name and the queue will stall. Update both the CI job name and the required status check name atomically.
- When a merge queue batch fails, GitHub ejects PRs from the batch one by one using binary search, re-running CI for each half. This can consume significant CI minutes for large batches.
- The GraphQL `enablePullRequestAutoMerge` mutation used in the hotfix fast-track requires the PR to already have passing CI and an approval — it cannot skip queue requirements, only remove the manual "Add to merge queue" step.

## Verification

```bash
# Check merge queue status on main
gh api repos/example-org/example-repo/merge-queue | jq .

# List active merge queue entries
gh api repos/example-org/example-repo/merge-queue/entries | jq '.[].pull_request.number'

# Verify the merge_group trigger is in CI
grep -A3 'merge_group' .github/workflows/ci.yml

# Check rulesets are active
gh api repos/example-org/example-repo/rulesets | jq '.[].enforcement'
```

## Related

- `documentation/categories/worktree/workers-trunk-based-development-workflow.md`
- `documentation/categories/worktree/workers-release-branch-strategy.md`
- `documentation/categories/worktree/workers-conventional-commits-enforcement.md`

## Sources

- https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/configuring-pull-request-merges/managing-a-merge-queue
- https://github.blog/changelog/2023-02-08-pull-request-merge-queue-is-now-generally-available/
- https://docs.github.com/en/graphql/reference/mutations#enablepullrequestautomerge
