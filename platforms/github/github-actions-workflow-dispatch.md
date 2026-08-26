# github-actions-workflow-dispatch

**Issue:** Triggering workflows manually with typed inputs via UI or API
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Teams need one-off workflow runs with runtime parameters — deploying a specific version, running a migration against a chosen environment, or kicking off a release with a custom tag. Hard-coded triggers don't cover these cases.

## Pattern / Solution
`workflow_dispatch` exposes a form in the Actions UI and an API endpoint for scripted triggers.

**Basic dispatch with typed inputs:**
```yaml
on:
  workflow_dispatch:
    inputs:
      environment:
        description: Target environment
        required: true
        type: choice
        options: [staging, production]
        default: staging
      version:
        description: Image tag to deploy
        required: true
        type: string
      dry_run:
        description: Skip actual deploy
        required: false
        type: boolean
        default: false

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - name: Deploy
        if: ${{ !inputs.dry_run }}
        run: |
          ./deploy.sh \
            --env "${{ inputs.environment }}" \
            --version "${{ inputs.version }}"
```

**Trigger via `gh` CLI:**
```bash
gh workflow run deploy.yml \
  --ref main \
  --field environment=production \
  --field version=v2.3.1 \
  --field dry_run=false
```

**Trigger via REST API:**
```bash
curl -X POST \
  -H "Authorization: Bearer $TOKEN" \
  -H "Accept: application/vnd.github+json" \
  https://api.github.com/repos/OWNER/REPO/actions/workflows/deploy.yml/dispatches \
  -d '{"ref":"main","inputs":{"environment":"production","version":"v2.3.1"}}'
```

## Gotchas
- `workflow_dispatch` only appears in the UI when the workflow file exists on the **default branch** — testing on a feature branch won't show the button
- Input values are always strings in the runner even when declared as `boolean` or `number` — compare with `== 'true'` not `== true` in shell
- Maximum of 10 inputs per workflow
- The dispatched run is not linked to any PR or commit context — `github.sha` is the HEAD of the ref you specified
- `type: environment` input (showing configured environments) requires the repo to have at least one environment created

## Related
- `github-actions-environment-protection.md`
- `github-actions-secrets-management.md`
- `github-actions-reusable-workflows.md`
