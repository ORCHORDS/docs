# github-actions-deploy-pages

**Issue:** Deploying a static site to GitHub Pages via Actions with the official flow
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
GitHub Pages historically required a `gh-pages` branch. The modern approach uses the `actions/deploy-pages` action with OIDC and no branch needed.

## Pattern / Solution
```yaml
on:
  push:
    branches: [main]

permissions:
  contents: read
  pages: write
  id-token: write

concurrency:
  group: pages
  cancel-in-progress: false

jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: npm ci && npm run build
      - uses: actions/upload-pages-artifact@v3
        with:
          path: dist/

  deploy:
    needs: build
    environment:
      name: github-pages
      url: ${{ steps.deployment.outputs.page_url }}
    runs-on: ubuntu-latest
    steps:
      - id: deployment
        uses: actions/deploy-pages@v4
```

## Gotchas
- Enable Pages in repo Settings → Pages → Source: GitHub Actions (not a branch).
- `id-token: write` permission is required for OIDC-based deployment.
- The `cancel-in-progress: false` on the concurrency group prevents a deploy from being cancelled mid-flight.
- Custom domains require a `CNAME` file in the build output or configured in repo settings.

## Related
- `github-actions-environment-protection.md`
- `github-actions-oidc-cloudflare.md`
