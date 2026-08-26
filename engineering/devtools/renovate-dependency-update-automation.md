# renovate-dependency-update-automation

**Issue:** Dependencies rot silently. Security patches pile up as advisories, framework majors drift two versions behind, and when someone finally tries to upgrade everything at once it becomes a multi-day yak-shave that gets abandoned half-done. Doing updates manually also produces the worst kind of PR: 40 changed packages in one commit with no bisectable history. Dependency-update bots invert this by continuously opening small, grouped, machine-attributed pull requests — and in 2025-2026 the tooling choice has consolidated around Renovate (depth, grouping, auto-merge, multi-platform) versus GitHub Dependabot (zero-config, native alerts). This article covers picking between them and configuring Renovate so a busy monorepo like this one gets signal, not hundreds of noisy PRs a week.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Choosing between Renovate and Dependabot

1. **Renovate when the repo is a monorepo or multi-platform.** Renovate understands workspaces natively, has a built-in `group:monorepos` preset that bumps related packages (all `@types/*`, framework families) in a single PR, and supports GitLab/Bitbucket/Azure in addition to GitHub. Its `packageRules` engine handles per-directory schedules and grouping that Dependabot's config cannot express.
2. **Dependabot when the repo is GitHub-only and wants zero config.** One `dependabot.yml` with no app installation, plus direct wiring into GitHub security advisories and code scanning alerts. For a single-package repo it is genuinely enough.
3. **Grouping is the number-one lever either way.** Un-grouped bots open one PR per dependency, which trains maintainers to ignore the tab entirely. Group dev dependencies together, group minor+patch separately from majors, and let the bot auto-merge the boring tier.
4. **They can coexist but pick one for updates.** Running both for version updates duplicates PRs; the sane combo is Dependabot purely for security alerts and Renovate for everything else — or just Renovate, which also reads OSV/advisory data and can prioritize vulnerable updates with a dedicated preset.

## Core Renovate configuration

1. **Start from presets, not a blank file.** `config:recommended` sets sane defaults (pinning, limits, updates locked files). Layer `:pinAllExceptPeerDependencies`, `group:monorepos`, `schedule:weekly`, and `lockFileMaintenance` on top rather than hand-writing rules.
2. **packageRules are the workhorse.** Each rule matches on `matchPackageNames`, `matchManagers`, `matchFileNames` (critical for monorepos) and applies `groupName`, `schedule`, `rangeStrategy`, or `automerge`. Typical setup: everything minor/patch grouped as "non-major", majors grouped per-package-family with their own PR, and a distinct quiet schedule for dev-only tooling.
3. **Separate automerge tiers.** `automerge: true` with `matchUpdateTypes: ["patch", "pin", "digest"]` plus required status checks (`automergeType: "pr"`, platform auto-merge) lets CI green-merge trivial updates, while majors always wait for a human. Auto-merge is only safe when CI is meaningful — it amplifies whatever your test suite actually covers.
4. **Monorepo directories via matchFileNames.** In a pnpm workspace, scope rules to `packages/router/**` or the root `package.json` so the router's framework major does not get tangled with the fleet CLI's. Dependabot's rough equivalent is multiple `directories:` entries in dependabot.yml, which is workable but far less expressive.
5. **Validate locally before pushing.** `renovate-config-validator` against `renovate.json` catches malformed presets and typo'd packageRules in seconds; the Mend Renovate docs' config-validation page is the reference. This belongs in CI as a lint step so config drift never lands.

## Taming PR noise

1. **Schedule the bot.** `schedule:weekly` or an off-hours window batches updates into predictable pulses instead of a constant drip; `prCreation: "status-success"` suppresses PRs that would start red.
2. **Use dependencyDashboard.** One pinned issue lists every detected update with checkboxes, including ones held back by filters. Reviewers triage a list instead of closing PRs, and you can batch-approve from the dashboard.
3. **Limit concurrent PRs.** `prConcurrentLimit: 5` stops a bot storm after a lockfile overhaul; queued updates wait instead of burying the repo.
4. **Commit body discipline.** Renovate commits carry release notes and changelog links per package; keep `commitBodyTable` enabled so future `git log` archaeology (and this repo's commit-message tooling) can attribute each bump precisely.

## Security and compliance angle

1. **Vulnerability data comes to you.** Renovate matches installed versions against OSV/GHSA and applies `vulnerabilityAlerts` handling — flagged updates can be scheduled immediately, grouped separately, and labeled so patch SLAs are enforceable.
2. **Lockfile integrity is part of the guarantee.** `rangeStrategy: "pin"` and lockFileMaintenance PRs keep digest-level reproducibility, which matters for the Nix/devenv and CI-cache story documented elsewhere in this knowledge base.
3. **Audit the bot like any dependency.** Renovate runs with repo write access via a GitHub App; prefer the official Mend-hosted app or the self-hosted runner (which this repo's fleet tooling could operate) over third-party forks, and review `allowedPostUpgradeCommands` — enabling arbitrary post-upgrade commands is a supply-chain foot-gun.
4. **Scorecards and SBOMs close the loop.** Feed Renovate's activity into OpenSSF Scorecard checks and generate SBOMs in CI; automated updates plus an inventory is what turns dependency management from firefighting into an auditable process.

## Related

1. **Adjacent repo articles.** `changesets-versioning.md` and `semantic-release-setup.md` cover publishing your own packages (Renovate is the consumption side of that pipeline); `commitlint-setup.md` and `git-hooks-husky.md` cover the commit gates these bots must pass.
2. **Primary sources.** docs.renovatebot.com (bot-comparison, configuration-options, config-presets pages) and the GitHub community discussion on Dependabot in npm monorepos ground the comparison above.
