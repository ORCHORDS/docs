# npm workspace command selection and if-present contract

**Issue:** A monorepo command can silently omit the root or a package, run packages in an unexpected order, or turn a missing required check into success through broad workspace flags.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Controls

- Pin npm and select targets explicitly with repeated `--workspace` values for required lanes. Use `--workspaces` only when every configured workspace is intended.
- Treat execution order as the order of workspace declarations in the root `package.json`; it is not a dependency-topological scheduler.
- Keep `--include-workspace-root` explicit. By default, workspace selection does not imply that the root package's script runs.
- Use `--if-present` only for genuinely optional scripts. It suppresses the missing-script error but does not suppress a failure from a script that exists.
- Produce a machine-readable expected workspace list and compare it with the selected set before checks, builds, or publishes begin.

## Verification

Test one workspace by name, multiple repeated selectors, a parent-directory selector, all workspaces, reordered declarations, a missing optional script, a missing mandatory script, a failing present script, and root inclusion. Assert both invocation order and exit status.

## Gotchas

- A green fan-out can mean the relevant package was never selected.
- Workspace names, paths, and parent paths are accepted selectors; ambiguous conventions increase operator error.
- Package-local execution changes working directory and environment assumptions.

## Official source

- [npm 11 workspaces](https://docs.npmjs.com/cli/v11/using-npm/workspaces/)
