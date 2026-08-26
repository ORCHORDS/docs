# dependabot-config

**Issue:** Dependabot config — group updates, ignore majors, schedule
**Date:** 2026-08-09
**Status:** documented

## Symptom
Dependabot opens 30 PRs in one week, one for every minor + patch
bump across your 200 dependencies. Your PR queue is 90% Dependabot.
The signal-to-noise ratio is zero.

## Root cause
By default, Dependabot creates a separate PR per dependency
version bump. For a large repo, this floods the queue.

**Source:** GH Dependabot config docs:
https://docs.github.com/en/code-security/dependabot/dependabot-version-updates/configuration-options-for-the-dependabot.yml-file

## Fix
A well-tuned `.github/dependabot.yml`:

```yaml
version: 2

updates:
  - package-ecosystem: "npm"
    directory: "/"
    schedule:
      interval: "weekly"
      day: "monday"
      time: "06:00"
      timezone: "UTC"
    # Group all minor + patch updates into a single PR
    groups:
      minor-and-patch:
        patterns:
          - "*"
        update-types:
          - "minor"
          - "patch"
      production:
        patterns:
          - "next"
          - "react"
          - "express"
        update-types:
          - "minor"
          - "patch"
    # Major updates need human review
    open-pull-requests-limit: 10
    labels:
      - "dependencies"
      - "automated"
    # Ignore specific majors (e.g. typescript 5→7 blocked)
    ignore:
      - dependency-name: "typescript"
        versions: ["7.x"]
        # Reason: typescript-eslint v8 peer dep blocks upgrade
    reviewers:
      - "backend-team"
    assignees:
      - "dependabot-bot"
    commit-message:
      prefix: "deps"
      prefix-development: "deps(dev)"
      include: "scope"

  - package-ecosystem: "github-actions"
    directory: "/"
    schedule:
      interval: "weekly"
    groups:
      actions:
        patterns: ["*"]
        update-types: ["minor", "patch"]
    labels:
      - "dependencies"
      - "ci"
```

## Key features

### Groups
Combine multiple dependency updates into a single PR:
- `minor-and-patch`: all minor + patch bumps across all deps
- `production`: critical runtime deps in their own group
- `dev`: dev-only deps in their own group

### `ignore`
Skip specific major versions that are known to break:
```yaml
ignore:
  - dependency-name: "typescript"
    versions: ["7.x"]
```

The `versions` field uses semver ranges. `7.x` means any 7.x
version.

### `open-pull-requests-limit`
Cap the number of open Dependabot PRs. Default 5. With groups,
you typically have 1-3 PRs at a time.

### `schedule`
Control when Dependabot runs. Weekly is the right default for
most repos. Daily floods the queue; monthly misses security
updates.

### `auto-merge`
For trivial updates, enable auto-merge:
```yaml
# In the repo settings, OR via a separate workflow:
# .github/workflows/dependabot-auto-merge.yml
```

But auto-merge requires the CI to be fast + green. A flaky CI
will block all auto-merges.

## Verification
- **Test:** Dependabot opens 1-3 PRs per week (not 30)
- **Live:** Major updates get individual PRs + human review
- **Audit:** Monthly review of Dependabot PRs + ignored majors

## Gotchas
- **Grouped PRs are larger but easier to review.** A single PR
  with 10 minor bumps is faster to review than 10 separate
  PRs.
- **Dependabot security updates are separate from version
  updates.** Security updates always get their own PR (no
  grouping) and are high-priority.
- **For monorepos, multiple `updates` entries** (one per
  ecosystem or directory) may be needed. pnpm + GH Actions =
  2 entries.
- **The `versions` field in `ignore` is cumulative.** Listing
  `7.x` ignores ALL 7.x. List specific versions for surgical
  control.
- **Dependabot can't resolve version conflicts.** If two PRs
  have conflicting `package-lock.json`, the second will fail
  CI. Manually rebase.
- **Renovate** is an alternative to Dependabot with more
  features (better monorepo support, more config). Migration is
  straightforward.

## Related
- `secrets-rotation-runbook.md` (for the GH PAT Dependabot uses)
- `pat-self-merge-workaround.md` (for stalled Dependabot PRs)
- Dependabot docs: https://docs.github.com/en/code-security/dependabot
