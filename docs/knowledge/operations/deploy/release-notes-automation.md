# release-notes-automation

**Issue:** Generating user-facing release notes automatically from PRs and commits at release time
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Writing release notes by hand is slow, inconsistent, and often skipped. Automating the process from structured commit history and PR metadata produces consistent notes with zero extra work per release.

## Pattern / Solution
**Prerequisites: structured commit messages (Conventional Commits)**
```
feat(checkout): add Apple Pay support
fix(auth): handle expired refresh tokens correctly
perf(search): cache autocomplete results in Redis
chore(deps): bump Node.js to 22.x
```

**GitHub Release Notes automation (built-in)**
```yaml
# .github/release.yml
changelog:
  exclude:
    labels:
      - ignore-for-release
  categories:
    - title: "New Features"
      labels:
        - feature
        - enhancement
    - title: "Bug Fixes"
      labels:
        - bug
        - fix
    - title: "Performance"
      labels:
        - performance
    - title: "Other Changes"
      labels: ["*"]
```

**Automated GitHub Release via CI**
```yaml
- name: Create release
  uses: softprops/action-gh-release@v2
  with:
    generate_release_notes: true
    tag_name: ${{ steps.version.outputs.tag }}
  env:
    GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
```

**Filtering commit types for user-facing notes**
```bash
# Extract only feat/fix/perf between two tags
git log v2.40.0..v2.41.0 \
  --pretty=format:"%s" \
  --no-merges \
  | grep -E "^(feat|fix|perf)" \
  | sed 's/^feat/✨/; s/^fix/🐛/; s/^perf/⚡/'
```

## Gotchas
- Squash-merging PRs discards commit history — use PR title as the changelog entry, not commits
- `chore`, `ci`, `docs`, `test` commits must be excluded from user-facing notes
- Breaking changes (`feat!`) must be highlighted prominently — parse the `!` flag
- Release notes are public in open-source repos — do not include internal ticket IDs or security details

## Related
- `changelog-generation.md`
- `semver-best-practices.md`
- `artifact-versioning-strategy.md`
