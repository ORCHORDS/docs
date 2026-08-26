# husky-lint-staged

**Issue:** A team pushes code with ESLint errors, broken formatting, and a typo in a TypeScript type. CI catches it 4 minutes later. The dev was already on the next file. The fix-and-retry cycle wastes a full minute per commit.
**Date:** 2026-08-10
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Symptom

Without pre-commit hooks, the only quality gate is CI. CI is slow (3-15 minutes), shared, and runs after the developer has moved on. ESLint warnings pile up; formatting drifts; type errors slip into main.

The fix is local pre-commit hooks: fast checks on staged files, run before the commit is created. The dev fixes issues at the source, not 4 minutes later in a CI red X.

## The standard stack: husky + lint-staged

Git has native hooks — `pre-commit`, `commit-msg`, `pre-push` — that are just executable scripts in `.git/hooks/`. Husky manages those hooks for a JavaScript project. lint-staged runs tools only on staged files (not the whole repo) for speed.

```bash
# Install
npm install --save-dev husky lint-staged

# Initialize husky
npx husky init
# Creates:
#   .husky/pre-commit (sample hook)
#   package.json: "prepare": "husky" (installs hooks on npm install)
```

The `prepare` script ensures hooks are installed when someone runs `npm install`. Without it, new clones have no hooks.

## The pre-commit hook

```bash
# .husky/pre-commit
npx lint-staged
```

This is the entire hook. lint-staged reads the staged files, matches them against glob patterns, and runs the configured commands only for matching files.

## The lint-staged config

```json
{
  "lint-staged": {
    "*.{ts,tsx}": [
      "eslint --fix --max-warnings 0",
      "prettier --write"
    ],
    "*.{js,mjs,cjs}": [
      "eslint --fix"
    ],
    "*.{json,yaml,yml,md}": [
      "prettier --write"
    ]
  }
}
```

The performance difference is dramatic:

- **Without lint-staged:** `eslint .` lints the entire repo. On a 50k-line project, that's 30+ seconds.
- **With lint-staged:** `eslint --fix` runs on the 2 changed files. That's 0.5 seconds.

The 60× speedup is the difference between "pre-commit is too slow, I'll skip it" and "pre-commit is invisible."

## The commit-msg hook with commitlint

Validate commit message format to keep Conventional Commits consistent:

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
    'type-enum': [2, 'always', ['feat', 'fix', 'docs', 'style', 'refactor', 'test', 'chore']],
  },
};
```

Now a `feat: add new endpoint` commit passes; `fixed the bug` fails. The team can rely on `feat:` / `fix:` to drive release automation.

## The pre-push hook

For checks too expensive or too repo-wide for pre-commit:

```bash
# .husky/pre-push
npm run type-check
npm test
```

The trade-off: pre-push runs the full type-check or test suite. On a 50k-line project, that's 30-60 seconds. Use pre-push for checks that must run on every push but are too slow for pre-commit:

- Full type-check (not just on staged files)
- Integration tests
- A smoke build

## The monorepo pattern

In a monorepo, run the hook from the root, but use per-package lint-staged configs:

```json
// package.json (root)
"scripts": {
  "prepare": "husky"
}
```

```bash
# .husky/pre-commit
pnpm exec lint-staged
```

```javascript
// .lintstagedrc.mjs (root)
export default {
  '*.md': 'prettier --write',
};
```

```javascript
// packages/frontend/lint-staged.config.mjs
import base from '../../.lintstagedrc.mjs';
export default {
  ...base,
  '*.{js,jsx,ts,tsx}': ['eslint --fix', 'prettier --write'],
};
```

lint-staged always uses the configuration file closest to the staged file. A root config does not fill in missing globs for a closer package config.

For complex monorepos with build orchestration (Nx, Turborepo):

```javascript
// lint-staged.config.js (monorepo root)
module.exports = {
  '{apps,libs,tools}/**/*.{ts,tsx}': (files) =>
    `nx affected --target=typecheck --files=${files.join(',')}`,
  '{apps,libs,tools}/**/*.{ts,tsx}': (files) =>
    `nx affected:lint --files=${files.join(',')}`,
  '{apps,libs,tools}/**/*.{ts,tsx,js,jsx,json,md}': (files) =>
    `nx format:write --files=${files.join(',')}`,
};
```

The `--concurrent false` flag on lint-staged is important here: it prevents concurrent writes from clobbering each other.

## The lefthook alternative

For large monorepos where sequential husky hooks are too slow, lefthook is a Go-based alternative that runs in parallel:

```yaml
# lefthook.yml
pre-commit:
  parallel: true
  commands:
    eslint:
      glob: "*.{ts,tsx,js}"
      run: npx eslint --fix {staged_files}
      stage_fixed: true
    prettier:
      glob: "*.{ts,tsx,js,json,css,md}"
      run: npx prettier --write {staged_files}
      stage_fixed: true
    typecheck:
      run: npx tsc --noEmit --skipLibCheck
