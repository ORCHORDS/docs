# github-actions-create-release

**Issue:** Automatically creating a GitHub Release when a tag is pushed
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
On `git push --tags` you want a GitHub Release created with auto-generated release notes.

## Pattern / Solution
```yaml
on:
  push:
    tags: ["v*.*.*"]

jobs:
  release:
    runs-on: ubuntu-latest
    permissions:
      contents: write
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0
      - name: Create release
        uses: softprops/action-gh-release@v2
        with:
          generate_release_notes: true
          draft: false
          prerelease: ${{ contains(github.ref_name, '-rc') }}
```
Via `gh` CLI:
```bash
gh release create "${{ github.ref_name }}" \
  --generate-notes \
  --title "Release ${{ github.ref_name }}"
```

## Gotchas
- `fetch-depth: 0` is required if the action generates a changelog from git history.
- `generate_release_notes: true` uses GitHub's built-in release notes based on merged PR titles.
- Draft releases are not visible to users; set `draft: false` for immediate publishing.
- Tag must exist in the remote before the workflow triggers.

## Related
- `github-actions-upload-release-assets.md`
- `github-actions-semver-bump.md`
- `github-release-automation-2026.md`
