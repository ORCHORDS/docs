# git-hooks-2026

**Issue:** A team wants to enforce pre-commit linting, commit message format, pre-push tests. The team debates pre-commit framework vs simple shell scripts. The team needs the 2026 reference for Git hooks.

**Date:** 2026-08-10
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## The 9 hook types

1. **pre-commit** - before commit message written.
2. **prepare-commit-msg** - before commit message editor opens.
3. **commit-msg** - validate commit message.
4. **post-commit** - after commit completes.
5. **pre-push** - before push.
6. **pre-receive** - server-side equivalent.
7. **post-receive** - server-side.
8. **pre-rebase** - before rebase.
9. **post-merge** - after merge.

## The 3 hook managers compared

| Manager | Language | Speed | Best for |
|---|---|---|---|
| pre-commit.com | Python | Fast (parallel) | Multi-language, mature |
| Husky | Node | Moderate | JS/TS projects |
| Lefthook | Go | Fastest | Speed-critical, Go projects |
| simple-git-hooks | Node | Minimal | Minimal setup |
| pre-commit (Python) | Python | Fast | Python/data projects |

## The 5 best practices

1. **Fast hooks** (<5s). Developers skip slow hooks.
2. **Bypassable** for emergencies (`--no-verify`).
3. **CI runs the same checks** (don't rely on local hooks alone).
4. **Server-side enforcement** for compliance checks (e.g., secret scanning).
5. **Documented hook purpose** in the hook file.

## The 5 anti-patterns

1. **Network calls in pre-commit.** Slows commits to a crawl.
2. **Auto-formatting on save** (instead of pre-commit). Skippable, often skipped.
3. **No `git config core.hooksPath`** when sharing hooks. Each dev has their own.
4. **Secret scanning only on client.** Leaks slip through `--no-verify`.
5. **Hooks that reformat staged changes** (infinite re-stage loop).

## Gotchas

- Hooks are per-clone; `git init` doesn't copy them. `core.hooksPath` or symlinks needed.
- Husky 9+ dropped bash support for `.husky/_/` directory; pure Node hooks.
- Lefthook can run hooks in parallel; pre-commit.com supports parallel since 3.0.
- Some hooks (commit-msg) need access to the staged message; pre-commit provides this via stdin.

## Source URLs (verified 2026-08-10)

- https://git-scm.com/docs/githooks
- https://pre-commit.com/
- https://typicode.github.io/husky/
- https://github.com/evilmartians/lefthook
- https://github.com/toplenboren/simple-git-hooks
