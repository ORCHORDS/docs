# github-actions-semver-bump

**Issue:** Automatically bumping semantic version based on commit messages or labels
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Manual version bumping is error-prone. Automating it from conventional commits or PR labels keeps versions accurate.

## Pattern / Solution
Using `mathieudutour/github-tag-action`:
```yaml
on:
  push:
    branches: [main]

jobs:
  tag:
    runs-on: ubuntu-latest
    permissions:
      contents: write
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0
      - id: tag
        uses: mathieudutour/github-tag-action@v6.2
        with:
          github_token: ${{ secrets.GITHUB_TOKEN }}
          release_branches: main
          default_bump: patch
      - run: echo "New tag ${{ steps.tag.outputs.new_tag }}"
```
Commit message keywords:
- `feat:` → minor bump
- `fix:` / `perf:` → patch bump
- `BREAKING CHANGE` in footer → major bump

## Gotchas
- `fetch-depth: 0` is required to read the full git history for changelog generation.
- If no conventional commit keyword is found, `default_bump` is used.
- Protect the `main` branch from direct pushes; only merge through PRs so commits follow the convention.
- The action pushes a tag directly — ensure your branch protection allows the Actions bot to push tags.

## Related
- `github-actions-create-release.md`
- `github-commit-message-conventions.md`
