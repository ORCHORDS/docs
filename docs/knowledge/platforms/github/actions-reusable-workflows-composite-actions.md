# GitHub Actions — Reusable Workflows and Composite Actions

**Date:** 2026-08-16
**Author:** the platform team
**Status:** published

## Symptom

Your organization has 30 repositories each with a copy-pasted
CI/CD workflow. A security fix to the build step requires editing
30 files across 30 repos. Two teams independently build their own
"setup Node and install deps" workflow steps with subtle differences
that cause inconsistent build environments. A third-party action
pinned to `@v3` (a mutable tag) is compromised — the tag is
repointed to malicious code, and 23,000 repos are affected because
nobody pinned to a commit SHA.

## Context

GitHub Actions provides two mechanisms for reusable CI/CD logic:
reusable workflows (`on: workflow_call`) for job-level and pipeline-
level reuse across repositories, and composite actions (`runs.using:
composite`) for step-level reuse within a single job. Reusable
workflows can define inputs, secrets, and outputs, and support up
to 4 levels of nesting with a maximum of 20 reusable workflow
invocations per run. Composite actions bundle multiple steps into
a single reusable action but cannot span multiple jobs or define
`runs-on`. Versioning strategy — SHA pinning vs tag pinning — is
a critical security decision after the March 2025 `tj-actions/
changed-files` supply chain attack.

## Reusable workflows

```yaml
# .github/workflows/reusable-build.yml
on:
  workflow_call:
    inputs:
      environment:
        type: string
        required: true
      node-version:
        type: string
        default: '20'
    secrets:
      DEPLOY_TOKEN:
        required: true
    outputs:
      image-tag:
        value: ${{ jobs.build.outputs.tag }}

jobs:
  build:
    runs-on: ubuntu-latest
    outputs:
      tag: ${{ steps.meta.outputs.tag }}
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: ${{ inputs.node-version }}
      - run: npm ci && npm run build
      - id: meta
        run: echo "tag=$GITHUB_SHA" >> "$GITHUB_OUTPUT"
```

```yaml
# Caller workflow
jobs:
  call-build:
    uses: org/repo/.github/workflows/reusable-build.yml@v1
    with:
      environment: production
    secrets: inherit
```

```
Limitations:
  → Max nesting: 4 levels deep
  → Max invocations: 20 reusable workflows per run
  → secrets: inherit must be explicit at each hop
  → Caller env context not available inside called workflow
  → Each uses: job is entirely delegated (no inline steps)
```

## Composite actions

```yaml
# .github/actions/setup-build/action.yml
name: 'Setup and Build'
description: 'Install deps and build'
inputs:
  node-version:
    default: '20'
outputs:
  build-id:
    value: ${{ steps.build.outputs.id }}
runs:
  using: composite
  steps:
    - uses: actions/setup-node@v4
      with:
        node-version: ${{ inputs.node-version }}
    - run: npm ci
      shell: bash
    - id: build
      run: |
        npm run build
        echo "id=$(git rev-parse --short HEAD)" >> "$GITHUB_OUTPUT"
      shell: bash
```

```
Composite action rules:
  → shell: required for every run step
  → github.action_path resolves the action's directory
  → Can call other composite actions
  → Can be mixed with inline steps in a job
  → Cannot span multiple jobs
  → Cannot define runs-on
  → Cannot define workflow-level concurrency or permissions
```

## When to use each

```
Need                              Use
──────────────────────────────────────────────────────────────
Step-level reuse within one job   Composite action
(setup, build, lint boilerplate)

Job/pipeline-level orchestration  Reusable workflow
across repos (build→test→deploy)

Different runners per stage       Reusable workflow
(linux build, macos test)

Matrix strategy per stage         Reusable workflow
(test across node versions)

Mixing with inline steps          Composite action
in the same job

Full job permissions/concurrency  Reusable workflow
control
```

## Versioning strategy

