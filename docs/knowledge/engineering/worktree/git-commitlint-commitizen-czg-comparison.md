# Conventional Commits Tooling: commitlint vs commitizen vs czg

- **Date**: 2026-08-23
- **Author**: example.com
- **Status**: production

## Symptom / Use-case
The team has agreed on Conventional Commits but engineers write freeform messages in their local editors, causing `semantic-release` or `release-please` to silently skip version bumps — and nobody notices until a deploy goes out with the wrong version.

## Context
Three tools dominate the Conventional Commits enforcement space in 2026: `commitlint` (a linter — it validates after the fact), `commitizen` (an interactive CLI prompt — it guides before the fact), and `czg` (a modern reimplementation of commitizen with better monorepo and emoji support). Cloudflare Workers monorepos using pnpm workspaces benefit from understanding which tool enforces what, at which hook point, and at what performance cost.

## Tool roles at a glance
```
┌─────────────────┬──────────────────┬──────────────────────────────────────────┐
│ Tool            │ Hook point       │ What it does                             │
├─────────────────┼──────────────────┼──────────────────────────────────────────┤
│ commitlint      │ commit-msg       │ Validates the message AFTER you type it  │
│ commitizen      │ replaces git cit │ Interactive prompt; writes the message   │
│ czg             │ replaces git cit │ Same as commitizen, faster, richer UI    │
│ husky/lefthook  │ (hook runner)    │ Executes any of the above at hook points │
└─────────────────┴──────────────────┴──────────────────────────────────────────┘
```

They are complementary, not mutually exclusive. The canonical setup: czg or commitizen for interactive commits, commitlint as the `commit-msg` guard.

## commitlint: validation-only enforcement

```bash
pnpm add -D @commitlint/cli @commitlint/config-conventional
```

```javascript
// commitlint.config.mjs
export default {
  extends: ["@commitlint/config-conventional"],
  rules: {
    // Enforce scopes to match Worker package names
    "scope-enum": [
      2,
      "always",
      ["kv-cache", "d1-query", "r2-upload", "auth", "shared", "ci", "deps"],
    ],
    // Body lines must be ≤100 chars (GitHub PR preview wraps at 72, but we allow more)
    "body-max-line-length": [1, "always", 100],
    // Require scope on feat and fix
    "scope-empty": [2, "never"],
  },
  // Ignore Renovate bot commits
  ignores: [(commit) => commit.startsWith("chore(deps)")],
};
```

```bash
# Run manually against any commit
echo "feat(kv-cache): add TTL sliding window" | pnpm commitlint

# Run in CI against the PR's commit range
pnpm commitlint --from="$(git merge-base HEAD origin/main)" --to=HEAD
```

```yaml
# .github/workflows/commitlint.yml
name: Lint commits

on:
  pull_request:
    types: [opened, synchronize]

jobs:
  commitlint:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0   # commitlint needs full range
      - uses: pnpm/action-setup@v4
      - run: pnpm install --frozen-lockfile
      - name: Lint commit messages
        run: |
          pnpm commitlint \
            --from "$(git merge-base HEAD origin/main)" \
            --to HEAD \
            --verbose
```

## commitizen: interactive guided prompts

```bash
pnpm add -D commitizen cz-conventional-changelog
```

```json
// package.json (root)
{
  "scripts": {
    "commit": "cz"
  },
  "config": {
    "commitizen": {
      "path": "./node_modules/cz-conventional-changelog"
    }
  }
}
```

```bash
# Instead of: git commit
pnpm commit
# → Interactive prompts:
# ? Select the type of change: (Use arrow keys)
# ❯ feat     A new feature
#   fix      A bug fix
#   docs     Documentation only
# ? What is the scope of this change? (e.g. component name): kv-cache
# ? Write a short description: add sliding TTL for cache entries
# → Writes: feat(kv-cache): add sliding TTL for cache entries
```

### Monorepo scope adapter
```javascript
// .cz-config.cjs — custom scope list for cz-customizable
module.exports = {
  types: [
    { value: "feat", name: "feat:     A new feature" },
    { value: "fix", name: "fix:      A bug fix" },
    { value: "chore", name: "chore:    Build/tooling changes" },
    { value: "ci", name: "ci:       CI/CD changes" },
    { value: "perf", name: "perf:     Performance improvement" },
    { value: "refactor", name: "refactor: Code change, no feature/fix" },
    { value: "test", name: "test:     Adding missing tests" },
  ],
  scopes: [
    { name: "kv-cache" },
    { name: "d1-query" },
    { name: "r2-upload" },
    { name: "auth" },
    { name: "shared" },
    { name: "ci" },
    { name: "deps" },
  ],
  allowCustomScopes: false,
  allowBreakingChanges: ["feat", "fix"],
};
```

## czg: modern commitizen replacement
`czg` is a drop-in replacement for `commitizen` with a TUI, emoji support, and built-in AI-assist commit generation. It requires no `config.commitizen` package.json field.

```bash
pnpm add -D czg
```

```bash
# Interactive commit (TUI)
pnpm czg

# AI-assisted: generates subject from staged diff
pnpm czg ai

# Non-interactive (CI-safe): write directly
pnpm czg --type=chore --scope=deps --subject="update pnpm lockfile" --no-emoji
```

