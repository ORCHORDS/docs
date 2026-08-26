# Playwright Git metadata capture policy

**Problem**

Capturing commit and diff metadata in test reports improves traceability but can expose uncommitted source or sensitive paths.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## When to use

Use for controlled CI reports bound to an exact revision.

## Controls

- Enable commit metadata separately from diff capture.
- Never capture working-tree diffs on secret-bearing or shared runners without review.
- Bind report metadata to checkout SHA and repository.

## Implementation

- Configure `captureGitInfo` in the test config.
- Redact report attachments and restrict retention.
- Keep required result independent of optional metadata collection.

## Tests

- Test detached HEAD, shallow clone, dirty tree, missing Git, and PR merge commits.

## Gotchas

- Diffs can contain secrets.
- Shallow clones limit metadata.
- Metadata does not prove artifact provenance.

## Official sources

- [Official documentation](https://playwright.dev/docs/api/class-testconfig#test-config-capture-git-info)
