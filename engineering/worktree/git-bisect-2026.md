# git-bisect-2026

**Issue:** Production broke between v2.1.0 and v2.2.0. The team has 200 commits between the tags. The team needs to find the regression. The team reads about `git bisect` and wants the 2026 automation.

**Date:** 2026-08-10
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## The 4 bisect modes

1. **Manual.** Mark commits good/bad interactively.
2. **Automated (`git bisect run`).** Run a test script; bisect picks the next commit automatically.
3. **Visual.** `git bisect visualize` opens gitk with the search space.
4. **External tool.** `git bisect` is scriptable from any language.

## The 5-step bisect run pattern

1. `git bisect start`
2. `git bisect bad HEAD` (current state is bad)
3. `git bisect good v2.1.0` (last known good)
4. `git bisect run ./test-script.sh`
5. `git bisect reset` when found

## The 4 best practices

1. **Test script must be fast and deterministic.** Otherwise bisect is slow or wrong.
2. **Test must be runnable in CI or local Docker** for reproducibility.
3. **Write the bad-commit SHA to a file** as soon as found, before investigating.
4. **Use `git bisect skip`** for commits that don't build or have unrelated issues.

## The 4 anti-patterns

1. **Manual bisect on a 200-commit range** without automation. Tedious, error-prone.
2. **Non-deterministic test script.** Bisect results are random.
3. **Forgetting `git bisect reset`.** Leave you on a detached HEAD.
4. **Bisecting in a dirty working tree.** Uncommitted changes confuse the process.

## Gotchas

- Bisect requires a linear history for the bad/good range; merge commits can confuse it.
- `git bisect log` records your steps; view or replay.
- `git bisect visualize` requires gitk installed.
- Bisect can be parallelized with `git bisect run --jobs N`.

## Source URLs (verified 2026-08-10)

- https://git-scm.com/docs/git-bisect
- https://www.metaltoad.com/blog/using-git-bisect-find-bugs
- https://git-scm.com/book/en/v2/Git-Tools-Debugging-with-Git
