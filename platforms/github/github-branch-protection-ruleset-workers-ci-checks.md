# Branch Protection Rulesets: Workers CI Checks

Date: 2026-08-23 / Author: example.com / Status: production

## Symptom / Use-case

A team deploys Cloudflare Workers from CI and wants to ensure no merge to `main` bypasses the
Workers deploy check or the Wrangler type-check step. Classic branch protection rules associate
required checks by name only — a misconfigured workflow in a fork can report the same check name
as passing and, in some edge configurations, satisfy the requirement. Repository rulesets support
`integration_id` binding on required checks, tying each check to the specific GitHub App that must
report it. This closes the spoofing gap and provides audit-ready configuration stored in version
control.

## Context

GitHub's ruleset API supports:

- `required_status_checks` with optional `integration_id` — only the bound app can satisfy the
  requirement; another app reporting the same name is rejected.
- `required_deployments` — requires a successful deployment to a named environment before merging.
- `non_fast_forward` and `deletion` — prevents force-pushes and branch deletion.

For a Workers CI pipeline the typical required checks are:

- `typecheck` — `pnpm tsc --noEmit` across all workers (GitHub Actions app, integration_id 15368)
- `test` — vitest unit tests (same app)
- `deploy-staging` — `wrangler deploy --env staging` (same app, runs in the `staging` environment)

The production Workers deploy is deliberately excluded from required checks; it runs after merge
via `push` to `main` so a Cloudflare API blip never blocks merges.

## Fetching the GitHub Actions Integration ID

The GitHub Actions app has a fixed integration_id of `15368`. Confirm it for your specific check
runs before hardcoding:

```typescript
// scripts/get-actions-integration-id.ts
const TOKEN = process.env.GITHUB_TOKEN!;
const OWNER = process.env.OWNER!;
const REPO = process.env.REPO!;

interface CheckRun {
  name: string;
  app: { id: number; slug: string } | null;
  conclusion: string | null;
}

interface CheckRunsResponse {
  check_runs: CheckRun[];
}

async function inspectCheckRuns(sha: string): Promise<void> {
  const res = await fetch(
    `https://api.github.com/repos/${OWNER}/${REPO}/commits/${sha}/check-runs`,
    {
      headers: {
        Authorization: `Bearer ${TOKEN}`,
        "X-GitHub-Api-Version": "2022-11-28",
      },
    }
  );
  const { check_runs } = (await res.json()) as CheckRunsResponse;
  for (const run of check_runs) {
    console.log(`${run.name.padEnd(30)} app_id=${run.app?.id} (${run.app?.slug})`);
  }
}

// Pass a recent commit SHA from a merged PR to list check run apps
await inspectCheckRuns(process.argv[2]);
```

```bash
pnpm tsx scripts/get-actions-integration-id.ts <sha>
# typecheck                       app_id=15368 (github-actions)
# test                            app_id=15368 (github-actions)
# deploy-staging                  app_id=15368 (github-actions)
```

## Creating the Ruleset via Script

Store this script in the repo and run it from CI when `scripts/configure-ruleset.ts` changes, so
ruleset configuration is tracked in version control and not managed only through the UI.

```typescript
// scripts/configure-branch-ruleset.ts
const TOKEN = process.env.GITHUB_TOKEN!;
const OWNER = process.env.OWNER!;
const REPO = process.env.REPO!;

const ACTIONS_APP_ID = 15368;

interface RulesetResponse {
  id: number;
  name: string;
}

