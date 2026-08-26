# GitHub Actions Starter Workflow Templates — Organization-Wide Standards

Date: 2026-08-23
Author: example.com
Status: production

---

## Symptom / Use-case

Every new repository in the organization bootstraps its own workflow from scratch,
leading to inconsistent lint configs, missing OIDC scopes, and divergent Wrangler
versions across 40+ Workers repos. Engineers copy-paste old workflows and forget to
update token permissions or pinned action SHAs.

Starter workflow templates — stored in `.github/workflow-templates/` on the `.github`
repository — appear in the GitHub Actions "New workflow" picker for every repo in the
org. They differ from *reusable workflows*: they are **copied** into the target repo
(not called via `uses:`), so teams can customize from a known-good starting point.

---

## Context

Organization starter workflows live at:

```
{org}/.github/                        ← the special org-level repo
  workflow-templates/
    workers-deploy.yml                ← the template YAML
    workers-deploy.properties.json    ← metadata (name, description, icon)
    workers-ci.yml
    workers-ci.properties.json
```

The `.github` repository must be public (or internal in GHES) for the templates to
appear to members. Each template YAML can use `$default-branch` as a placeholder that
GitHub replaces with the target repo's default branch name on copy.

---

## 1. Properties Metadata File

Every template needs a paired `.properties.json` file with the same base name:

```json
{
  "name": "Cloudflare Workers Deploy",
  "description": "OIDC-based deploy to Cloudflare Workers for production and preview environments",
  "iconName": "octicon-rocket",
  "categories": ["Deployment", "Cloudflare"],
  "filePatterns": ["wrangler.toml", "wrangler.json"]
}
```

- `filePatterns`: GitHub pre-filters and highlights this template in the picker when
  any of the listed files exist in the new repo.
- `iconName`: any Octicon name; shown in the template card.
- `categories`: free-form strings used by the picker's filter sidebar.

---

## 2. Workers Deploy Starter Template

```yaml
# .github/workflow-templates/workers-deploy.yml
name: Deploy Workers

on:
  push:
    branches: [$default-branch]
  workflow_dispatch:

permissions:
  contents: read
  id-token: write   # required for OIDC token exchange with Cloudflare

jobs:
  deploy:
    name: Deploy to Cloudflare Workers
    runs-on: ubuntu-latest
    environment: production
    concurrency:
      group: workers-deploy-production
      cancel-in-progress: false   # never cancel a production deploy mid-flight

    steps:
      - uses: actions/checkout@v4
        with:
          persist-credentials: false

      # Pin Wrangler version org-wide; update via Dependabot
      - name: Deploy
        uses: cloudflare/wrangler-action@v3
        with:
          apiToken: ${{ secrets.CF_API_TOKEN }}
          accountId: ${{ secrets.CF_ACCOUNT_ID }}
          command: deploy --env production
```

---

## 3. Workers CI Starter Template

```yaml
# .github/workflow-templates/workers-ci.yml
name: Workers CI

on:
  pull_request:
    branches: [$default-branch]

permissions:
  contents: read
  checks: write       # for test result annotations
  pull-requests: read

jobs:
  test:
    name: Unit tests
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          persist-credentials: false

      - uses: actions/setup-node@v4
        with:
          node-version-file: .nvmrc
          cache: pnpm

      - run: pnpm install --frozen-lockfile

      - name: Run Vitest with Workers pool
        run: pnpm test --reporter=junit --outputFile=test-results/junit.xml
        env:
          MINIFLARE_WORKERS_POOL: "1"

      - name: Upload test results
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: test-results
          path: test-results/
          retention-days: 7
```

---

## 4. Automating Template Version Bumps via Dependabot

Dependabot cannot update action SHAs inside `workflow-templates/` automatically
because these files are not live workflows. Use a separate meta-workflow to open
PRs whenever upstream actions release a new version:

