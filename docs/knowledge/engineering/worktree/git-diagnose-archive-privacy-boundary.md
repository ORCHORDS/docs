# Git diagnose archive privacy boundary

**Problem**

A Git diagnostic archive helps support repository failures but can contain configuration, paths, refs, logs, and system information not suitable for public sharing.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## When to use

Use when ordinary redacted command output is insufficient for support.

## Controls

- Generate only for the affected repository on a trusted host.
- Inspect and redact before transfer.
- Use an approved encrypted support channel and short retention.

## Implementation

- Run `git diagnose` at the minimum useful mode.
- Record Git version and incident ID separately.
- Delete local and uploaded copies after resolution.

## Tests

- Generate fixtures with credentials in URLs/config, sensitive ref names, worktree paths, and hook output; verify redaction.

## Gotchas

- The archive is evidence, not an automatic repair.
- Higher modes collect more information.
- Removing one known token does not prove safe sharing.

## Official sources

- [Official documentation](https://git-scm.com/docs/git-diagnose)
