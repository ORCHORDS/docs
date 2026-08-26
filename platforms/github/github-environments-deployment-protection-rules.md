# GitHub Environments — Deployment Protection Rules

**Date:** 2026-08-17
**Author:** the platform team
**Status:** published

## Symptom

A workflow deploys directly to the production Cloudflare Worker
without any human gate, or a junior engineer's branch-push
accidentally triggers a production deploy because the branch
filter is missing from the environment configuration.

## Context

example project maintains two Cloudflare environments — `staging` and
`production` — each with distinct D1 databases, R2 buckets, and
Cloudflare Worker routes. The production environment handles live
Solana payments and Identomat KYC calls; an unreviewed deploy can
break payment processing for all users. GitHub Environments with
deployment protection rules enforce a human approval gate and
branch policy before any production deploy job starts.

## 1. Creating Environments in Repository Settings

Navigate to **Settings → Environments → New environment**.
Create two environments: `staging` and `production`. Environment
names are case-sensitive and must match the `environment:` key
in workflow YAML exactly.

```
Settings → Environments
  ├── staging
  │     protection rules: (none — auto-deploy on push to main)
  └── production
        protection rules:
          ✓ Required reviewers: @acme/platform-team
          ✓ Wait timer: 5 minutes
          ✓ Deployment branches: main only
```

Via the REST API:

```bash
# Create the production environment with reviewer requirement
gh api \
  --method PUT \
  /repos/acme/example project/environments/production \
  --field wait_timer=5 \
  --field prevent_self_review=true
```

Reviewer assignment requires the UI or the GraphQL API; the
REST `PUT /environments/{name}` endpoint accepts
`reviewers` as an array of user or team objects.

## 2. Required Reviewers

Add the `@acme/platform-team` GitHub team as a required reviewer
on the `production` environment. At least one team member must
approve the pending deployment before the workflow job resumes.

```yaml
# .github/workflows/deploy.yml
jobs:
  deploy-production:
    needs: deploy-staging
    runs-on: ubuntu-latest
    environment:
      name: production
      url: https://app.example project.io
    steps:
      - name: Deploy Worker to production
        uses: cloudflare/wrangler-action@v3
        with:
          apiToken: ${{ secrets.CF_API_TOKEN }}
          command: deploy --env production
```

When this job runs, GitHub pauses execution and sends a review
request notification to all members of `@acme/platform-team`.
The job log shows:

```
Waiting for deployment to production...
Deployment #42 is waiting for review by @acme/platform-team
```

Enable **Prevent self-review** so the person who triggered the
workflow cannot be their own approver.

## 3. Wait Timer

A mandatory wait timer (minimum 1 minute, maximum 43 200 minutes)
provides a window to abort an approved deploy if a downstream
alert fires during the wait period.

```
Deploy approved at 14:05 UTC
  │
  ├── 5-minute timer starts
  │
  ├── (optional) on-call engineer confirms Datadog is clean
  │
  └── 14:10 UTC → deploy job resumes automatically
```

Set the timer to 5 minutes for standard releases and 0 minutes
on the hotfix bypass path (see section 6).

## 4. Branch Policy — Deploy Only from main

Restrict the `production` environment to deployments sourced
from the `main` branch. GitHub rejects any workflow run
referencing the `production` environment if the run originates
from any other ref.

```
Allowed branches: main
  ✓ refs/heads/main    → job runs
  ✗ refs/heads/feat/*  → job blocked at queue time
  ✗ refs/tags/v*       → blocked unless explicitly added
```

If your release process cuts a tag from `main` and deploys the
tag, add a second pattern `v[0-9]*` to the allowed-branches list.

Via the API:

```bash
gh api \
  --method POST \
  "/repos/acme/example project/environments/production/deployment-branch-policies" \
  --field type=branch_policy
# Then add the branch name pattern via the UI or a second API call
```

## 5. Environment Secrets vs Repository Secrets

