# Node test rerun-failures state-file contract

**Issue:** A persisted rerun state file can speed feedback but also skip tests after line moves, ordering changes, shard reuse, or untrusted state injection.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Controls

- Require Node 24.7 or later and use `--test-rerun-failures` only in a deterministic retry lane, never as the sole required suite.
- Create the state file inside the trusted job; do not restore one supplied by a pull request or a different commit.
- Namespace state by exact commit, Node version, test command, shard, platform, and relevant configuration. Delete it when test locations or order change.
- Keep the final authoritative gate as a clean full-suite run. Rerun state is an acceleration artifact, not evidence that omitted tests passed on the current revision.
- Retain the JSON only for a bounded diagnostic window and validate its schema before reuse.

## Verification

Fail then fix a test, move its line and column, reorder generated tests, change loop cardinality, split shards, corrupt the state file, and reuse it across commits. Assert only the intended failed tests rerun and the clean gate still executes every discovered test.

## Gotchas

- Test identity includes file path, line, column, and sometimes a counter.
- Nondeterministic discovery can associate a previous success with the wrong generated test.
- A state file that skips work is security-sensitive CI input.

## Official source

- [Node.js test runner: rerunning failed tests](https://nodejs.org/api/test.html#rerunning-failed-tests)
- [Node.js CLI: --test-rerun-failures](https://nodejs.org/api/cli.html#--test-rerun-failures)
