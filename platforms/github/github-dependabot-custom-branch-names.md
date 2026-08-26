# github-dependabot-custom-branch-names

**Issue:** Controlling Dependabot PR branch names (new 2026 `pull-request-branch-name.separator` config) so they fit naming conventions, monorepo routing, and required-prefix branch rulesets
**Date:** 2026-08-12
**Status:** documented

## Context

Dependabot creates a branch for every PR. Historically the branch name was
locked to `dependabot/<package_ecosystem>-<dependency>-<version>` with hyphens
only. That broke teams with branch rulesets requiring prefixes like `feat/`,
`deps/`, or `chore/`, or ticket IDs in the branch name.

In 2026 GitHub added `pull-request-branch-name.separator` (and prefix support)
to `dependabot.yml`, so teams can finally make Dependabot branches conform to
their own conventions.

This complements `dependabot-config.md` (grouping, scheduling, ignoring
majors). This KB is specifically about branch naming.

## Symptom

- Branch ruleset rejects Dependabot PRs because the branch doesn't match
  `^(feat|fix|chore|deps)/` — Dependabot created `dependabot/npm/react-18.3.1`.
- Two Dependabot PRs collide in the same branch namespace in a monorepo
  (`dependabot/npm/lodash-4.17.21` from `apps/web` and `apps/api`).
- Your team's automation (Jira sync, changelog generator) can't parse
  Dependabot branches because the separator is `hyphen` but the tooling
  expects `/`.
- After upgrading to the 2026 syntax, Dependabot silently ignores the new
  config and falls back to the old name.

## Configuration

### Minimal: change the separator

```yaml
# .github/dependabot.yml
version: 2
updates:
  - package-ecosystem: "npm"
    directory: "/apps/web"
    schedule:
      interval: "weekly"
    pull-request-branch-name:
      separator: "/"           # hyphen (default) | slash | underscore | dash
```

This produces `dependabot/npm/react/18/3/1` instead of
`dependabot/npm/react-18.3.1`. Note the version dots are also replaced by the
separator — choose accordingly.

### With prefix (ruleset-friendly)

```yaml
version: 2
updates:
  - package-ecosystem: "npm"
    directory: "/"
    schedule:
      interval: "weekly"
    pull-request-branch-name:
      separator: "/"
      prefix: "deps"            # appears BEFORE "dependabot/"
      # → deps/dependabot/npm/react/18/3/1
```

### Monorepo: unique prefix per directory

```yaml
version: 2
updates:
  - package-ecosystem: "npm"
    directory: "/apps/web"
    schedule:
      interval: "weekly"
    pull-request-branch-name:
      separator: "/"
      prefix: "web"
  - package-ecosystem: "npm"
    directory: "/apps/api"
    schedule:
      interval: "weekly"
    pull-request-branch-name:
      separator: "/"
      prefix: "api"
```

Branches become `web/dependabot/npm/lodash/4/17/21` and
`api/dependabot/npm/lodash/4/17/21` — no collision.

### With a ticket-id prefix (changelog / Jira-friendly)

```yaml
    pull-request-branch-name:
      separator: "-"
      prefix: "PROJ-1234"
      # → PROJ-1234/dependabot/npm/lodash-4.17.21
```

## Validating the config locally

```bash
# Validate the YAML without waiting for a Dependabot run
gh api -X POST repos/:owner/:repo/dependabot/config/validate \
  --field config=@.github/dependabot.yml
```

Or use the `dependabot` CLI for a dry-run:

```bash
# Trigger a dry run to see what branch name would be generated
gh api -X POST repos/:owner/:repo/dependabot/updates/dry-run \
  --field package_ecosystem=npm | jq '.[].branch_name'
```

## Gotchas

- **Separator replaces ALL non-alphanumeric chars, including the version
  dots.** `slash` separator turns `react-18.3.1` into `react/18/3/1`, which
  nests directories deeply and can confuse branch-list tooling. `underscore`
  (`react_18_3_1`) is often a safer choice if you want readability.
- **Prefix and separator together produce deep paths.** With `prefix: "deps"`
  and `separator: "/"`, a single dependency update creates a branch path
  `deps/dependabot/npm/react/18/3/1`. Some Git UIs truncate this in lists.
- **Existing open Dependabot PRs are NOT renamed when you change config.** The
  new naming only applies to PRs created after the config change. Either merge
  or close existing Dependabot PRs before swapping the separator, or accept a
  mix of old and new branch names until they roll through.
- **Branch rulesets evaluate the new name.** If your ruleset requires
  `^(feat|fix|chore|deps)/`, make sure your Dependabot prefix is `deps` and
  separator is `/`. If the prefix doesn't end in `/`, the ruleset may still
  reject it — test before relying on this.
- **CODEOWNERS routing depends on the file path, not the branch name.** Custom
  branch names do NOT change which CODEOWNERS team is requested. If you were
  using branch-name patterns in a separate GitHub Action to route reviews,
  update that action's regex alongside the Dependabot config.
- **`prefix` length is capped.** GitHub rejects prefixes longer than ~40
  chars. Ticket-ID patterns like `PROJ-1234-AUTH-PAYMENTS-2026-Q3` may be too
  long.
- **`dependabot.yml` v1 does NOT support `pull-request-branch-name.separator`.**
  Ensure `version: 2` at the top of the file. v1 silently ignores the new key.
- **Custom branch names break Dependabot's own "group updates" merging.** If
  you use `groups:` (see `dependabot-config.md`) with custom prefixes, all
  grouped updates share one branch — the prefix applies to the group, not per
  dependency. This is usually what you want, but verify.
- **Slash separator conflicts with branch-protection `restrict-creations`.**
  If your ruleset restricts branch creation to specific patterns and you
  switch Dependabot to `/`, you may need to add `dependabot/**` (or your
  custom prefix) to the allowed patterns or Dependabot will be unable to
  create its branch at all.

## Diagnostic checklist

- [ ] `version: 2` at the top of `dependabot.yml` (v1 silently ignores).
- [ ] Validated YAML via the config-validate API.
- [ ] Branch rulesets allow the new name pattern (test create + merge).
- [ ] Any branch-name-based GitHub Actions (routing, changelog) updated.
- [ ] Existing Dependabot PRs merged or closed before swapping separator.
- [ ] Prefix length under 40 chars.
- [ ] Dry-run confirms the expected branch name.

## References

- Changelog: "Customize Dependabot pull request branch names" (2026)
- Docs: `pull-request-branch-name.separator`, `.prefix`
- Related KB: `dependabot-config.md`, `github-rulesets-2026.md`,
  `github-rulesets-migration-from-branch-protection.md`
