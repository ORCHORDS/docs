# dependabot-renovate-2026

**Issue:** A team has 200 npm dependencies. A critical security vulnerability drops in `axios`. Nobody notices for 3 weeks. The team is on `axios@0.27.0` with a known CVE. The competitor that patches in 24 hours is not the team that ignores Dependabot alerts.
**Date:** 2026-08-10
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Symptom

Dependencies go stale. Security CVEs land in upstream packages. New versions break things if upgraded blindly. Teams manually upgrade every few months; the cycle is broken between upgrades. The result: known CVEs in production.

## Root cause

Dependabot (GitHub) and Renovate (Mend) are the two main automated dependency update tools. They open PRs for new versions, security advisories, and breaking changes. A team that enables them stays current; a team that doesn't falls behind within weeks.

## The 2026 comparison

| Feature | Dependabot | Renovate |
|---|---|---|
| GitHub integration | Native (GitHub-owned) | Native (Mend) |
| GitLab, Bitbucket, others | Limited | Yes |
| Auto-merge | Yes (with config) | Yes (with config) |
| Grouping multiple updates | Yes | Yes (more flexible) |
| Lock file maintenance | Yes | Yes |
| Security alerts | GitHub Advisory Database | Multiple databases |
| Scheduling | Weekly default, configurable | Configurable per-package |
| Custom regex managers | Limited | Yes |
| Vulnerability alerts | Yes (GitHub Security tab) | Yes (dashboard) |
| Free for public repos | Yes | Yes |
| Free for private repos | Yes (limited) | Yes (limited) |

For a GitHub-only project, Dependabot is the path of least resistance. For multi-platform or advanced config (custom regex, monorepo-aware grouping), Renovate is the better fit.

## The Dependabot config

```yaml
# .github/dependabot.yml
version: 2
updates:
  - package-ecosystem: "npm"
    directory: "/"
    schedule:
      interval: "weekly"
      day: "monday"
    open-pull-requests-limit: 10
    groups:
      production-dependencies:
        dependency-type: "production"
      development-dependencies:
        dependency-type: "development"
    labels:
      - "dependencies"
      - "automated-pr"
    reviewers:
      - "myorg/frontend-team"
    commit-message:
      prefix: "deps"
    # Auto-merge minor and patch updates
    # (configure via GitHub Actions, not dependabot.yml)
```

Key settings:
- `interval: weekly` — Dependabot checks weekly
- `groups` — bundle multiple updates into one PR
- `open-pull-requests-limit` — cap the number of open PRs
- `labels`, `reviewers` — automation-friendly PR metadata
- `commit-message.prefix` — Conventional Commits-friendly

## The Renovate config

```json
// renovate.json
{
  "$schema": "https://docs.renovatebot.com/renovate-schema.json",
  "extends": ["config:recommended"],
  "packageRules": [
    {
      "description": "Auto-merge patch updates",
      "matchUpdateTypes": ["patch", "minor"],
      "automerge": true,
      "automergeType": "pr",
      "platformAutomerge": {
        "enabled": true
      }
    },
    {
      "description": "Group all dev dependencies",
      "matchDepTypes": ["devDependencies"],
      "groupName": "dev dependencies",
      "schedule": ["before 6am on monday"]
    },
    {
      "description": "Pin major versions of production dependencies",
      "matchDepTypes": ["dependencies"],
      "rangeStrategy": "pin"
    }
  ]
}
```

Renovate's `extends: ["config:recommended"]` is a starting preset. Custom rules layer on top: automerge policy, group rules, version pinning, schedule.

## The 5 best practices

1. **Enable both Dependabot and security advisories.** Dependabot opens PRs; GitHub Security tab alerts on CVEs.
2. **Group minor and patch updates.** Don't open 20 PRs for 20 patch updates; bundle into one weekly PR.
3. **Auto-merge with tests.** Configure auto-merge for patch and minor updates; let CI gate. Major updates still require review.
4. **Pin major versions in production.** `rangeStrategy: pin` keeps major versions stable; manual upgrade for breaking changes.
5. **Schedule updates outside work hours.** Monday morning is worst; late Sunday or early Monday is better. CI resources are freed.

