# github-wiki-vs-docs

**Issue:** Choosing between GitHub Wiki, repo /docs, and GitHub Pages for project documentation
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Teams dump docs in the wiki but discover it's not reviewable via PRs, not searchable from the main repo, and not versioned alongside code. Knowing when to use each option prevents documentation debt.

## Pattern / Solution
Three primary options exist, each with different trade-offs:

**GitHub Wiki**
- Editable directly in the UI; no PR workflow
- Good for: internal runbooks, meeting notes, scratch-pad docs that don't need code review
- Bad for: versioned API docs, anything that should change atomically with code
- Cloneable: `git clone https://github.com/OWNER/REPO.wiki.git`
- Not included in repo search; separate search index

**`/docs` directory in repo**
- Markdown files committed alongside code; reviewed in PRs
- Good for: architecture decisions (ADRs), contribution guides, API references that change with code
- Versioned per branch/tag — `git checkout v1.2.0 -- docs/` shows old docs
- Can be published to GitHub Pages automatically

**GitHub Pages (from `/docs` or `gh-pages` branch)**
```yaml
# .github/workflows/docs.yml
name: Deploy docs

on:
  push:
    branches: [main]
    paths: ['docs/**']

permissions:
  contents: read
  pages: write
  id-token: write

jobs:
  deploy:
    runs-on: ubuntu-latest
    environment:
      name: github-pages
      url: ${{ steps.deployment.outputs.page_url }}
    steps:
      - uses: actions/checkout@v4
      - uses: actions/configure-pages@v5
      - uses: actions/upload-pages-artifact@v3
        with:
          path: docs/
      - uses: actions/deploy-pages@v4
        id: deployment
```

**Decision matrix:**
| Need | Best option |
|------|-------------|
| Code-reviewed, versioned docs | `/docs` in repo |
| Public website | GitHub Pages |
| Internal notes, unreviewed | Wiki |
| API reference auto-generated | Pages from CI |

## Gotchas
- Wiki edits bypass branch protection — anyone with write access can modify without review
- GitHub Pages has a 1 GB size limit and 100 GB/month bandwidth limit for public repos
- The `gh-pages` branch approach is legacy; the Actions-based Pages deployment (via `upload-pages-artifact`) is the current recommended pattern
- Private repo GitHub Pages requires at least a GitHub Team plan
- Wiki is disabled by default in forked repos

## Related
- `github-discussions-2026.md`
- `github-release-automation-2026.md`
- `issue-and-pr-templates.md`