Environment secrets are only injected into jobs that reference
the named environment. Repository secrets are available to every
job in every workflow. Use environment secrets for all production
credentials.

```
Secret scope comparison
────────────────────────────────────────────────────────────────
Secret name         Scope             Available to
CF_API_TOKEN        Environment:prod  deploy-production job only
CF_API_TOKEN        Environment:stg   deploy-staging job only
CLOUDFLARE_ACCT_ID  Repository var    all jobs (non-sensitive)
SENTRY_DSN          Repository secret all jobs (no harm exposed)
HELIUS_API_KEY      Environment:prod  deploy-production job only
────────────────────────────────────────────────────────────────
```

A repository-level `CF_API_TOKEN` that covers production bypasses
the environment gate entirely — any job can access it. Always
scope the production Cloudflare token to the `production`
environment.

## 6. Deployment Status Checks and Hotfix Bypass

Reference the environment in the workflow to create a deployment
event in GitHub's Deployments API. This powers the environment
status badge and deployment history.

```yaml
environment:
  name: production
  url: https://app.example project.io
```

For critical hotfixes where the 5-minute timer and reviewer
requirement would delay incident mitigation, configure a
**bypass list** in the environment settings. Only add users
with on-call authority (typically two SREs).

```
Environment: production
  Bypass list: @alice (SRE lead), @bob (platform lead)
  Effect: bypass reviewer requirement AND wait timer
```

Document every bypass use in the post-mortem template:

```markdown
## Deployment bypass used
- Approver: @alice
- Reason: P0 payment processing outage (PID-2026-042)
- Deploy SHA: <commit-sha>
- Rolled back: no
```

## Anti-patterns

- Placing the production `CF_API_TOKEN` in repository-level
  secrets; any workflow job can read it regardless of environment
  approval status.
- Using the same environment name for staging and production;
  a typo in the workflow `environment:` key sends a staging
  deploy to production's protection rules (or vice versa).
- Adding all engineers to the bypass list to avoid friction;
  the bypass path is reserved for declared P0/P1 incidents.
- Setting `prevent_self_review: false` on a small team where
  the triggering engineer can also approve their own deploy.

## Gotchas

- If `needs:` points to a job in a different workflow file, the
  `environment:` protection for the downstream job still applies,
  but the reviewer notification references the calling workflow
  URL, not the reusable workflow URL.
- Deleting an environment does not delete its secrets; they become
  orphaned. Re-create the environment and the secrets will
  re-attach automatically.
- The wait timer counts from the moment a reviewer approves, not
  from the workflow trigger time.
- Rulesets at the organisation level can override per-repo
  environment branch policies; check org-level rulesets when
  branch restrictions appear to have no effect.

## Verification

```bash
# List deployments and their statuses for an environment
gh api /repos/acme/example project/deployments \
  --jq '.[] | {id, environment, sha: .sha[:7], state: .statuses_url}'

# Confirm the production environment protection rules
gh api /repos/acme/example project/environments/production \
  --jq '{wait_timer, reviewers: [.protection_rules[].reviewers]}'

# Trigger a dry-run dispatch to staging (no production risk)
gh workflow run deploy.yml \
  --ref main \
  --field environment=staging
```

## Related

- documentation/categories/github/github-actions-cloudflare-deploy-workflow.md
- documentation/categories/github/github-actions-reusable-workflow-patterns.md
- documentation/categories/deploy/hotfix-runbook.md
- documentation/categories/cloudflare/workers-secrets-env-vars.md

## Source URLs (verified 2026-08-17)

- https://docs.github.com/en/actions/deployment/targeting-different-environments/using-environments-for-deployment
- https://docs.github.com/en/rest/deployments/environments
- https://docs.github.com/en/actions/security-guides/using-secrets-in-github-actions#creating-secrets-for-an-environment
- https://docs.github.com/en/actions/deployment/targeting-different-environments/using-environments-for-deployment#deployment-protection-rules
