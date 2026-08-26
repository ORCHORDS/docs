# ESLint empty-pattern fail-closed policy

**Issue**

Allowing lint to pass when file patterns match nothing can turn a path, checkout, or generated-source mistake into a false green check.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Controls

- Keep `--pass-on-no-patterns` disabled in required lint jobs.
- Assert expected file counts before linting generated or selected paths.
- Use the option only in explicitly optional local tooling.

## Verification

1. Rename source roots and require CI failure.
2. Test empty change selections and generated files.
3. Confirm wrapper scripts preserve ESLint exit status.

## Gotchas

- Ignored files and unmatched patterns differ.
- Shell glob expansion can alter arguments.
- A successful empty run is not validation.

## Official source

- [Official documentation](https://eslint.org/docs/latest/use/command-line-interface#--pass-on-no-patterns)
