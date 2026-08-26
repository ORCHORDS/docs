# Automated PR Labeling Based on Changed Files

- **Date**: 2026-08-22
- **Author**: example.com
- **Status**: production

---

## Symptom / Use-case

Pull requests accumulate without any categorization, so reviewers cannot triage quickly.
Humans forget to apply labels, or apply the wrong ones, causing dashboards and
release-notes generators to misclassify work. Engineers spend time on manual
housekeeping that a workflow can own entirely.

The goal: every PR receives one or more labels the moment it is opened or its file
list changes, based purely on which paths were touched — zero human action required.

---

## Context

GitHub exposes `pull_request` and `pull_request_target` webhook events that fire on
`opened`, `synchronize`, and `reopened` actions. The `actions/labeler` action (v5+)
consumes a YAML configuration that maps label names to file-path glob patterns. It
compares the PR diff against those patterns and applies matching labels atomically.

Key constraints:
- Labels must already exist in the repository before the action can apply them.
- `actions/labeler` v5 changed the config schema (array syntax replaced the flat map);
  mixing v4 configs with v5 action references silently mislabels everything.
- On `pull_request_target`, the action runs in the context of the base branch, which
  matters for forks — the labeler config comes from the base, not the contributor's fork.
- The action requires `pull-requests: write` permission in the GITHUB_TOKEN scope.

---

## Workflow Setup

### 1. Create the workflow file

```yaml
# .github/workflows/label-pr.yml
name: Label PR by changed files

on:
  pull_request:
    types: [opened, synchronize, reopened]

permissions:
  contents: read
  pull-requests: write

jobs:
  label:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/labeler@v5
        with:
          repo-token: ${{ secrets.GITHUB_TOKEN }}
          configuration-path: .github/labeler.yml
          sync-labels: true   # removes labels that no longer match after a push
```

`sync-labels: true` is important: without it a label applied on the first push stays
even when the contributor later removes the file, leaving a stale categorization.

### 2. Define the labeler configuration

```yaml
# .github/labeler.yml  (actions/labeler v5 array syntax)

area/frontend:
  - changed-files:
    - any-glob-to-any-file:
      - 'apps/web/**'
      - 'packages/ui/**'
      - '**/*.css'
      - '**/*.scss'

area/backend:
  - changed-files:
    - any-glob-to-any-file:
      - 'apps/api/**'
      - 'packages/core/**'
      - 'packages/db/**'

area/infrastructure:
  - changed-files:
    - any-glob-to-any-file:
      - 'infra/**'
      - '.github/workflows/**'
      - 'Dockerfile*'
      - 'docker-compose*.yml'
      - 'wrangler.toml'
      - 'wrangler.*.toml'

area/docs:
  - changed-files:
    - any-glob-to-any-file:
      - 'docs/**'
      - '*.md'
      - 'documentation/**'

area/tests:
  - changed-files:
    - any-glob-to-any-file:
      - '**/*.test.ts'
      - '**/*.spec.ts'
      - '**/__tests__/**'
      - 'e2e/**'
      - 'cypress/**'

size/breaking-change:
  - changed-files:
    - any-glob-to-any-file:
      - '**/migrations/**'
      - '**/schema.prisma'
      - '**/openapi.yaml'
      - '**/openapi.json'

dependencies:
  - changed-files:
    - any-glob-to-any-file:
      - 'package.json'
      - 'package-lock.json'
      - 'pnpm-lock.yaml'
      - 'yarn.lock'
      - '**/package.json'
```

### 3. Pre-create labels in the repository

Labels must exist before the action can apply them. Bootstrap with the GitHub CLI:

```bash
# Create all required labels idempotently
labels=(
  "area/frontend:0075ca:Frontend and UI changes"
  "area/backend:e4e669:API and server-side changes"
  "area/infrastructure:d93f0b:CI, deployment and infra changes"
  "area/docs:0075ca:Documentation updates"
  "area/tests:bfd4f2:Test-only changes"
  "size/breaking-change:b60205:May require migration or versioning"
  "dependencies:0075ca:Dependency version changes"
)

for entry in "${labels[@]}"; do
  IFS=':' read -r name color description <<< "$entry"
  gh label create "$name" --color "$color" --description "$description" \
    --force  # --force updates if already exists
done
```

Commit this bootstrap script to `scripts/create-labels.sh` and run it once per
repository, or call it from your repo-provisioning automation.

---

## Multi-label and Compound Rules

`actions/labeler` v5 supports `all-globs-to-all-files` (every listed glob must match
every changed file — useful for "only docs changed") and `any-glob-to-any-file`
(at least one glob matches at least one changed file — the common case).

```yaml
# Label only when ALL changed files are documentation
docs-only:
  - changed-files:
    - all-globs-to-all-files:
      - '**/*.md'
      - 'docs/**'

# Label when the PR touches both frontend and backend (full-stack)
area/fullstack:
  - changed-files:
    - any-glob-to-any-file:
      - 'apps/web/**'
  - changed-files:
    - any-glob-to-any-file:
      - 'apps/api/**'
```

Multiple top-level list entries under a label are ANDed together. This lets you
build compound conditions without writing custom scripts.

---

## Custom Labeler Script for Advanced Logic

