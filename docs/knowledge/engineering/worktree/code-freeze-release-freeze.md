# Code Freeze and Release Freeze Procedures

- **Date**: 2026-08-22
- **Author**: example.com
- **Status**: production

---

## Symptom / Use-case

A release is approaching and last-minute changes are landing in `main`, each one
introducing potential regressions. QA cannot pin a build to test against. On-call
engineers dread the weekend because deploys are still flowing. Leadership asks
"are we stable?" and no one can answer confidently.

A code freeze formalizes the answer: from a declared timestamp, no new code enters
the release branch (or `main`, on trunk-based workflows) without passing an explicit
exception process. It creates a stable artifact for testing and gives the team
a shared, contractual understanding of what is — and is not — in the release.

---

## Context

**Code freeze** halts all non-critical merges to the release target during a defined
window — typically 1–3 days before a major release and through the release day itself.
**Release freeze** is broader: it can also include a moratorium on infrastructure
changes, configuration changes, and third-party dependency updates that would affect
the production environment.

The two levers:

| Lever | Scope | Duration | Enforcement |
|---|---|---|---|
| Code freeze | Source merges to release branch | 1–5 days | Branch protection + merge queue pause |
| Release freeze | All production change | Days to weeks | Change-management policy + approval gates |

Release freezes are common around:
- Year-end / peak business periods (e-commerce Black Friday, fiscal closes)
- Major product launches (all hands preparing for the event)
- Disaster recovery exercises or infrastructure migrations
- Regulatory audit windows

---

## Phase 1 — Declaring the Freeze

### Freeze announcement template

```markdown
## Code Freeze Notice — Release 2026-09-01

**Freeze window**: 2026-08-29 18:00 UTC → 2026-09-01 22:00 UTC
**Target release**: v3.4.0 on branch `release/3.4.0`
**Release manager**: @alice

### What is frozen
- All merges to `release/3.4.0`
- All merges to `main` that are scheduled for v3.4.0

### What is NOT frozen
- Merges to `main` tagged `target: v3.5.0` (future release)
- Hotfix PRs with the `freeze-exception` label (see exception process below)
- Documentation-only changes to `docs/` with no code impact

### Exception process
1. Ping @release-managers in #releases with a one-paragraph justification.
2. Two release-manager approvals required (not the PR author).
3. A freeze-exception PR must have 100 % passing CI and zero test failures.
4. Author cherry-picks the commit to `release/3.4.0` after approval.

### Contacts
- Release manager: @alice
- Backup: @bob
- Escalation: @eng-director
```

Send this notice to:
- Engineering Slack channel (`#engineering-announcements`)
- The project management tool (Jira/Linear epic pinned comment)
- Email distribution list for external stakeholders if the freeze also covers infrastructure

---

## Phase 2 — Enforcing the Freeze via Branch Protection

### Temporary branch protection via GitHub CLI

```bash
REPO="org/repo"
BRANCH="release/3.4.0"

# Add an additional required status check that intentionally fails during freeze
# The "freeze-gate" check is a workflow that exits 1 unless the PR carries
# the 'freeze-exception' label.
gh api \
  --method PUT \
  "/repos/${REPO}/branches/${BRANCH}/protection" \
  --field required_status_checks='{"strict":true,"contexts":["freeze-gate"]}' \
  --field enforce_admins=true \
  --field required_pull_request_reviews='{"required_approving_review_count":2,"dismiss_stale_reviews":true}' \
  --field restrictions=null
```

### The freeze-gate workflow

```yaml
# .github/workflows/freeze-gate.yml
name: Freeze Gate

on:
  pull_request:
    branches:
      - 'release/**'
      - main

permissions:
  contents: read
  pull-requests: read

jobs:
  freeze-gate:
    runs-on: ubuntu-latest
    steps:
      - name: Check freeze status
        env:
          GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}
        run: |
          # Read freeze configuration from repo variable
          FREEZE_ACTIVE="${{ vars.CODE_FREEZE_ACTIVE }}"

          if [[ "$FREEZE_ACTIVE" != "true" ]]; then
            echo "No freeze in effect. Passing."
            exit 0
          fi

          # Check whether the PR carries the exception label
          PR_NUMBER="${{ github.event.pull_request.number }}"
          LABELS=$(gh pr view "$PR_NUMBER" --json labels --jq '[.labels[].name] | join(",")')

          if echo "$LABELS" | grep -q "freeze-exception"; then
            echo "Freeze exception label present. Passing."
            exit 0
          fi

          echo "::error::Code freeze is active. This PR requires a 'freeze-exception' label and two release-manager approvals."
          exit 1
```

Toggle the freeze on and off without modifying workflow files:

```bash
# Activate freeze
gh variable set CODE_FREEZE_ACTIVE --body "true" --repo org/repo

# Deactivate freeze after release
gh variable set CODE_FREEZE_ACTIVE --body "false" --repo org/repo
```

This approach avoids branch rule edits during a high-stress window — a single
variable flip activates and deactivates the gate.

---

## Phase 3 — Managing Exceptions

### Exception tracking label and PR template

```bash
# Create the exception label
gh label create "freeze-exception" \
  --color "b60205" \
  --description "Approved for merge during code freeze" \
  --repo org/repo
```

