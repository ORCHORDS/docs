# GitHub Rulesets Bypass Actors and Break-Glass Emergency Procedures

Date: 2026-08-23 / Author: example.com / Status: production

## Symptom / Use-case

A critical hotfix must reach production immediately but the merge queue is full, a
required status check is timing out, or a CI runner pool is down.  Without a documented
break-glass procedure, engineers either disable branch protection entirely (high blast
radius) or wait indefinitely.  Ruleset bypass actors provide a scoped, audited
alternative.

## Context

GitHub Rulesets (the successor to branch protection rules) support **bypass actors** —
specific users, teams, GitHub Apps, or deploy keys that can push or merge *despite*
otherwise-blocking rules.  Bypass can be configured as:

- **Always bypass** — the actor ignores all rules in the ruleset unconditionally.
- **Pull request only** — the actor can open a PR that bypasses rules but cannot
  force-push directly.

Unlike disabling branch protection (which affects all actors), bypass actors are named
and every bypass is written to the audit log with actor, repo, rule, and timestamp.

---

## 1. Adding a Bypass Actor via API

```bash
# List existing rulesets to find the ID
gh api repos/{owner}/{repo}/rulesets | jq '.[] | {id, name, enforcement}'

# Add a team as a bypass actor to an existing ruleset
gh api --method PUT repos/{owner}/{repo}/rulesets/{ruleset_id} \
  --input - <<'EOF'
{
  "bypass_actors": [
    {
      "actor_id": 123456,
      "actor_type": "Team",
      "bypass_mode": "pull_request"
    }
  ]
}
EOF
```

Actor types: `RepositoryRole`, `Team`, `Integration` (GitHub App), `OrganizationAdmin`.

```bash
# Get the team node ID (numeric) from the slug
gh api orgs/{org}/teams/{team_slug} | jq '.id'

# Get the GitHub App installation ID
gh api repos/{owner}/{repo}/installation | jq '.id'
```

---

## 2. Org-Level Ruleset Bypass for All Repositories

For emergency access across many repos, configure bypass on an org-level ruleset so a
single "break-glass" team can push to any protected repo.

```json
// PATCH /orgs/{org}/rulesets/{ruleset_id}
{
  "bypass_actors": [
    {
      "actor_id": 987654,
      "actor_type": "Team",
      "bypass_mode": "pull_request"
    }
  ],
  "conditions": {
    "repository_name": { "include": ["*"], "exclude": [] },
    "ref_name": {
      "include": ["refs/heads/main", "refs/heads/release/*"],
      "exclude": []
    }
  }
}
```

Restrict team membership to ≤ 3 principals (on-call leads) and rotate after each use.

---

## 3. Break-Glass GitHub Action for Timed Bypass

Automate the bypass grant and auto-revoke pattern so no human forgets to remove access.

```yaml
# .github/workflows/break-glass.yml
name: Break-Glass Bypass Grant

on:
  workflow_dispatch:
    inputs:
      justification:
        description: "Reason for bypass (incident ID required)"
        required: true
      duration_minutes:
        description: "Auto-revoke after N minutes (max 60)"
        default: "30"
        required: true

permissions:
  contents: write   # to call the rulesets API via GH App

jobs:
  grant:
    runs-on: ubuntu-latest
    environment: break-glass   # requires two approvers in org settings
    steps:
      - name: Validate duration
        run: |
          if (( ${{ inputs.duration_minutes }} > 60 )); then
            echo "Duration exceeds 60-minute maximum" && exit 1
          fi

      - name: Log break-glass event
        run: |
          echo "BREAK-GLASS initiated by ${{ github.actor }}" \
               "at $(date -u +%Y-%m-%dT%H:%M:%SZ)" \
               "for: ${{ inputs.justification }}" | tee /tmp/bg-log.txt

      - name: Grant bypass to initiator's team
        uses: actions/github-script@v7
        with:
          github-token: ${{ secrets.BREAK_GLASS_APP_TOKEN }}
          script: |
            // Add actor; implementation depends on your team ID mapping
            const rulesetId = process.env.RULESET_ID;
            // ... PATCH rulesets API to add bypass actor

      - name: Schedule auto-revoke
        run: |
          REVOKE_AT=$(date -u -d "+${{ inputs.duration_minutes }} minutes" +%Y-%m-%dT%H:%M:%SZ)
          echo "Bypass will be auto-revoked at $REVOKE_AT"
          # Trigger a time-delayed workflow via repository_dispatch or
          # schedule a GitHub Actions run via the API.

      - name: Notify security channel
        run: |
          curl -s -X POST "${{ secrets.SLACK_SECURITY_WEBHOOK }}" \
            -H "Content-Type: application/json" \
            -d "{\"text\":\"BREAK-GLASS by ${{ github.actor }}: ${{ inputs.justification }}\"}"
```

