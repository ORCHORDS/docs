# github-actions-importer-ci-migration

**Issue:** Engineering organizations consolidating CI spend and tooling frequently need to move years of Jenkinsfiles, `.gitlab-ci.yml` pipelines, CircleCI configs, and Azure DevOps definitions onto GitHub Actions. Doing this repo-by-repo by hand is slow and error-prone; doing it purely with an automated converter produces workflows that pass syntax validation but silently diverge from the original pipeline's semantics — missing credentials bindings, dropped manual-approval gates, or flaky custom plugins with no Actions equivalent. The engineering problem is designing a migration program that uses GitHub Actions Importer for mechanical translation while budgeting real effort for the semantic gap, the credential model change, and the post-migration deprecation debt (migrating onto already-EOL action versions is a classic own-goal). As of 2026 the Importer remains an active, maintained tool — `gh actions-importer update` ships regular releases — and the docs present two supported paths: automated migration via Importer, and the manual migration guide.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## The migration program shape

1. **Inventory before converting.** Importer's `audit` command crawls the source CI system (Jenkins, GitLab, CircleCI, Azure DevOps, Bitbucket Pipelines, Travis CI) and produces a CSV/JSON inventory of every pipeline with its build statistics. Run it first: the audit report is what you use to tier the migration — high-change-rate services first, archived pipelines never.
2. **Forecast the translation gap.** The `forecast` command estimates what fraction of each pipeline converts cleanly based on historical usage. Its output drives the real decisions: pipelines with heavy custom plugin usage get manual treatment budgeted up front instead of being discovered mid-migration.
3. **Dry-run before you write anything.** `gh actions-importer dry-run` converts pipelines to workflow files without committing, and flags each construct that fell into an `unknown` or `action-` placeholder mapping. Review the dry-run diff the same way you review a PR — placeholders are the semantic gap made visible.
4. **Convert into a migration branch, not main.** Generated workflows land on a branch where the team replaces placeholders, rebinds credentials, and re-adds gates. The PR review of that branch is effectively the migration's acceptance test.

## Mapping concepts across systems

1. **Jobs and stages map to jobs and needs.** Jenkins stages, GitLab stages/jobs, and CircleCI jobs become Actions jobs wired with `needs`; fan-in/fan-out graphs translate well. What does not translate automatically: Jenkins node labels become `runs-on` with a best guess, so self-hosted runner pools need explicit label strategy.
2. **Credentials need a model change, not translation.** Jenkins credentials bindings and GitLab CI/CD variables become GitHub-hosted secrets, environment secrets, or — the 2026-correct default for cloud deploys — OIDC federation to the cloud provider with no long-lived secret at all. Never let a converter paste a cloud key into a repo secret when OIDC is available.
3. **Manual approvals become environments.** Jenkins input steps and Azure DevOps approvals map to GitHub environments with required reviewers and deployment protection rules. This is one of the mappings Importer handles least well, so expect to rebuild approval gates by hand.
4. **Custom plugins become actions or scripts.** Jenkins plugins and GitLab `include:` templates rarely have exact equivalents; the standard resolution is a composite action or a reusable workflow in an internal collection, so each migrated pipeline composes shared building blocks instead of forked scripts.

## Post-migration hygiene

1. **Do not migrate onto dead action versions.** Migrations that emit `actions/upload-artifact@v3` style references are broken on arrival — v3 artifact actions were retired in January 2025. Pin every generated action to a current major on a recent SHA, and let Dependabot/Renovate own ongoing updates from day one.
2. **Re-tune concurrency immediately.** Source systems' queue semantics do not carry over. Add `concurrency` groups keyed on the ref so cancel-in-progress replaces the old build queue's behavior, otherwise migrated repos double-spend CI minutes on stacked PRs.
3. **Port dashboards and badges.** Jenkins Blue Ocean views, GitLab pipeline badges, and Slack notifications all have Actions equivalents (job summaries, status badges, `slackapi/slack-github-action`). Budget a day per team for the observability gap or users will keep the old system alive "just to check history."
4. **Decommission with a freeze window.** Keep the source CI read-only for one sprint after cutover for audit history, then archive. Migrations stall permanently at 90% when the old system keeps accepting new pipelines.

## Program management lessons

1. **Measure in pipelines retired, not converted.** A converted-but-unmerged workflow is negative progress. Track the burn-down of builds executing on the legacy system — that is the number that ends the contract spend.
2. **Codify the patterns as you go.** Every manual fix applied during migration should be promoted into a shared reusable workflow or composite action, so migration fifty costs a fraction of migration five.
3. **Keep Importer current.** Translation coverage improves release over release; running `gh actions-importer update` before each wave picks up newly supported transformers and reduces placeholder churn between waves.
4. **Document the exceptions list.** Some pipelines (agent-coupled Jenkins jobs, on-prem hardware tests) are intentionally not migratable. Writing that list down early stops the program from being judged against a 100% target nobody planned to hit.
