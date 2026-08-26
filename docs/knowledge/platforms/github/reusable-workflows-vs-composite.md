# reusable-workflows-vs-composite

**Issue:** Reusable workflows vs composite actions
**Date:** 2026-08-09
**Status:** documented

## Symptom
You copy-paste the same 50 lines of CI into 10 repos.
Drift sets in. One repo has lint, one has tests.
You wish you had shared CI.

## Root cause
**Without shared CI, drift wins.** Use reusable
workflows.

**Source:** GitHub docs + NerdLevelTech 2026.

## The "reusable workflow" concept

Reusable workflow:
- **File:** `.github/workflows/*.yml`
- **Trigger:** `on: workflow_call`
- **Jobs:** Multiple
- **Runner:** Per job
- **Secrets:** Can use
- **Logging:** Per step

The workflow is per job.

## The "composite action" concept

Composite action:
- **File:** `action.yml` (or `action.yaml`)
- **Runner:** `runs.using: "composite"`
- **Steps:** Sequential
- **Runner:** Caller's
- **Secrets:** Cannot use
- **Logging:** One step

The action is per step.

## The "comparison" pattern

For choice:
| Dim | Reusable wf | Composite action |
|---|---|---|
| File | .github/workflows/ | action.yml |
| Invocation | `uses: ./.github/...` | `uses: org/repo` |
| Jobs | Multiple | None |
| Runner | Per job | Caller's |
| Secrets | Yes | No |
| Marketplace | No | Yes |
| Logging | Per step | One step |
| Nesting | 10 levels | 10 deep |

The choice is per shape.

## The "when to use reusable workflow" pattern

For workflow:
- ✅ Multiple jobs
- ✅ Different runners per job
- ✅ Secrets needed
- ✅ Environment gates
- ✅ Per-step logs
- ✅ Real-time progress

The workflow is for pipelines.

## The "when to use composite action" pattern

For action:
- ✅ Bundle steps
- ✅ Marketplace publish
- ✅ Same job context
- ✅ No secrets needed
- ✅ Pre/post steps in same job

The action is for steps.

## The "reusable workflow example" pattern

For workflow:
```yaml
# .github/workflows/build-and-test.yml
name: Build and Test
on:
  workflow_call:
    inputs:
      node-version:
        required: true
        type: string
    secrets:
      NPM_TOKEN:
        required: true
jobs:
  build:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        node: [18, 20, 22]
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: ${{ inputs.node-version }}
      - run: npm ci
        env:
          NPM_TOKEN: ${{ secrets.NPM_TOKEN }}
      - run: npm test
```

The workflow is structured.

## The "call reusable workflow" pattern

For caller:
```yaml
# .github/workflows/ci.yml
name: CI
on: [push, pull_request]
jobs:
  ci:
    uses: ./.github/workflows/build-and-test.yml
    with:
      node-version: '20'
    secrets:
      NPM_TOKEN: ${{ secrets.NPM_TOKEN }}
```

The call is simple.

## The "composite action example" pattern

For action:
```yaml
# action.yml
name: 'Setup Node + Install'
description: 'Setup Node and install dependencies'
inputs:
  node-version:
    description: 'Node version'
    required: true
runs:
  using: "composite"
  steps:
    - uses: actions/setup-node@v4
      with:
        node-version: ${{ inputs.node-version }}
    - shell: bash
      run: npm ci
    - shell: bash
      run: npm run lint
```

The action is bundle.

## The "use composite action" pattern

For caller:
```yaml
- name: Setup
  uses: org/setup-action@v1
  with:
    node-version: '20'
- name: Test
  run: npm test
```

The use is step.

## The "matrix limitation" pattern

For matrix:
- **Reusable wf:** Matrix must be inside
- **Caller:** Cannot pass matrix as input
- **Workaround:** Inputs influence matrix
- **Limitation:** Pre-2026 still

The matrix is internal.

## The "matrix inside reusable" pattern

For matrix:
```yaml
# Inside reusable
on: workflow_call:
  inputs:
    target:
      required: true
      type: string
jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - run: echo "Deploying to ${{ inputs.target }}"
```

The inputs drive.

## The "matrix fan-out" pattern

For multi-env:
```yaml
jobs:
  deploy-all:
    strategy:
      matrix:
        target: [dev, stage, prod]
    uses: octo-org/repo/.github/workflows/deploy.yml@v1
    with:
      environment: ${{ matrix.target }}
    secrets: inherit
```

The fan is per env.

## The "secret forwarding" pattern

For secrets:
- **Reusable:** Pass via `secrets:` map
- **Not automatic:** Must be explicit
- **`secrets: inherit`:** Pass all

The secret is forwarded.

## The "secrets: inherit" pattern

For all:
```yaml
uses: ./.github/workflows/deploy.yml
with:
  environment: prod
secrets: inherit  # All secrets
```

The inherit is all.

## The "nesting limits" pattern

