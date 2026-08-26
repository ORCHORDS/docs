# github-org-variables-config-hierarchy

**Issue:** Workflows accumulate configuration: registry hostnames, environment names, feature toggles, region names, timeout values. Naive teams hardcode these into every workflow (drifts per file), duplicate them as secrets (wrong primitive — secrets are masked and awkward to read), or copy-paste an env block across fifty repos (unfixable the day one value changes). GitHub Actions has a real configuration hierarchy for this: configuration variables at organization, repository, and environment levels, exposed through the `vars` context, with lower layers overriding higher ones. Used deliberately, `vars` gives an org a single place to set a default (say, the container registry URL) that every repo inherits and any repo or environment can override — the same pattern as a conventional config hierarchy, but native to the platform and auditable through the settings UI and API. Misused, it becomes an invisible pile of snowflake values nobody can inventory.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## The three layers and their precedence

1. **Organization variables.** Org owners create them under Settings → Secrets and variables → Actions → Variables, and scope access with a repository access policy — all repositories, private only, or an explicit list. This is where org-wide defaults live: registry endpoints, default deploy regions, shared webhook URLs, tool version pins. Note that org-level variables are not available to private repositories on GitHub Free plans — a constraint that decides the layer choice for free-tier orgs.
2. **Repository variables.** Anyone with write access to an org repo (or collaborator access on a personal repo) can define repo-level variables. A repo variable with the same name as an org variable shadows it for that repository, which is the override mechanism: org sets the default, repo flips it.
3. **Environment variables (the Actions kind).** Defined per environment under Settings → Environments, these override repo and org values for jobs that reference that environment. Production vs staging differences — API URLs, cluster names, approval thresholds — belong here, because environments already carry the protection rules that gate where those values are used.
4. **Resolution is most-specific wins.** A job referencing environment `production` sees environment variables over repo variables over org variables. Unlike secrets, configuration variables are plain values readable in logs — choose the layer for override semantics, not for secrecy.

## vars vs env vs secrets — the decision rules

1. **`vars` for configuration, `secrets` for credentials.** The `vars` context holds non-sensitive settings; secrets are masked everywhere and access-audited. If a value would embarrass you printed in a log, it is a secret; if engineers argue about its value in Slack, it is a variable.
2. **Workflow-level `env` for literal, in-file constants.** The `env:` block in a workflow is versioned with the code and visible in review — the right place for values that change only with the workflow itself. Promotion of an `env` literal into a `var` is justified the moment a second workflow or repo needs the same value.
3. **Context syntax where the runner never runs.** In `if:` conditionals and other sections not sent to the runner, shell-style variables do not exist — use `${{ vars.NAME }}` and `${{ env.NAME }}` contexts. Undefined `vars` references resolve to an empty string, so a typo produces a silently-wrong default, not an error; guard critical reads with explicit checks.
4. **Runner-side defaults stay distinct.** Platform defaults like `RUNNER_OS` (and the `runner.os` context) exist independently of your variables; name custom variables so they never shadow or mimic the reserved `GITHUB_*` namespace.

## A working hierarchy pattern

1. **Org layer sets convention, not policy.** Org variables should hold the values every repo shares and almost none override: `REGISTRY`, `DEFAULT_REGION`, `TOOLING_BUCKET`. Keep the count low — an org variable list of 200 is a junk drawer, not a convention.
2. **Repo layer holds identity.** Repo variables are for what makes this repo different: its service name, its deploy targets, its toggles. If more than a handful of repos override the same org variable, the org default was wrong — fix the default, delete the overrides.
3. **Environment layer holds deployment topology.** Anything that differs between staging and production lives per-environment, which also means changing it requires environment-adjacent permissions rather than workflow-file write access — a free security improvement.
4. **Inventory through the API, not memory.** Org and repo variables are managed through the GitHub REST/GraphQL API (the variables endpoints). A periodic export script that dumps the effective hierarchy per repo is the only way to answer "where is REGION set and what wins" in a 40-repo org.

## Failure modes and guardrails

1. **Empty-string propagation.** Because undefined `vars` resolve to empty strings, a deleted org variable silently blanks every workflow that referenced it. Delete through a two-step (rename to `DEPRECATED_*`, then remove after a quarantine window) and grep workflows for the name first.
2. **Free-plan org-layer gaps.** On GitHub Free, private repositories cannot read org-level variables — teams discover this when a repo works locally but resolves blank in CI. Either move the value to repo scope for private repos on Free, or accept that the hierarchy starts at the repo layer on that plan.
3. **Values in variables pretending to be secrets.** Configuration variables are readable by anyone with read access to the run environment configuration and appear in expanded contexts; tokens, keys, and certificates must be secrets or OIDC-federated away entirely.
4. **Unreviewable magic.** A workflow whose behavior hinges on a variable nobody remembers setting is unreviewable. Reference variables sparingly, name them after their effect (`DEPLOY_STRATEGY`, not `FLAG_3`), and document each org variable's meaning in the org README or wiki when it is created.
5. **Layer fights.** When the same name is defined at all three layers, debugging which value won requires checking three settings pages. An org policy lint — fail CI if a repo defines a variable that exists at org scope without a matching override-approval label — keeps the hierarchy intentional.