---

## 4. Audit Log Queries for Bypass Events

Every bypass writes an `protected_branch.policy_override_push` or
`protected_branch.policy_override_merge` event to the audit log.

```bash
# Stream last 24h of bypass events from the audit log API
gh api \
  "orgs/{org}/audit-log?phrase=action:protected_branch.policy_override&per_page=100" \
  | jq '.[] | {actor, repo: .repository, action, created_at}'
```

For SIEM export, configure audit log streaming (covered in `audit-log-streaming-siem.md`)
and create an alert on these event codes:

```bash
# Grep for bypass events in streamed audit NDJSON
grep '"action":"protected_branch.policy_override' /var/log/gh-audit/*.ndjson \
  | jq -r '[.created_at, .actor, .repository, .action] | @tsv'
```

---

## 5. Enforcing Post-Incident Review via Issue Automation

After each bypass, automatically open a follow-up issue.

```yaml
      - name: Open post-incident review issue
        uses: actions/github-script@v7
        with:
          github-token: ${{ secrets.GITHUB_TOKEN }}
          script: |
            await github.rest.issues.create({
              owner: context.repo.owner,
              repo: context.repo.repo,
              title: `[Break-Glass Review] ${new Date().toISOString().slice(0,10)} — ${{ github.actor }}`,
              body: `## Break-Glass Event\n\n**Actor:** ${{ github.actor }}\n**Justification:** ${{ inputs.justification }}\n\n## Required actions\n- [ ] Confirm the bypass was necessary\n- [ ] Verify no unreviewed commits landed on main\n- [ ] Close the incident\n- [ ] Remove bypass actor if still active`,
              labels: ['break-glass', 'security-review'],
              assignees: ['${{ github.actor }}']
            });
```

---

## Anti-patterns

- Setting `bypass_mode: "always"` for any team or user — this allows direct force-pushes
  to protected branches; prefer `"pull_request"` mode to preserve PR audit trails.
- Granting bypass to the `OrganizationAdmin` actor type — every org admin becomes a
  bypass actor, widening the blast radius far beyond break-glass intent.
- Not logging bypass events to a SIEM or Slack channel — bypasses become invisible and
  post-incident reviews impossible.
- Leaving bypass actors in place after the incident; treat them like firewall rules that
  must be removed within hours.

## Gotchas

- Bypass actors configured on an org-level ruleset are inherited by repositories; repo-
  level rulesets cannot *remove* an org-level bypass.
- `OrganizationAdmin` as a bypass actor type refers to the org *role*, not a team named
  "admins" — all owners of the org gain bypass automatically.
- The "enforcement" field on a ruleset can be `active`, `evaluate` (dry-run), or
  `disabled`; switching to `evaluate` during an incident is safer than adding bypass
  actors because it still logs violations without blocking.
- GitHub Apps used as bypass actors must be installed on the target repository; an
  app installed only at the org level without repo access will not bypass repo rulesets.

## Verification

```bash
# Confirm bypass actors are scoped correctly
gh api repos/{owner}/{repo}/rulesets/{ruleset_id} \
  | jq '.bypass_actors[] | {actor_type, bypass_mode}'

# Replay the last 10 audit bypass events
gh api "orgs/{org}/audit-log?phrase=action:protected_branch&per_page=10" \
  | jq '.[] | {actor, action, created_at, repo: .repository}'

# Confirm bypass actor was removed after incident
gh api repos/{owner}/{repo}/rulesets/{ruleset_id} | jq '.bypass_actors | length'
```

## Related

- `github-rulesets-2026.md`
- `github-rulesets-migration-from-branch-protection.md`
- `audit-log-streaming-siem.md`
- `github-actions-environment-protection.md`
- `github-branch-protection-ruleset-workers-ci-checks.md`

## Sources

- https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-rulesets/managing-rulesets-for-a-repository#granting-bypass-permissions-for-your-ruleset
- https://docs.github.com/en/organizations/managing-organization-settings/audit-log-events-for-your-organization
- https://github.blog/changelog/2023-10-12-github-rulesets-are-generally-available/