For limits:
- **10 levels:** Workflow depth
- **50 unique:** Reusables per file
- **10 deep:** Composite actions
- **256 jobs:** Matrix max

The limits are set.

## The "permissions" pattern

For perms:
- **Maintained or reduced:** Through chain
- **Never elevated:** Through chain
- **Per workflow:** Set at top

The perms are tight.

## The "naming convention" pattern

For name:
- **Workflow:** `build.yml`, `deploy.yml`
- **Action:** `action.yml`
- **Org action:** `org/setup`, `org/build`
- **Version:** `v1`, `v1.2`

The name is per file.

## The "pinning" pattern

For version:
- **SHA:** Most secure
- **Tag:** v1 (less secure)
- **Branch:** main (risky)
- **Pin:** Always

The pin is required.

## The "inputs validation" pattern

For validate:
```yaml
on:
  workflow_call:
    inputs:
      node-version:
        required: true
        type: string
      environment:
        type: choice
        options: [dev, staging, prod]
        required: true
```

The input is validated.

## The "outputs" pattern

For outputs:
```yaml
# Reusable
jobs:
  build:
    outputs:
      version: ${{ steps.ver.outputs.v }}
    steps:
      - id: ver
        run: echo "v=1.0" >> $GITHUB_OUTPUT

# Caller
jobs:
  release:
    needs: build
    steps:
      - run: echo "${{ needs.build.outputs.version }}"
```

The output is passed.

## The "no composite for jobs" anti-pattern

For composite:
- **Issue:** Trying to do jobs
- **Fix:** Use reusable workflow

The action is for steps.

## The "copy-paste CI" anti-pattern

For copy:
- **Issue:** Drift
- **Fix:** Reusable workflow

The CI is shared.

## The "no pinning" anti-pattern

For unpinned:
- **Issue:** Security risk
- **Fix:** SHA or tag

The pin is required.

## The "secrets in composite" anti-pattern

For composite:
- **Issue:** Want to use secret
- **Fix:** Use reusable workflow

The action is for non-secret.

## The "matrix not passed" anti-pattern

For caller:
- **Issue:** Want to pass matrix
- **Fix:** Inputs + matrix inside

The matrix is internal.

## The "too deep nesting" anti-pattern

For deep:
- **Issue:** Hard to debug
- **Fix:** Flatten (max 3-4)

The depth is shallow.

## The "centralize" pattern

For CI:
- **Reusable:** Common steps
- **Caller:** Specific trigger
- **Org-wide:** Standard CI
- **Drift:** Eliminated

The CI is centralized.

## The "shared across orgs" pattern

For org:
- **Repo:** `org/shared-workflows`
- **Use:** `uses: org/shared-workflows/.github/workflows/build.yml@main`
- **Pin:** Tag
- **Auth:** Required

The org is shared.

## The "vs GitHub App" pattern

For App:
- **Reusable:** Same repo
- **GitHub App:** Across org
- **Decision:** Same repo = reusable, multi = App

The App is for cross.

## The "no README" anti-pattern

For action:
- **Issue:** Hard to use
- **Fix:** README in repo

The README is required.

## The "naming check" pattern

For check:
- **Available:** Org name + repo
- **Duplicate:** No
- **Versioned:** Tag
- **Public:** For marketplace

The check is before publish.

## The "composite shell" pattern

For shell:
- **Required:** Every `run` needs `shell:`
- **No default:** Unlike workflow

The shell is required.

## The "composite marketplace" pattern

For publish:
- **GitHub Marketplace:** Yes
- **Reusable:** No
- **Version:** SemVer
- **Docs:** Required

The marketplace is for action.

## The "reusable checklist" pattern

For checklist:
- [ ] on: workflow_call
- [ ] Inputs validated
- [ ] Secrets explicit
- [ ] Pin to SHA
- [ ] Output declared
- [ ] Matrix inside
- [ ] Permissions tight
- [ ] Documented in README

The checklist is 8.

## Verification
- **Test:** Caller works
- **Test:** Inputs flow
- **Test:** Secrets flow
- **Test:** Outputs return
- **Audit:** Quarterly

## Gotchas
- **The "copy-paste CI" anti-pattern.** Reusable.
- **The "no pinning" anti-pattern.** SHA.
- **The "secrets in composite" anti-pattern.** Reusable.

## Related
- `github/github-actions-reusable-workflows.md`
- `github/branch-protection-and-codeowners.md`
- `github/issue-and-pr-templates.md`
- `worktree/git-hooks-2026.md`
- `infra/arc-github-runners-k8s.md`
- `infra/monorepo-2026.md`
- GitHub docs: https://docs.github.com/en/actions/concepts/workflows-and-actions/reusing-workflow-configurations
- NerdLevelTech: https://nerdleveltech.com/github-actions-reusable-workflow-vs-composite-action
- Sachith: https://www.sachith.co.uk/github-actions-reusable-workflows-matrices-from-zero-to-production-practical-guide-may-7-2026/