```json
// .czrc — czg configuration (JSON, not JS)
{
  "czg": {
    "scopes": ["kv-cache", "d1-query", "r2-upload", "auth", "shared", "ci", "deps"],
    "emoji": false,
    "maxSubjectLength": 72,
    "breaklineChar": "|",
    "skipQuestions": ["footer"]
  }
}
```

## Performance comparison
| Metric | commitlint (hook only) | commitizen | czg |
|---|---|---|---|
| Install size | ~12 MB | ~45 MB | ~8 MB |
| `commit-msg` hook time | ~250 ms | N/A | N/A |
| Interactive startup | N/A | ~1.8 s | ~0.4 s |
| pnpm workspace aware | via config | via adapter | native |
| AI subject generation | ❌ | ❌ | ✅ (`czg ai`) |
| Emoji support | config | via adapter | native |
| Node 22 ESM support | ✅ | ⚠️ CJS only | ✅ |

## Recommended setup for Workers monorepos
```bash
# Install
pnpm add -D @commitlint/cli @commitlint/config-conventional czg lefthook
```

```yaml
# lefthook.yml
commit-msg:
  commands:
    commitlint:
      run: pnpm commitlint --edit {1}

prepare-commit-msg:
  commands:
    czg-hook:
      # Only invoke czg when commit is not from merge/squash/rebase
      run: |
        [ "$2" != "merge" ] && [ "$2" != "squash" ] && \
          node_modules/.bin/czg hook || true
```

```typescript
// scripts/validate-recent-commits.ts
// Run in CI to surface any commits that escaped local hooks
import { execSync } from "node:child_process";

const base = execSync("git merge-base HEAD origin/main").toString().trim();
const messages = execSync(`git log --format=%s ${base}..HEAD`)
  .toString()
  .trim()
  .split("\n")
  .filter(Boolean);

const CONVENTIONAL = /^(feat|fix|chore|ci|perf|refactor|test|docs|build|revert)(\(\w[\w-]*\))!?: .{1,72}$/;

const invalid = messages.filter((m) => !CONVENTIONAL.test(m));
if (invalid.length > 0) {
  console.error("Non-conventional commit messages found:");
  invalid.forEach((m) => console.error(`  - ${m}`));
  process.exit(1);
}
console.log(`All ${messages.length} commit(s) pass conventional format.`);
```

## Anti-patterns
- Installing only commitizen without commitlint — the prompt guides but nothing validates; engineers can still bypass with `git commit -m`.
- Configuring `commitlint` with no `scope-enum` rule — this allows arbitrary scopes that break `semantic-release` scope-based changelogs.
- Running `czg ai` in CI pipelines to auto-generate commit messages for merge commits — AI generation introduces non-determinism in commit history.
- Adding `--no-verify` to `git commit` in CI scripts to bypass the `commit-msg` hook — this defeats the entire enforcement chain.
- Using commitizen with the default CJS adapter in an ESM-only monorepo without wrapping in a `.cjs` config file — Node 22 will throw `ERR_REQUIRE_ESM`.

## Gotchas
- `commitlint` requires `fetch-depth: 0` in GitHub Actions when validating a PR range with `--from`/`--to` — the merge-base commit is beyond a shallow boundary with depth 1.
- `czg hook` must be invoked from the `prepare-commit-msg` hook, not `commit-msg` — the TUI needs to write to the commit message file before Git reads it.
- `lefthook` runs hooks in parallel by default; commitlint in `commit-msg` should be marked `run_directly: true` to avoid timing issues with czg's message file write.
- `cz-conventional-changelog` and `czg` write different footers for breaking changes; commitlint treats `BREAKING CHANGE:` (with space) and `BREAKING-CHANGE:` (with hyphen) identically per the spec, but some release tools do not.
- The `ignores` function in `commitlint.config.mjs` must return `true` to skip — returning a truthy non-boolean silently fails the ignore and commitlint still validates.

## Verification
```bash
# Test commitlint against a good and bad message
echo "feat(kv-cache): add sliding TTL" | pnpm commitlint  # exit 0
echo "WIP stuff" | pnpm commitlint                         # exit 1

# Confirm czg writes a valid message
git add .
pnpm czg --type=fix --scope=auth --subject="correct token expiry check" --no-emoji
git log -1 --format=%s
# → fix(auth): correct token expiry check

# Run the CI validation script locally
pnpm tsx scripts/validate-recent-commits.ts
```

## Related
- [conventional-commits-2026.md](conventional-commits-2026.md)
- [conventional-commits-automated-changelog.md](conventional-commits-automated-changelog.md)
- [git-hooks-husky-lint-staged-commitlint.md](git-hooks-husky-lint-staged-commitlint.md)
- [git-hooks-lefthook-monorepo.md](git-hooks-lefthook-monorepo.md)
- [semantic-release-automation.md](semantic-release-automation.md)

## Sources
- https://commitlint.js.org/
- https://github.com/commitizen/cz-cli
- https://github.com/Zhengqbbb/cz-git (czg)