For rules the YAML DSL cannot express (e.g., "label based on number of files changed"
or "label based on PR title regex"), write a small Node.js script:

```typescript
// .github/scripts/label-pr.ts
import * as core from '@actions/core';
import * as github from '@actions/github';

async function run(): Promise<void> {
  const token = process.env.GITHUB_TOKEN!;
  const octokit = github.getOctokit(token);
  const { context } = github;

  if (!context.payload.pull_request) return;

  const pr = context.payload.pull_request;
  const { owner, repo } = context.repo;
  const prNumber = pr.number;

  // Fetch changed files (paginate for large PRs)
  const files = await octokit.paginate(
    octokit.rest.pulls.listFiles,
    { owner, repo, pull_number: prNumber, per_page: 100 }
  );

  const labelsToAdd: string[] = [];

  // Rule: large PR warning
  if (files.length > 50) {
    labelsToAdd.push('size/xl');
  } else if (files.length > 20) {
    labelsToAdd.push('size/large');
  }

  // Rule: migration alert
  const hasMigration = files.some(f =>
    f.filename.includes('/migrations/') && f.filename.endsWith('.sql')
  );
  if (hasMigration) {
    labelsToAdd.push('requires/migration-review');
  }

  // Rule: public API surface changed
  const touchesPublicApi = files.some(f =>
    f.filename.startsWith('packages/') &&
    (f.filename.endsWith('index.ts') || f.filename.endsWith('index.d.ts'))
  );
  if (touchesPublicApi) {
    labelsToAdd.push('area/public-api');
  }

  if (labelsToAdd.length > 0) {
    await octokit.rest.issues.addLabels({
      owner,
      repo,
      issue_number: prNumber,
      labels: labelsToAdd,
    });
    core.info(`Applied labels: ${labelsToAdd.join(', ')}`);
  }
}

run().catch(core.setFailed);
```

```yaml
# Workflow step calling the custom script
- name: Apply advanced labels
  env:
    GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
  run: npx ts-node .github/scripts/label-pr.ts
```

---

## Anti-patterns

**Hardcoding label strings in multiple places.** Define label names in a single
source-of-truth file (e.g., `.github/labels.json`) parsed by both the bootstrap
script and the workflow. Drift causes silent failures when a label is renamed.

**Using `pull_request_target` without auditing fork trust.** The `pull_request_target`
event has elevated permissions and runs in the base context. Combine it with a
condition that checks `github.event.pull_request.head.repo.full_name ==
github.repository` before running sensitive steps.

**Omitting `sync-labels: true`.** Without sync, labels accumulate as the PR evolves.
A PR that starts touching migrations and then reverts the migration file will
permanently carry `size/breaking-change`.

**Relying on labels as the only signal in protected branch rules.** Labels can be
added by anyone with triage access. Do not gate mergeability solely on label presence
without also protecting that label via a status check.

---

## Gotchas

- The labeler action only fires on the `pull_request` or `pull_request_target` event.
  It does not run on `push`, `merge_group`, or manual dispatch — do not expect labels
  to appear on pushes directly to the default branch.

- Glob syntax in `labeler.yml` uses `micromatch`, not shell glob. In particular,
  `**` crosses directory boundaries including the root, but patterns must not start
  with `/`. Use `apps/web/**` not `/apps/web/**`.

- Actions/labeler v5 requires `actions/labeler@v5` — pinning to a SHA is safer for
  supply-chain hygiene: `actions/labeler@<full-sha>`.

- The GitHub API rate-limit for label operations is shared with all other API calls
  in a workflow run. High-volume repos with many concurrent PRs may hit secondary
  rate limits; add `retry-on-snapshot-absent: true` or implement exponential backoff
  in custom scripts.

- Label operations are **not** atomic with CI status checks. A required status check
  that reads labels may see the PR before labels are applied if the label workflow
  and the status check workflow race.

---

## Verification

```bash
# Confirm labeler config parses correctly (requires yq)
yq '.[] | keys' .github/labeler.yml

# Dry-run: list files that would trigger each label
# (replace 'main' with your base branch)
gh pr diff <PR-NUMBER> --name-only | \
  while read -r file; do echo "$file"; done

# Check labels on a PR
gh pr view <PR-NUMBER> --json labels --jq '.labels[].name'

# Audit label application history in workflow logs
gh run list --workflow=label-pr.yml --limit 10

# Verify all expected labels exist in the repo
gh label list --limit 100 | grep "area/"
```

---

## Related

- `feature-branch-naming-automated-pr-checks.md` — branch naming conventions that
  complement labeling
- `conventional-commits-2026.md` — commit convention that drives release-note
  generation downstream of labels
- `pr-readiness-checklist-workers-projects.md` — label-gated readiness gates
- `github-codeowners-best-practices.md` — CODEOWNERS pairs with labels for review
  routing

---

## Sources

- GitHub Actions Labeler v5 documentation: https://github.com/actions/labeler
- GitHub REST API — Labels: https://docs.github.com/en/rest/issues/labels
- `micromatch` glob reference: https://github.com/micromatch/micromatch
- GitHub Actions permissions reference: https://docs.github.com/en/actions/security-guides/automatic-token-authentication
