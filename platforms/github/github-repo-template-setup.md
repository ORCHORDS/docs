# github-repo-template-setup

**Issue:** Creating and using GitHub repository templates for consistent project scaffolding
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
New repos in an org should start with standard CI workflows, branch protection, issue templates, and tooling config without copy-pasting.

## Pattern / Solution
Mark a repo as a template:
- Settings → General → Template repository (check the box).

What is copied when using the template:
- All files and directories (excluding `.git` history)
- `.github/` workflows, templates, CODEOWNERS
- Any config files (`.eslintrc`, `pyproject.toml`, etc.)

Create from template via CLI:
```bash
gh repo create my-new-service \
  --template org/repo-template \
  --private \
  --clone
```
Automate post-creation setup with a workflow triggered on `create`:
```yaml
on:
  create:
jobs:
  setup:
    if: github.ref == 'refs/heads/main' && github.event.ref_type == 'branch'
    runs-on: ubuntu-latest
    steps:
      - run: echo "New repo initialised from template"
```

## Gotchas
- Template repos cannot include wikis or GitHub Actions secrets.
- Branch protection rules are not copied; apply them via the API post-creation.
- The `create` event only fires once; a guard on `refs/heads/main` prevents re-runs.
- Workflows in templates use the new repo's `GITHUB_TOKEN` — no extra permissions needed.

## Related
- `github-organization-settings.md`
- `issue-and-pr-templates.md`