## The auto-merge pattern

```yaml
# .github/workflows/auto-merge.yml
on:
  pull_request:
    types: [opened, synchronize, reopened]

jobs:
  auto-merge:
    runs-on: ubuntu-latest
    if: github.actor == 'dependabot[bot]' || github.actor == 'renovate[bot]'
    steps:
      - uses: actions/checkout@v4
      - name: Enable auto-merge
        run: gh pr merge --auto --squash "$PR_URL"
        env:
          GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}
          PR_URL: ${{ github.event.pull_request.html_url }}
```

The workflow checks that CI passes; if so, auto-merges. If CI fails, the PR stays open for human review.

## The security alert workflow

For a CVE that requires immediate action:

1. **GitHub Security tab** shows the alert with severity, affected versions, fixed version
2. **Dependabot opens a PR** with the fix
3. **CI runs** security tests
4. **Auto-merge** if CI passes; manual review if not
5. **Production deploy** via the normal release process

The cycle from CVE disclosure to production fix is 24-72 hours. Without automation, it's weeks to months.

## The monorepo pattern

For a monorepo with multiple packages, Dependabot and Renovate both support per-package configs:

```yaml
# .github/dependabot.yml
updates:
  - package-ecosystem: "npm"
    directory: "/packages/api"
    schedule:
      interval: "weekly"
  - package-ecosystem: "npm"
    directory: "/packages/web"
    schedule:
      interval: "weekly"
    groups:
      web:
        applies-to: "packages/web/package.json"
```

Each package gets its own update PRs. The `groups` config bundles updates within a package. Cross-package updates (e.g., a shared types package) are coordinated manually.

## The lock file maintenance

Both tools update the lock file (`package-lock.json`, `yarn.lock`, `pnpm-lock.yaml`) alongside the package.json. The CI runs `npm ci` (which uses the lock file) to ensure reproducibility. A team that doesn't commit the lock file loses this protection.

## The breaking change handling

Major version updates often include breaking changes. The discipline:

- **Don't auto-merge major updates.** Review the changelog; check the breaking change section; plan the migration.
- **Use Renovate's `major.automerge: false`.** Set this explicitly.
- **Track breaking changes in a project board.** Major upgrades are work items.
- **Read the migration guide before merging.** Skipping the read is a release incident waiting to happen.

## The verification

The tell that automated dependency updates are working:

- A CVE is patched within 72 hours of disclosure
- The team never runs a manual dependency upgrade
- CI passes on auto-merged PRs
- Lock file is always committed
- Major version upgrades have a project ticket

The tell it isn't:

- Dependabot alerts are 200+ open
- The team runs `npm outdated` quarterly as a chore
- A known CVE in production is "we'll fix it next sprint"
- Lock file is in .gitignore (it shouldn't be)

## Gotchas

- **Auto-merge without tests is dangerous.** CI must be the gate; auto-merge is the convenience.
- **Major versions need human review.** Even with auto-merge, major upgrades deserve a release ticket.
- **Lock file must be committed.** Without it, `npm install` produces different trees on different machines.
- **Dependabot/Renovate are not security scanners.** They alert; they don't run `npm audit`-style deep scans. Run those separately.
- **Private packages need different config.** Dependabot's free tier for private repos is limited; Renovate's free tier is more generous.
- **Schedule updates outside work hours.** Monday morning sees 50 PRs and breaks focus; schedule for Sunday night or early Monday.
- **Group related updates.** A weekly PR with 20 minor updates is easier to review than 20 individual PRs.

## Related

- `worktree/husky-lint-staged.md` — local pre-commit
- `worktree/branch-protection-codeowners-2026.md` — CODEOWNERS for review
- `worktree/conventional-commits-2026.md` — clean commit messages for Dependabot
- `worktree/release-please-semantic-release.md` — automation downstream of dependency updates

## Source URLs (verified 2026-08-10)

- https://docs.github.com/en/code-security/dependabot
- https://docs.renovatebot.com/
- https://github.blog/changelog/label/dependabot/
- https://docs.renovatebot.com/merge-confidence/
- https://www.mend.io/renovate/
