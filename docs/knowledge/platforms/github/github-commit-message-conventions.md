# github-commit-message-conventions

**Issue:** Writing and enforcing conventional commit messages for changelog and semver automation
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Inconsistent commit messages make release notes, changelogs, and automated version bumping impossible.

## Pattern / Solution
Conventional Commits format:
```
<type>(<scope>): <short summary>

[optional body]

[optional footer(s)]
BREAKING CHANGE: <description>
```
Types: `feat`, `fix`, `docs`, `style`, `refactor`, `perf`, `test`, `chore`, `ci`, `build`, `revert`

Examples:
```
feat(auth): add OAuth2 PKCE flow
fix(payments): handle timeout on charge endpoint
chore(deps): bump lodash from 4.17.20 to 4.17.21
feat!: remove deprecated v1 API endpoints
```
Enforce with commitlint:
```yaml
      - uses: wagoid/commitlint-github-action@v6
        with:
          configFile: .commitlintrc.yml
```

## Gotchas
- `feat!:` or `BREAKING CHANGE:` in the footer triggers a major semver bump in tools like semantic-release.
- The scope is optional but recommended in monorepos to identify the affected package.
- Keep the summary under 72 characters so it fits in `git log --oneline`.
- Squash-merge PR titles must also follow the convention if you use title-based changelog generation.

## Related
- `github-actions-semver-bump.md`
- `github-squash-vs-merge-vs-rebase.md`
