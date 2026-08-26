# GitHub Actions Workflow Dispatch Approval Gate

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

You need a manual deployment or maintenance workflow that can only proceed after
a named human reviewer explicitly approves it. Environment protection rules handle
_scheduled_ or _push-triggered_ flows, but for `workflow_dispatch` triggers you
also want to capture the approver identity, log it to audit, and optionally post a
Slack message before execution begins. The naive pattern (just protecting the
environment) silently blocks the run; you want a rich, traceable gate.

---

## Context

`workflow_dispatch` lets any user with write access trigger a workflow. When the
target environment has required reviewers set, GitHub pauses the job at the
environment gate and notifies reviewers — but the UX is buried in the Actions tab.
A purpose-built approval gate workflow combines:

- An environment with required reviewers to enforce the gate.
- A dedicated approval-request job that runs first and posts visible notifications.
- The deploying job that only starts after the gate passes.
- Structured audit output written to the job summary.

This pattern is used for one-off Cloudflare Workers production deployments,
D1 schema migrations, and R2 bucket policy changes that should not run
automatically but still need CI-managed execution.

---

## Environment Setup

Create a `production-gate` environment in repo Settings → Environments.

```yaml
# .github/environments/production-gate.yml  (documentation only – environments
# are configured through the UI or the GitHub API, not committed YAML)
#
# Settings to apply:
#   Required reviewers: @org/platform-leads  (up to 6 teams/users)
#   Wait timer: 0 minutes
#   Deployment branches: main only
#   Prevent self-review: true   (reviewer ≠ dispatcher)
```

Using the API to create/update the environment:

```typescript
// scripts/ensure-gate-environment.ts
import { Octokit } from "@octokit/rest";

const octokit = new Octokit({ auth: process.env.GITHUB_TOKEN });

await octokit.rest.repos.createOrUpdateEnvironment({
  owner: "your-org",
  repo: "example project-monorepo",
  environment_name: "production-gate",
  reviewers: [
    { type: "Team", id: 123456 }, // platform-leads team ID
  ],
  deployment_branch_policy: {
    protected_branches: true,
    custom_branch_policies: false,
  },
});
```

---

## Workflow Structure

```yaml
# .github/workflows/manual-production-deploy.yml
name: Manual Production Deploy (Gated)

on:
  workflow_dispatch:
    inputs:
      worker_name:
        description: "Worker to deploy (e.g. api-gateway)"
        required: true
        type: string
      reason:
        description: "Reason for manual deploy (logged to audit)"
        required: true
        type: string
      dry_run:
        description: "Dry-run only — skip actual deployment"
        required: false
        type: boolean
        default: false

permissions:
  contents: read
  id-token: write      # OIDC for Cloudflare
  deployments: write   # Deployment API

jobs:
  # ── Stage 1: request approval (runs immediately, no gate) ──────────────────
  request-approval:
    name: Request Approval
    runs-on: ubuntu-24.04
    steps:
      - name: Post Slack approval request
        env:
          SLACK_WEBHOOK: ${{ secrets.SLACK_OPS_WEBHOOK }}
          DISPATCHER: ${{ github.actor }}
          WORKER: ${{ inputs.worker_name }}
          REASON: ${{ inputs.reason }}
          RUN_URL: ${{ github.server_url }}/${{ github.repository }}/actions/runs/${{ github.run_id }}
        run: |
          curl -fsSL -X POST "$SLACK_WEBHOOK" \
            -H 'Content-Type: application/json' \
            -d "$(jq -n \
              --arg dispatcher "$DISPATCHER" \
              --arg worker "$WORKER" \
              --arg reason "$REASON" \
              --arg url "$RUN_URL" \
              '{
                text: (":rocket: *Manual deploy requested* by `" + $dispatcher + "`\n" +
                       "Worker: `" + $worker + "`\n" +
                       "Reason: " + $reason + "\n" +
                       "<" + $url + "|Approve or reject here>")
              }')"

  # ── Stage 2: gated deploy (blocked until reviewer approves) ────────────────
  deploy:
    name: Deploy ${{ inputs.worker_name }}
    needs: request-approval
    runs-on: ubuntu-24.04
    environment: production-gate          # ← triggers the approval gate
    steps:
      - uses: actions/checkout@v4

      - name: Authenticate to Cloudflare via OIDC
        uses: cloudflare/wrangler-action@v3
        with:
          accountId: ${{ vars.CF_ACCOUNT_ID }}
          # OIDC is preferred; no long-lived API token needed

      - name: Deploy worker
        if: ${{ !inputs.dry_run }}
        run: pnpm wrangler deploy --name "${{ inputs.worker_name }}" --env production

      - name: Dry-run notice
        if: ${{ inputs.dry_run }}
        run: echo "DRY RUN — skipping actual deploy"

      - name: Write audit summary
        env:
          GH_TOKEN: ${{ github.token }}
        run: |
          cat >> "$GITHUB_STEP_SUMMARY" <<EOF
          ## Deployment Audit Record

          | Field      | Value |
          |------------|-------|
          | Actor      | ${{ github.actor }} |
          | Approver   | ${{ github.triggering_actor }} |
          | Worker     | ${{ inputs.worker_name }} |
          | Reason     | ${{ inputs.reason }} |
          | Dry-run    | ${{ inputs.dry_run }} |
          | SHA        | \`${{ github.sha }}\` |
          | Run ID     | ${{ github.run_id }} |
          | Timestamp  | $(date -u +"%Y-%m-%dT%H:%M:%SZ") |
          EOF
```