```
Approach         Security    Convenience
──────────────────────────────────────────────────────────────
Tag (@v1)        Lower       Higher (auto-updates within
                             major version)

SHA pinning      Higher      Lower (requires Dependabot
(@abc123...)                 to keep current)

Best practices:
  → Pin third-party actions to full commit SHA
  → Use Dependabot to keep pinned SHAs current
  → Reserve mutable tags for first-party/internal actions
  → Since August 2025: GitHub Actions policy supports
    enforcing SHA pinning at org/repo level

Supply chain incident (March 2025):
  tj-actions/changed-files — 350+ tags repointed to
  malicious commit that dumped secrets. ~23,000 repos
  affected. SHA pinning would have prevented exploitation.
```

## Secrets and caching

```
Secrets inheritance:
  → secrets: inherit forwards ALL caller-accessible secrets
  → Convenient but widens blast radius
  → Prefer explicit secrets: mapping for shared/public workflows
  → Secrets don't auto-propagate through intermediate hops
    without explicit forwarding at each level

Caching:
  → actions/cache works identically in composite actions
    and reusable workflows
  → Cache keys should incorporate calling repo/workflow
    context to avoid cross-workflow collisions
  → Cache scope is per-repository (not per-workflow)
```

## Output passing

```
Composite action outputs:
  steps.<id>.outputs → action-level outputs:
  Consumer: steps.<action-step>.outputs.<name>

Reusable workflow outputs:
  1. Step output: steps.<id>.outputs.<name>
  2. Job output: jobs.<job>.outputs.<name> (maps step output)
  3. Workflow output: on.workflow_call.outputs (maps job output)
  4. Consumer: needs.<job>.outputs.<name>

  Three-layer mapping required — step → job → workflow.
```

## Anti-patterns

- **Copy-pasting workflows across repos** — any fix requires
  editing every copy. Extract shared logic into reusable
  workflows or composite actions in a central repository.
- **Using @main or @latest for third-party actions** — mutable
  refs can be repointed to malicious code. Pin to commit SHA.
- **secrets: inherit everywhere** — forwards all secrets to
  called workflows, widening the blast radius. Use explicit
  secret mapping for shared or public workflows.
- **Recursive workflow calls** — self-referential or circular
  reusable workflow calls are rejected by GitHub. Design
  acyclic call chains.

## Gotchas

- **shell: required in composite actions** — every `run` step
  in a composite action must specify `shell: bash` (or another
  shell). Omitting it causes a validation error.
- **env context not inherited** — `env:` set at the caller
  workflow top level is not available inside called reusable
  workflows. Pass values as `inputs` instead.
- **20 reusable workflow limit** — includes nested and duplicated
  invocations across the entire run. Exceeding the limit fails
  the workflow.
- **Intermediate secret forwarding** — in multi-level chains
  (A calls B calls C), secrets must be explicitly forwarded at
  each hop. A single missing `secrets: inherit` breaks the chain
  silently.

## Verification

- Shared CI/CD logic extracted into reusable workflows or composite actions.
- Third-party actions pinned to commit SHA with Dependabot updates.
- Secrets explicitly mapped (not blanket inherited) for shared workflows.
- Output passing tested across workflow/action boundaries.
- Nesting depth verified within 4-level limit.
- SHA pinning policy enforced at organization level.

## Related

- `documentation/docs/policies/github/actions-security-hardening.md`
- `documentation/docs/policies/github/actions-matrix-strategy-optimization.md`
- `documentation/docs/policies/deploy/argocd-flux-gitops-comparison.md`

## Source URLs (verified 2026-08-16)

- GitHub Docs — Reusing Workflows — https://docs.github.com/en/actions/using-workflows/reusing-workflows
- GitHub Docs — Creating a Composite Action — https://docs.github.com/en/actions/creating-actions/creating-a-composite-action
- GitHub Actions Security Hardening — https://docs.github.com/en/actions/security-guides/security-hardening-for-github-actions
- GitHub Blog — Actions Policy SHA Pinning Support — https://github.blog/changelog/2025-08-15-github-actions-policy-now-supports-blocking-and-sha-pinning-actions/
