# github-required-status-checks

**Issue:** Configuring required status checks so branches can only merge when CI passes
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
PRs merge even when tests fail because status checks aren't enforced. Or required checks are configured by job name and break silently when a workflow is renamed.

## Pattern / Solution
Required status checks are configured in branch protection rules (Settings → Branches → Add rule → Require status checks to pass).

**The check name is the job name (or step name for external checks):**
```yaml
# .github/workflows/ci.yml
jobs:
  test:          # <-- this is the check name "test"
    runs-on: ubuntu-latest
    steps:
      - run: npm test

  lint:          # <-- check name "lint"
    runs-on: ubuntu-latest
    steps:
      - run: npm run lint
```

Add `test` and `lint` as required checks in branch protection.

**Handling path-filtered workflows (check goes "missing"):**
```yaml
on:
  pull_request:
    paths:
      - 'src/**'

jobs:
  # Always run a minimal job so the check is never "missing"
  required-check:
    runs-on: ubuntu-latest
    steps:
      - run: echo "Check present"

  test:
    if: ... # conditional on paths
```

**Using GitHub Rulesets instead of legacy branch protection:**
```bash
gh api repos/OWNER/REPO/rulesets \
  --method POST \
  --input - <<'EOF'
{
  "name": "main-protection",
  "target": "branch",
  "enforcement": "active",
  "conditions": {"ref_name": {"include": ["refs/heads/main"], "exclude": []}},
  "rules": [
    {"type": "required_status_checks",
     "parameters": {
       "required_status_checks": [{"context": "test"}, {"context": "lint"}],
       "strict_required_status_checks_policy": true
     }}
  ]
}
EOF
```

**`strict_required_status_checks_policy: true`** means the branch must also be up to date with the base before merging.

## Gotchas
- Check names are exact-match strings — renaming a workflow file or job name silently removes the check without warning
- Checks from reusable workflows appear as `workflow-name / job-name` in the UI — add the full qualified name as the required check
- "Require branches to be up to date" (strict mode) causes extra friction in high-traffic repos — combine with merge queue instead
- Status checks from `merge_group` events must also be added as required checks for merge queue to work
- Skipped checks (from path filters) count as "passing" only if the branch protection rule has "skipped checks are passing" enabled

## Related
- `branch-protection-and-codeowners.md`
- `github-merge-queue.md`
- `github-rulesets-2026.md`
