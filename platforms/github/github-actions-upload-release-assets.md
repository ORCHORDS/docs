# github-actions-upload-release-assets

**Issue:** Uploading binary artefacts to a GitHub Release from a workflow
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
After building a cross-platform binary you want to attach it to a release so users can download it directly from the Releases page.

## Pattern / Solution
```yaml
jobs:
  release:
    runs-on: ubuntu-latest
    permissions:
      contents: write
    steps:
      - uses: actions/checkout@v4
      - name: Build
        run: make dist
      - name: Upload release asset
        uses: softprops/action-gh-release@v2
        with:
          files: |
            dist/myapp-linux-amd64
            dist/myapp-darwin-arm64
            dist/myapp-windows-amd64.exe
```
Using the GitHub CLI directly:
```bash
gh release upload "$TAG" dist/* --clobber
```

## Gotchas
- `permissions: contents: write` is required; default read-only GITHUB_TOKEN cannot upload assets.
- `softprops/action-gh-release` creates the release if it does not exist — useful in tag-triggered workflows.
- Asset names must be unique per release; use `--clobber` with `gh` to overwrite.
- Maximum individual asset size is 2 GB.

## Related
- `github-actions-create-release.md`
- `github-release-automation-2026.md`
