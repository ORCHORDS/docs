# pytest last-failed feedback with full-suite gates

**Issue:** Re-running only failed tests accelerates local diagnosis, but treating a cached subset as the required test result can hide regressions and newly collected tests.

**Date:** 2026-08-17
**Author:** ORCHORDS
**Status:** documented

## Guidance

pytest's built-in cache provider supports `--last-failed` (`--lf`) to run failures from the previous invocation and `--failed-first` (`--ff`) to run prior failures before the remaining suite. Use these modes as feedback accelerators, not replacements for the authoritative full-suite gate.

The cache is local cross-run state. Its meaning depends on the workspace, selected tests, configuration, plugins, and collection result that produced it. An absent or stale cache must never convert a required full run into a passing empty or partial run.

## Operational controls

- Use `--lf` only for an explicitly named diagnostic or developer loop.
- Keep protected-branch and release checks on a clean, complete test selection.
- Prefer `--ff` when early failure feedback is useful but complete coverage is still required.
- Do not share `.pytest_cache` across unrelated repositories, trust domains, Python environments, or incompatible revisions.
- Never cache secrets or use cached node IDs as evidence that tests still exist.
- Preserve collection errors and exit codes; do not mask them with fallback shell logic.

## Verification

1. Produce known failures, fix one, and confirm `--lf` selects the expected previous failures.
2. Add a new failing test and show that a full suite catches it even when a narrow last-failed run does not.
3. Run `--ff` and confirm all collected tests execute after previous failures.
4. Clear the cache and verify the required CI gate remains complete.
5. Record test counts so unexpected selection changes fail visibly.

## Sources

- [pytest: Re-run failures and maintain state](https://docs.pytest.org/en/stable/how-to/cache.html)
- [pytest: Exit codes](https://docs.pytest.org/en/stable/reference/exit-codes.html)
