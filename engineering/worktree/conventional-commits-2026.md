# conventional-commits-2026

**Issue:** A team wants release-please or semantic-release to derive versions from commit history. The history is `"fixed stuff"`, `"updates"`, `"WIP"`. The tool can't determine what shipped. The team falls back to manual versioning.
**Date:** 2026-08-10
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Symptom

Release automation tools (semantic-release, release-please, Changesets) read commit history to determine the next version. They require Conventional Commits — a structured format that maps commit types to SemVer bumps. Without it, the tool can't derive versions, falls back to manual bumping, and the team loses the automation.

## Root cause

Conventional Commits is a specification (currently v1.0.0) that defines a lightweight format for commit messages: `<type>(<scope>): <subject>`, optionally followed by a body and footer. It was designed to make commit history machine-readable.

The Angular commit convention defines the 11 standard types. The format:

```
<type>[optional scope][!]: <description>
[optional body]
[optional footer(s)]
```

## The 11 commit types

| Type | SemVer impact | When to use |
|---|---|---|
| `feat` | MINOR | A new feature for the user |
| `fix` | PATCH | A bug fix for the user |
| `docs` | none | Documentation only changes |
| `style` | none | Formatting, missing semicolons (no logic change) |
| `refactor` | none | Code change that neither adds a feature nor fixes a bug |
| `perf` | PATCH | Performance improvement |
| `test` | none | Adding or correcting tests |
| `build` | none | Changes to build system or dependencies |
| `ci` | none | Changes to CI configuration files and scripts |
| `chore` | none | Routine maintenance (deps, tooling) |
| `revert` | varies | Reverts a previous commit |

`feat` and `fix` are the only two types **required** by the specification. The other types produce no release.

## The breaking change indicator

Breaking changes trigger a MAJOR version bump. There are two ways to indicate one (they can be combined):

**Option 1 — `!` after the type/scope:**

```
feat(api)!: change authentication to use Bearer tokens
```

**Option 2 — `BREAKING CHANGE:` in the footer:**

```
feat(api): change authentication to use Bearer tokens

BREAKING CHANGE: the X-Auth-Token header is no longer accepted.
Use the standard Authorization: Bearer <token> header instead.
```

Either signals a major version bump (1.x.x → 2.0.0). Use `!` for short breaking changes; use `BREAKING CHANGE:` when the explanation is longer.

Any commit type can include a breaking change, not just `feat` or `fix`. A `refactor!: ...` or `chore!: ...` is valid.

## The full structure rules

The spec mandates 16 rules. The most important:

1. Commits MUST be prefixed with a type (`feat`, `fix`, etc.), followed by the OPTIONAL scope, OPTIONAL `!`, and REQUIRED terminal colon and space.
2. A scope MAY be provided after a type. A scope MUST consist of a noun describing a section of the codebase surrounded by parenthesis, e.g., `fix(parser):`.
3. A description MUST immediately follow the colon and space. Imperative mood, no capitalization, no period at end, under 72 characters.
4. A longer commit body MAY be provided after a blank line following the description.
5. One or more footers MAY be provided one blank line after the body. Each footer MUST consist of a word token, followed by `:<space>` or `<space>#` separator, followed by a string value.
6. A footer's token MUST use `-` in place of whitespace (e.g., `Acked-by`). Exception: `BREAKING CHANGE` may also be used as a token.
7. Breaking changes MUST be indicated in the type/scope prefix with `!` OR as a `BREAKING CHANGE:` footer entry.
8. If included as a footer, breaking change MUST be uppercase `BREAKING CHANGE`, followed by colon, space, description.
9. Types other than `feat` and `fix` MAY be used.
10. The units of information that make up Conventional Commits MUST NOT be treated as case-sensitive, with the exception of `BREAKING CHANGE` which MUST be uppercase.

## The scope conventions

A scope is an optional noun in parentheses after the type. It identifies which part of the codebase is affected. Common scopes:

| Scope | Meaning |
|---|---|
| `api` | REST/GraphQL API layer |
| `auth` | Authentication/authorization |
| `ui` | User interface components |
| `core` | Core business logic |
| `deps` | Dependency updates |
| `db` | Database schema or migrations |
| `router` | Routing logic |
| `config` | Configuration files |
| `i18n` | Internationalization |
| `a11y` | Accessibility |

The team agrees on scopes. The closest matching convention (commonly an AOSP-style or Angular-style set) is used consistently.

## The commitlint enforcement pattern

Validate commit messages with commitlint on every commit:

```bash
npm install --save-dev @commitlint/cli @commitlint/config-conventional
```