```

`parallel: true` is the killer feature. Where husky runs each task sequentially, lefthook runs them all in parallel. On a large repo, this halves the pre-commit time.

`stage_fixed: true` re-stages files after auto-fix, so the commit captures the formatted version.

## The skip-with-caution pattern

For genuine emergencies, the hooks can be bypassed:

```bash
git commit --no-verify -m "emergency fix"
```

`--no-verify` skips both pre-commit and commit-msg. The convention: use it rarely, document the reason in the commit message, and create a follow-up issue to address the bypass.

For partial bypass with lefthook:

```bash
LEFTHOOK_EXCLUDE=typecheck git commit -m "wip"
```

Skips only the typecheck command. Other hooks still run.

## The keep-it-light discipline

Pre-commit hooks must be fast. The threshold is 5 seconds; above that, developers start bypassing with `--no-verify`. Below 1 second is invisible.

Rules:

- Run lint and format on staged files only (lint-staged does this)
- Run type-check on pre-push, not pre-commit (full project type-check is too slow)
- Run unit tests on pre-push or in CI, not pre-commit
- Run integration tests in CI, not as a hook
- The pre-commit hook is the safety net for fast, dirty fixes; CI is the safety net for everything else

## Verification

The tell that husky + lint-staged is working:

- A new engineer runs `npm install`, then makes a commit with bad formatting; the commit is rejected; the fix is applied automatically; the commit succeeds
- Pre-commit runs in under 5 seconds (lint-staged on staged files only)
- The team never pushes a commit with ESLint errors (unless `--no-verify` is used, which is rare and documented)
- Conventional commit format is enforced; `git log` is parseable by release-please

The tell it isn't:

- Pre-commit takes 30+ seconds; developers use `--no-verify` routinely
- ESLint warnings pile up despite the hook (auto-fix isn't enabled)
- Commit messages are inconsistent; release-please can't derive versions
- The hooks are not in the repo (missing `.husky/` directory)

## Gotchas

- **The `prepare` script is required.** Without it, new clones have no hooks and the team gradually loses enforcement.
- **lint-staged must run on staged files, not the whole repo.** Without lint-staged, eslint runs on 50k lines; developers skip.
- **Type-check is for pre-push, not pre-commit.** Pre-commit type-check on the full project is too slow.
- **`--concurrent false` is required for monorepos with auto-fix.** Without it, concurrent writes can clobber each other.
- **`--no-verify` should be rare and documented.** If it's routine, the hooks are too slow.
- **Hooks are not pushed to remote.** A new clone has no hooks until `npm install` runs the `prepare` script.

## Related

- `worktree/git-rerere.md` — replaying conflict resolutions
- `worktree/git-bisect-automation.md` — finding regression commits
- `worktree/release-please-semantic-release.md` — the consumer of clean commit messages

## Source URLs (verified 2026-08-10)

- https://www.pkgpulse.com/guides/husky-vs-lefthook-vs-lint-staged-git-hooks-nodejs-2026
- https://stevekinney.com/courses/enterprise-ui/husky-and-lint-staged
- https://www.thisdot.co/blog/linting-formatting-and-type-checking-commits-in-an-nx-monorepo-with-husky
- https://medium.com/@syedzainullahqazi/setting-up-husky-to-run-lint-and-typecheck-on-entire-monorepo-5ce0c5a37556
- https://syskool.com/setting-up-pre-commit-hooks-husky-lint-staged-for-typescript-monorepos/