async function upsertRuleset(): Promise<void> {
  // Check if a ruleset named "workers-ci-gate" already exists
  const listRes = await fetch(
    `https://api.github.com/repos/${OWNER}/${REPO}/rulesets`,
    {
      headers: {
        Authorization: `Bearer ${TOKEN}`,
        "X-GitHub-Api-Version": "2022-11-28",
      },
    }
  );
  const existing = (await listRes.json()) as RulesetResponse[];
  const current = existing.find((r) => r.name === "workers-ci-gate");

  const body = JSON.stringify({
    name: "workers-ci-gate",
    target: "branch",
    enforcement: "active",
    bypass_actors: [
      // Repo admins can bypass in break-glass emergencies
      { actor_id: 5, actor_type: "RepositoryRole", bypass_mode: "always" },
    ],
    conditions: {
      ref_name: {
        include: ["refs/heads/main"],
        exclude: [],
      },
    },
    rules: [
      {
        type: "required_status_checks",
        parameters: {
          strict_required_status_checks_policy: false,
          required_status_checks: [
            { context: "typecheck",      integration_id: ACTIONS_APP_ID },
            { context: "test",           integration_id: ACTIONS_APP_ID },
            { context: "deploy-staging", integration_id: ACTIONS_APP_ID },
          ],
        },
      },
      { type: "non_fast_forward" },
      { type: "deletion" },
    ],
  });

  const method = current ? "PUT" : "POST";
  const url = current
    ? `https://api.github.com/repos/${OWNER}/${REPO}/rulesets/${current.id}`
    : `https://api.github.com/repos/${OWNER}/${REPO}/rulesets`;

  const res = await fetch(url, {
    method,
    headers: {
      Authorization: `Bearer ${TOKEN}`,
      "Content-Type": "application/json",
      "X-GitHub-Api-Version": "2022-11-28",
    },
    body,
  });

  if (!res.ok) throw new Error(`${res.status}: ${await res.text()}`);
  const ruleset = (await res.json()) as RulesetResponse;
  console.log(`${current ? "Updated" : "Created"} ruleset "${ruleset.name}" id=${ruleset.id}`);
}

await upsertRuleset();
```

## CI Workflow Naming Convention

Check names in the ruleset must exactly match the `name:` field (or job `id` if `name` is absent)
as reported by GitHub Actions. Use explicit `name:` values to decouple the display name from the
job identifier.

```yaml
# .github/workflows/ci.yml
name: CI
on:
  pull_request:
  push:
    branches: [main]

jobs:
  typecheck:
    name: typecheck          # matches ruleset context exactly
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with: { node-version: 22, cache: pnpm }
      - run: pnpm install --frozen-lockfile
      - run: pnpm tsc --noEmit

  test:
    name: test
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with: { node-version: 22, cache: pnpm }
      - run: pnpm install --frozen-lockfile
      - run: pnpm vitest run

  deploy-staging:
    name: deploy-staging
    needs: [typecheck, test]
    runs-on: ubuntu-latest
    environment: staging
    if: github.event_name == 'pull_request' || github.event_name == 'merge_group'
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with: { node-version: 22, cache: pnpm }
      - run: pnpm install --frozen-lockfile
      - run: pnpm wrangler deploy --env staging
        env:
          CLOUDFLARE_API_TOKEN: ${{ secrets.CF_STAGING_API_TOKEN }}
```

## Auditing That Merged PRs Passed the Correct App

Run periodically to confirm no PR slipped through with a check reported by a different app.

```typescript
// scripts/audit-ruleset-compliance.ts
const TOKEN = process.env.GITHUB_TOKEN!;
const OWNER = process.env.OWNER!;
const REPO = process.env.REPO!;
const REQUIRED_CHECKS = ["typecheck", "test", "deploy-staging"];
const ACTIONS_APP_ID = 15368;

interface PullRequest { number: number; merge_commit_sha: string | null }
interface CheckRun {
  name: string;
  conclusion: string | null;
  app: { id: number } | null;
}

async function get<T>(url: string): Promise<T> {
  const res = await fetch(url, {
    headers: {
      Authorization: `Bearer ${TOKEN}`,
      "X-GitHub-Api-Version": "2022-11-28",
    },
  });
  return res.json() as Promise<T>;
}

const prs = await get<PullRequest[]>(
  `https://api.github.com/repos/${OWNER}/${REPO}/pulls?state=closed&per_page=20`
);