Maintain a freeze exception log in the release epic or a pinned Slack thread:

```
| # | PR  | Author | Justification          | Approvals | Risk   | Status   |
|---|-----|--------|------------------------|-----------|--------|----------|
| 1 | 912 | @carol | Fix payment null crash | @alice @bob | Low  | Merged   |
| 2 | 927 | @dave  | Add new analytics event| @alice    | Medium | Rejected |
```

Rejected exceptions should be explicitly acknowledged — silence is not a "no."

---

## Phase 4 — Release Day and Thaw

### Pre-thaw checklist

```markdown
## Pre-Thaw Checklist

- [ ] Release artifact tagged and signed (v3.4.0)
- [ ] Release deployed to production successfully
- [ ] Smoke tests passing in production
- [ ] Rollback tested (ran rollback script in staging, confirmed health)
- [ ] No active P0/P1 incidents in #incidents
- [ ] Release notes published to changelog
- [ ] `main` has received all cherry-picks from `release/3.4.0`
- [ ] `release/3.4.0` branch merged back to `main` (or PR opened)
- [ ] Release manager sign-off: @alice
```

### Automated thaw notification

```bash
# Post a Slack message when the freeze is lifted
FREEZE_END=$(date -u +"%Y-%m-%dT%H:%M:%SZ")

curl -X POST "$SLACK_WEBHOOK_URL" \
  -H 'Content-type: application/json' \
  -d "{
    \"text\": \":unlock: *Code freeze lifted* — v3.4.0 is live. Normal merging resumes as of ${FREEZE_END} UTC.\",
    \"channel\": \"#engineering-announcements\"
  }"

# Deactivate gate variable
gh variable set CODE_FREEZE_ACTIVE --body "false" --repo org/repo
```

---

## Anti-patterns

**Indefinite freeze with no declared end date.** Engineers stop sending PRs, work
piles up in draft, and the queue becomes unmanageable when the freeze lifts. Always
declare both start and end in the announcement.

**Admin bypass during freeze.** If `enforce_admins` is `false`, senior engineers
can merge around the freeze, undermining trust in the process. Enforce for admins
and use the exception process for legitimate urgent work.

**Freezing `main` without a release branch.** On trunk-based workflows, freezing
`main` blocks all future-release work. Always cut a `release/x.y.z` branch before
the freeze so feature development on `main` continues.

**Not tracking exceptions.** An unlogged exception becomes invisible in the
post-release retrospective. "I'm not sure how that got in" is a failure of process
traceability.

**Declaring a freeze too late.** Announcing a freeze 2 hours before it starts creates
panic merges — engineers rush to land work, increasing risk at exactly the wrong time.
Give 48 hours notice for planned freezes.

---

## Gotchas

- The `enforce_admins` flag in branch protection is not respected by the "Bypass
  list" feature introduced in newer GitHub branch ruleset APIs. If you use Rulesets
  (not classic branch protection), verify that no bypass actors are configured for
  the release branch during the freeze window.

- `vars.CODE_FREEZE_ACTIVE` is an organization or repository variable, not a secret.
  Any workflow can read it. This is intentional — the freeze state is not sensitive —
  but be aware that a compromised workflow could also read it.

- Cherry-picks to `release/3.4.0` after a freeze exception still require the freeze-gate
  check to pass. Apply the `freeze-exception` label to the cherry-pick PR as well, not
  only the original feature PR.

- Freeze windows do not automatically pause Dependabot or Renovate. Suppress automated
  dependency-update PRs by adding a schedule override in `renovate.json` or by
  disabling the Dependabot workflow via `gh workflow disable dependabot.yml`.

---

## Verification

```bash
# Confirm freeze gate is active
gh variable get CODE_FREEZE_ACTIVE --repo org/repo

# List all PRs currently labeled freeze-exception
gh pr list --label "freeze-exception" --repo org/repo

# Audit merge commits during freeze window
# (replace timestamps with actual freeze start/end)
FREEZE_START="2026-08-29T18:00:00Z"
FREEZE_END="2026-09-01T22:00:00Z"
gh api "/repos/org/repo/commits" \
  --jq ".[] | select(.commit.committer.date >= \"$FREEZE_START\" and .commit.committer.date <= \"$FREEZE_END\") | [.sha[0:7], .commit.committer.date, .commit.message] | @tsv" \
  -f since="$FREEZE_START" \
  -f until="$FREEZE_END" \
  -f sha="release/3.4.0"
```

---

## Related

- `hotfix-process.md` — the exception process for production-critical fixes during freeze
- `release-management-2026.md` — release planning cadence that freeze fits into
- `release-branch-strategy-gitflow-trunk.md` — when to use a release branch vs trunk
- `rollback-strategy.md` — post-release rollback if the freeze still let something slip

---

## Sources

- GitHub branch protection API: https://docs.github.com/en/rest/branches/branch-protection
- GitHub repository variables: https://docs.github.com/en/actions/writing-workflows/choosing-what-your-workflow-does/store-information-in-variables
- "Accelerate" by Forsgren, Humble & Kim — change failure rate and deployment frequency
- Google SRE Book — Change management and freeze windows
