# Docker Compose develop-watch boundaries

**Problem**

Automatic sync/rebuild/restart can copy unintended files or conceal differences between development and production images.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## When to use

Use for local development loops, never as production deployment reconciliation.

## Controls

- Allowlist watched paths and ignore secrets/build outputs.
- Choose sync, restart, or rebuild per artifact semantics.
- Keep production build required separately.

## Implementation

- Pin Compose version.
- Run as an unprivileged container user.
- Validate target paths and ownership.

## Tests

- Test create/change/delete/rename, ignored files, symlinks, large trees, restart failure, and rebuild.

## Gotchas

- Sync is not image reproducibility.
- Host filesystem semantics differ.
- Secrets can be copied accidentally.

## Official sources

- [Official documentation](https://docs.docker.com/compose/how-tos/file-watch/)