let violations = 0;

for (const pr of prs.filter((p) => p.merge_commit_sha)) {
  const { check_runs } = await get<{ check_runs: CheckRun[] }>(
    `https://api.github.com/repos/${OWNER}/${REPO}/commits/${pr.merge_commit_sha}/check-runs`
  );

  for (const name of REQUIRED_CHECKS) {
    const run = check_runs.find((r) => r.name === name);
    if (!run) {
      console.warn(`PR #${pr.number}: MISSING check "${name}"`);
      violations++;
    } else if (run.conclusion !== "success") {
      console.warn(`PR #${pr.number}: "${name}" conclusion=${run.conclusion}`);
      violations++;
    } else if (run.app?.id !== ACTIONS_APP_ID) {
      console.warn(
        `PR #${pr.number}: "${name}" reported by unexpected app id=${run.app?.id}`
      );
      violations++;
    } else {
      console.log(`PR #${pr.number}: OK ${name}`);
    }
  }
}

if (violations > 0) {
  console.error(`\n${violations} violation(s) found`);
  process.exit(1);
}
console.log("\nAll checks passed the correct app");
```

## Anti-patterns

- Using classic branch protection `required_status_checks` without `integration_id` — any workflow
  can report a check named `typecheck` as passing.
- Setting `strict_required_status_checks_policy: true` — requires the branch to be up to date
  before merging; on a busy `main` branch this creates a perpetual rebase loop. Use the merge
  queue for staleness guarantees instead.
- Requiring the production Workers deploy as a required status check — a Cloudflare API error
  blocks all merges. Require only the staging deploy; gate production behind an environment
  approval triggered after `push` to `main`.
- Managing the ruleset only through the UI — the configuration is not tracked in version control
  and silently drifts when admins make ad-hoc changes.

## Gotchas

- `bypass_actors` with `actor_type: "RepositoryRole"` and `actor_id: 5` maps to the Admin role.
  The mapping of role IDs to names is undocumented; confirm by calling
  `GET /repos/{owner}/{repo}/rulesets/{id}` after creation and checking what the UI shows.
- Renaming a job in the workflow YAML changes the check name reported to GitHub. The ruleset's
  `required_status_checks` entries must be updated simultaneously, otherwise the check requirement
  becomes permanently unresolvable for new PRs until the ruleset is patched.
- A ruleset with `enforcement: "evaluate"` runs in dry-run mode and reports insights but does not
  block merges. Use this to validate a new ruleset on a production repo before switching to
  `"active"`.
- Org-level rulesets take precedence over repo-level ones when they conflict. Confirm no org
  ruleset already requires a check of the same name under a different pattern or binding before
  adding a repo-level duplicate.

## Verification

```bash
# List all rulesets on the repo
gh api repos/:owner/:repo/rulesets --jq '.[].name'

# Inspect the workers-ci-gate ruleset in full
gh api repos/:owner/:repo/rulesets \
  --jq '.[] | select(.name == "workers-ci-gate")'

# Confirm what check runs are reported for the current tip of main
gh api repos/:owner/:repo/commits/main/check-runs \
  --jq '.check_runs[] | {name, conclusion, app_id: .app.id}'

# Run the compliance audit against the last 20 merged PRs
GITHUB_TOKEN=$(gh auth token) OWNER=myorg REPO=myrepo \
  pnpm tsx scripts/audit-ruleset-compliance.ts
```

## Related

- `github-rulesets-2026.md`
- `github-rulesets-migration-from-branch-protection.md`
- `github-required-status-checks.md`
- `github-merge-queue-workers-deploy-coordination.md`
- `github-actions-oidc-cloudflare.md`

## Sources

- https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-rulesets/available-rules-for-rulesets
- https://docs.github.com/en/rest/repos/rules
- https://docs.github.com/en/rest/checks/runs
- https://developers.cloudflare.com/workers/wrangler/commands/#deploy
