# ESLint effective-configuration inspection gate

**Problem**

Flat configuration merges, file globs, ignores, and plugin presets can produce a different effective rule set than reviewers infer from one configuration file.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## When to use

Use when migrating flat config, debugging file-specific behavior, or reviewing a security-critical lint policy.

## Controls

- Inspect representative files from every governed source class.
- Pin ESLint, plugins, parser, and configuration dependencies.
- Treat inspection output as diagnostic evidence; the normal lint run remains required.

## Implementation

- Run ESLint's supported configuration inspector in a trusted development or CI diagnostic lane.
- Record non-sensitive effective rule and ignore results for canonical fixture paths.
- Keep generated inspector output out of release artifacts unless reviewed.

## Tests

- Cover source, test, generated, ignored, nested-package, JavaScript, and TypeScript fixture paths.
- Change configuration order and assert the expected effective-policy diff.
- Verify ignored or unmatched required source roots fail through separate file-count gates.

## Gotchas

- One inspected file does not represent every glob.
- Plugins execute code while configuration loads.
- Diagnostic UI output may change across ESLint versions.
- A correct effective config does not prove lint was run on all files.

## Official sources

- [ESLint configuration inspector](https://eslint.org/docs/latest/use/configure/debug)
