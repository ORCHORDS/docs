# Node test reporter destination contract

**Problem**

Multiple reporters and destinations can lose, truncate, or expose results if streams and file lifecycles are not explicit.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## When to use

Use when producing both human and machine-readable Node test output.

## Controls

- Map each reporter to an explicit destination.
- Keep machine output separate from console diagnostics.
- Protect and retain result files by policy.

## Implementation

- Create destination directories securely.
- Propagate reporter/file errors.
- Flush before process exit.

## Tests

- Test pass/fail, crash, timeout, parallel tests, unwritable/full destination, and multiple reporters.

## Gotchas

- Reporter output may contain secrets.
- Forced exit can truncate streams.
- Formats evolve by Node version.

## Official sources

- [Official documentation](https://nodejs.org/api/test.html#test-reporters)