```bash
# .husky/commit-msg
npx --no -- commitlint --edit $1
```

```javascript
// commitlint.config.js
module.exports = {
  extends: ['@commitlint/config-conventional'],
  rules: {
    'header-max-length': [2, 'always', 100],
    'type-enum': [2, 'always', [
      'feat', 'fix', 'docs', 'style', 'refactor',
      'perf', 'test', 'build', 'ci', 'chore', 'revert'
    ]],
  },
};
```

A `feat: add new endpoint` passes; `fixed the bug` fails. The team can rely on `feat:` / `fix:` to drive release automation.

## The footer references

Footers are useful for issue references and metadata:

```
feat(auth): add OAuth2 PKCE flow

Adds the OAuth2 PKCE authorization code flow for SPAs.
The previous implicit flow is deprecated.

Closes #123
Refs: SECURITY-456
Reviewed-by: alice
```

Common footer tokens:

- `Closes #N` / `Fixes #N` / `Refs #N` — issue references
- `BREAKING CHANGE: <description>` — breaking change explanation
- `Reviewed-by: <name>` — code review
- `Co-authored-by: <name>` — pair programming
- `Signed-off-by: <name>` — DCO signoff

## The squash-merge prerequisite

For release automation to work cleanly with PR-based development, the team must use **squash merges** for PRs. With merge commits, the commit history on `main` contains merge artifacts that confuse version-derivation logic. With squash, each PR becomes a single commit on `main`, and the commit message is the PR title and body.

Configure in the GitHub repository settings: "Allow squash merging" → "Default to squash merge."

## The migration pattern

A team adopting Conventional Commits does not need to rewrite history. Three steps:

1. **Adopt commitlint today.** All new commits follow the spec.
2. **Backfill only if releasing from old history.** If the team is on `v0.5.0` and the next release is the first automated one, backfill old commits with the closest Conventional Commits type. Or just use the first new `feat`/`fix` after adoption as the start of automated versioning.
3. **Configure release-please or semantic-release.** First release is triggered by the first commit with `feat:` or `fix:`. There is no `0.0.1` initialization needed.

## The validation cadence

Run commitlint:

- **On every commit** (via the `commit-msg` hook)
- **On every PR** (via CI): validate the merged commit message
- **On every push to main**: ensure the merge commit follows the convention

A merge that doesn't follow the spec is either rejected (commit-msg hook) or flagged (CI annotation on the PR).

## Verification

The tell that Conventional Commits is working:

- The commit history on `main` is parseable by release-please or semantic-release
- Every commit has a recognizable type; no `"WIP"` or `"updates"` in history
- A `BREAKING CHANGE:` footer or `!` indicator triggers a major version bump automatically
- The team can answer "what shipped in v1.4.2?" by looking at the commit history
- The release PR (or direct release) is generated without human version-bumping

The tell it isn't:

- Commits are `"fixed the bug"`, `"WIP"`, `"updates"`, or `"stuff"`
- The team runs `npm version` by hand
- A `feat!` ships as a minor version
- Two engineers bump the version at the same time and conflict

## Gotchas

- **The first release needs initialization.** release-please: `chore: release 0.0.1` with `Release-As:`. semantic-release: first releasable commit.
- **Commit messages must be accurate.** A `feat:` that should have been a `fix:` triggers a minor version instead of a patch.
- **`BREAKING CHANGE:` must be uppercase.** `breaking change:` (lowercase) is not detected.
- **`!` is the shorthand for breaking change.** `feat!:` and `BREAKING CHANGE:` footer are equivalent; pick one per commit, not both (though combining is allowed).
- **Squash merges are required.** Without them, the commit history on main contains merge artifacts.
- **Commitlint is a per-commit gate.** A PR merged with a non-conforming message is a CI failure.
- **The 11 types are customizable.** A team can add `wip`, `experimental`, etc. — but the spec only guarantees `feat` and `fix` produce releases.

## Related

- `worktree/release-please-semantic-release.md` — the consumer of clean commit messages
- `worktree/husky-lint-staged.md` — the commit-msg hook for commitlint
- `worktree/git-rerere.md` — conflict resolution for the long-lived release branch

## Source URLs (verified 2026-08-10)

- https://www.conventionalcommits.org/en/v1.0.0/
- https://cheatsheets.zip/conventional-commits
- https://ashababnoor.github.io/cheatsheets/conventional-commits
- https://insitechat.ai/blog/conventional-commits-guide-2026
- https://gist.github.com/qoomon/5dfcdf8eec66a051ecd85625518cfd13