---

## Preventing Self-Approval

GitHub enforces the **prevent self-review** environment option (GA 2025) so the
person who clicked "Run workflow" cannot also be the reviewer. Verify it is set:

```bash
gh api \
  repos/{owner}/{repo}/environments/production-gate \
  --jq '.prevent_self_review'
# must return: true
```

If the API returns `false`, update it:

```bash
gh api --method PUT \
  repos/{owner}/{repo}/environments/production-gate \
  -F prevent_self_review=true \
  -F 'reviewers[][type]=Team' \
  -F 'reviewers[][id]=123456'
```

---

## Capturing the Reviewer Identity

GitHub exposes `github.triggering_actor` (the person who approved the gate) and
`github.actor` (who triggered the workflow). Write both to the job summary and to
a deployment record:

```yaml
- name: Record deployment
  env:
    GH_TOKEN: ${{ github.token }}
  run: |
    gh api repos/${{ github.repository }}/deployments \
      --method POST \
      -f ref="${{ github.sha }}" \
      -f environment="production" \
      -f description="Manual deploy: ${{ inputs.worker_name }} approved by ${{ github.triggering_actor }}" \
      -F auto_merge=false \
      -F required_contexts='[]'
```

---

## Timeout and Expiry

By default, pending environment approvals expire after **30 days**. For gated
workflows that should expire much sooner, add a `wait-timer` on the environment
(0–43,200 minutes). Pair it with a job-level `timeout-minutes` so stale runs
cancel automatically:

```yaml
jobs:
  deploy:
    timeout-minutes: 60   # run fails if approval not given within 1 hour
    environment: production-gate
```

---

## Anti-patterns

- **Skipping `prevent_self_review`**: allows the dispatcher to rubber-stamp their
  own deployment, defeating the gate.
- **Sharing the gate environment with push-triggered workflows**: the environment
  becomes the bottleneck for automated deploys too. Use a separate
  `production-gate` environment for manual runs and `production` for automated.
- **Storing the approval gate in a reusable workflow**: the environment must be
  declared in the _calling_ workflow for reviewers to be notified correctly.
- **Using `if: github.triggering_actor != github.actor`** as a DIY self-review
  block: this check runs _inside_ the job, after the gate, and prevents deploy
  but still counts as a deployment that consumed the approval.

---

## Gotchas

- `github.triggering_actor` and `github.actor` are equal when the workflow is
  triggered by an event other than a manual approval; do not rely on their
  difference to detect gating outside of protected environments.
- If the reviewer clicks **Reject** instead of **Approve**, the job transitions
  to `failure`. Your Slack notification from `request-approval` will not
  automatically update — add a follow-up notification job using `if: failure()`.
- Environment protection rules are scoped to _environments_, not to individual
  workflow steps. You cannot gate a single step; wrap it in its own job with
  `environment:`.
- The `wait-timer` on the environment adds a mandatory delay _after_ approval
  before the job starts. Set it to `0` unless you specifically want a cooling-off
  period.

---

## Verification

```bash
# 1. Trigger the workflow as a non-reviewer user
gh workflow run manual-production-deploy.yml \
  -f worker_name=api-gateway \
  -f reason="emergency hotfix test" \
  --ref main

# 2. Check that the run is blocked at environment gate
gh run list --workflow=manual-production-deploy.yml --limit 1

# 3. Approve as a reviewer
gh run review <run-id> --approve --comment "LGTM for hotfix test"

# 4. Verify audit summary
gh run view <run-id> --log | grep "Approver"
```

---

## Related

- `github-actions-environment-protection.md`
- `github-actions-deployment-gates.md`
- `github-environments-approval-gates.md`
- `github-actions-workflow-dispatch-input-validation.md`
- `github-actions-github-token-permission-minimization.md`

---

## Sources

- GitHub Docs — Using environments for deployment: https://docs.github.com/en/actions/deployment/targeting-different-environments/using-environments-for-deployment
- GitHub Docs — Reviewing deployments: https://docs.github.com/en/actions/managing-workflow-runs/reviewing-deployments
- GitHub Changelog — Prevent self-review on environment protection: https://github.blog/changelog/2023-09-15-prevent-self-review-on-environment-protection-rules/
- `github.triggering_actor` context reference: https://docs.github.com/en/actions/learn-github-actions/contexts#github-context
