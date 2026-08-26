# github-actions-reusable-2026

**Issue:** A team has 30 repos, each with a copy-pasted CI workflow. The team upgrades Node.js in one repo, forgets the others, and gets 6 months of inconsistent pipelines. The team wants reusable CI/CD in GitHub Actions. The team needs the 2026 decision framework for reusable workflows vs composite actions.

**Date:** 2026-08-10
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Symptom

GitHub Actions offers two reuse mechanisms: **reusable workflows** (entire workflows invoked at job level) and **composite actions** (bundled steps invoked as a step). The two have different limits, different secret access, different logging behavior, different publishability. Picking wrong costs refactoring later.

## Root cause

Reusable workflows are YAML files in `.github/workflows/` with `on: workflow_call`. They can contain multiple jobs, pick their own runners, consume secrets. Called from a job with `uses: org/repo/.github/workflows/file.yml@ref`. Composite actions are `action.yml` files with `runs.using: "composite"`, bundle steps, run on the caller's runner, can't access `secrets` context. Cannot be nested in the same way.

## The 7-axis comparison

| Axis | Reusable workflow | Composite action |
|---|---|---|
| What it is | YAML workflow file | Action with bundled steps |
| Lives in | `.github/workflows/` | Repo or directory with `action.yml` |
| Invoked | `jobs.<id>.uses:` | `steps[].uses:` |
| Jobs | Multiple | None (steps only) |
| Runner | Each job sets its own | Caller's runner |
| Logging | Every step logged separately | Logged as one step |
| Secrets | Can use `secrets:` | Cannot use `secrets` context |
| Marketplace publishable | No | Yes |
| Nesting limit | 10 levels | 10 per workflow |
| Cost | Same (per-minute) | Same (per-minute) |

## The 4-step decision rule

1. **Reusing a pipeline shape (multi-job, multiple runners, gates, secrets)** → reusable workflow.
2. **Reusing a step shape (sequential steps, single runner, no secrets, want Marketplace)** → composite action.
3. **Need to call from many repos, can't change runner** → composite action.
4. **Need to fan out across runners (Linux build + macOS sign)** → reusable workflow.

## The 5 reusable-workflow mechanics

1. **`on: workflow_call`** trigger (not `on: push` or `on: pull_request`).
2. **Inputs** declared in the called workflow's `workflow_call.inputs`, passed by caller as `with:`.
3. **Secrets** declared in `workflow_call.secrets`, passed as `secrets:`. Must use `secrets: inherit` to access all caller secrets.
4. **Outputs** returned via `outputs:` from any job.
5. **Nesting:** 10 levels max; 50 unique reusable workflows per file. Permissions can only be maintained or reduced, never elevated.

## The 4 composite-action mechanics

1. **`action.yml` with `runs.using: "composite"`** and `runs.steps:` array.
2. **Each `run:` step MUST specify `shell:`** - no default.
3. **Inputs** in `inputs:`, used as `${{ inputs.name }}`.
4. **Cannot use `secrets` context** - pass via `inputs:` from the caller.

## The 5 anti-patterns

1. **Pasting the same 80-line workflow into 20 repos.** Use reusable workflows.
2. **Composing a multi-job pipeline with composite actions.** Composite actions cannot contain jobs.
3. **Trying to use `secrets` in a composite action.** Pass as input instead.
4. **Calling a reusable workflow from a step.** Reusable workflows are at job level only.
5. **Exceeding 10 nesting levels.** Audit the call graph if you hit this.

## The 5-step adoption pattern

1. **Audit current pipelines.** Find duplicated steps and jobs.
2. **Pick one repo as the source of truth.** Move the canonical pipeline there.
3. **Reusable workflow for the pipeline skeleton** (build -> test -> deploy).
4. **Composite actions for common steps** (Node.js setup, cache restore, Slack notify, Docker build).
5. **Migrate other repos one at a time**, pointing their workflows at the source of truth.

## The 5 best practices

1. **Pin reusable workflows by SHA in production** (`@sha` not `@main`) for security and reproducibility.
2. **Use semantic versioning for composite actions** that you publish.
3. **Document inputs, secrets, outputs** with `description:` fields in both.
4. **Use `secrets: inherit`** to pass all caller secrets; otherwise list explicitly.
5. **Test the reusable workflow standalone** before depending on it from many repos.

## Verification

The tell that reuse is set up right:

- One source-of-truth repo defines the canonical pipeline
- 20+ repos call into it with `uses: org/source/.github/workflows/ci.yml@v1`
- Composite actions handle the common steps (cache, setup, build)
- Reusable workflow secrets use `secrets: inherit` for the deploy job
- Pipeline updates happen in one place, propagate via version bump

The tell it isn't:

- "We have 30 copies of basically the same workflow"
- Reusable workflow tries to use `secrets` and fails
- Composite action contains 5 jobs and GitHub rejects
- 10+ level deep workflow nesting

## Gotchas

- **Reusable workflow file MUST be in `.github/workflows/`** - subdirectories are not supported.
- **Composite action `shell:` is required** - forgot it and the action fails with confusing error.
- **Permissions can only narrow through the chain.** A reusable workflow cannot grant permissions the caller didn't have.
- **`env:` from caller is NOT passed to reusable workflow.** Pass via inputs.
- **Matrix combinations** still cap at 256 jobs per workflow run, regardless of nesting.

## Related

- `worktree/branch-protection-codeowners-2026.md` - branch protection
- `worktree/dependabot-renovate-2026.md` - dependency updates
- `worktree/secret-scanning-2026.md` - if applicable

## Source URLs (verified 2026-08-10)

- https://docs.github.com/en/actions/concepts/workflows-and-actions/reusing-workflow-configurations
- https://nerdleveltech.com/github-actions-reusable-workflow-vs-composite-action
- https://docs.github.com/en/actions/concepts/workflows-and-actions/composite-actions
- https://docs.github.com/en/actions/security-for-github-actions/security-guides/security-hardening-for-github-actions
- https://www.youngju.dev/blog/devops/2026-03-12-github-actions-reusable-workflows-composite-actions-monorepo