```yaml
# .github/workflows/sync-template-shas.yml
name: Sync template action SHAs

on:
  schedule:
    - cron: "0 8 * * 1"   # every Monday 08:00 UTC
  workflow_dispatch:

permissions:
  contents: write
  pull-requests: write

jobs:
  sync:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Update pinned SHAs in templates
        run: |
          # Example: resolve latest SHA for actions/checkout@v4
          SHA=$(gh api /repos/actions/checkout/git/refs/tags/v4 \
                  --jq '.object.sha' 2>/dev/null || \
                gh api /repos/actions/checkout/commits?per_page=1 \
                  --jq '.[0].sha')
          sed -i "s|actions/checkout@[a-f0-9]*|actions/checkout@${SHA}|g" \
            .github/workflow-templates/*.yml
        env:
          GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}

      - name: Open PR if changed
        uses: peter-evans/create-pull-request@v7
        with:
          branch: chore/sync-template-shas
          commit-message: "chore: sync action SHAs in workflow templates"
          title: "chore: sync pinned SHAs in starter workflow templates"
          body: "Automated SHA bump for starter workflow templates."
```

---

## 5. Validating Templates in CI

Starter templates are YAML and must parse correctly, but GitHub does not lint them on
push. Add a validation step to the `.github` repo's own CI:

```yaml
# .github/workflows/validate-templates.yml
name: Validate workflow templates

on:
  pull_request:
    paths:
      - "workflow-templates/**"

jobs:
  validate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Install actionlint
        run: |
          bash <(curl -Ls https://raw.githubusercontent.com/rhysd/actionlint/main/scripts/download-actionlint.bash)

      - name: Lint templates
        run: |
          # actionlint supports $default-branch as a special placeholder
          ./actionlint .github/workflow-templates/*.yml

      - name: Validate properties JSON
        run: |
          for f in .github/workflow-templates/*.properties.json; do
            python3 -c "import json,sys; json.load(open('$f'))" \
              && echo "OK: $f" || { echo "INVALID: $f"; exit 1; }
          done
```

---

## Anti-patterns

- **Using `${{ secrets.X }}` in template bodies**: Secret names used in templates must
  exist in the *target* repo; document required secrets in the template's description,
  not hardcoded values.
- **Shipping mutable `@v3`-style references**: Always commit full SHA pins in templates;
  use the sync workflow above to keep them current.
- **Skipping the `.properties.json` file**: Templates without a paired properties file
  are not surfaced in the Actions picker UI.
- **Putting templates in the wrong branch**: GitHub reads `workflow-templates/` from the
  `.github` repository's **default branch** only.

---

## Gotchas

- `$default-branch` is the only supported placeholder; custom variables are not
  interpolated — values like `$ORG_NAME` are treated as literals and will cause syntax
  errors in the target repo after copy.
- Templates are **copied**, not referenced. Changes to templates do not propagate to
  existing repos; only new repos picking up the template receive the update.
- The `.github` repository must be **public** or **internal** (enterprise). Private
  `.github` repos do not expose templates to org members.
- `filePatterns` matching is advisory — it only affects picker prominence, not
  availability. All templates are always copyable by any repo member.

---

## Verification

1. Navigate to any org repo → **Actions** → **New workflow**.
2. Scroll to the *"By {org}"* section; verify your templates appear with correct icons.
3. Click *"Configure"* on a template, confirm `$default-branch` is replaced with
   `main` (or the repo's default branch) in the editor.
4. Run `./actionlint .github/workflow-templates/*.yml` locally — exit 0 expected.

---

## Related

- `actions-reusable-workflows-composite-actions.md`
- `github-actions-reusable-workflows.md`
- `reusable-workflows-vs-composite.md`
- `github-actions-security-hardening.md`
- `actions-policy-sha-pinning-and-blocklists-2026.md`

---

## Sources

- https://docs.github.com/en/actions/using-workflows/creating-starter-workflows-for-your-organization
- https://github.com/rhysd/actionlint
- https://docs.github.com/en/repositories/creating-and-managing-repositories/creating-a-template-repository
