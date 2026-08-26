# Git fsmonitor socket-directory policy

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Problem

Relocating the fsmonitor daemon socket can solve path limits but creates ownership, collision, and cleanup risks across repositories and users.

## When to use

Use when the default worktree administrative path cannot host the IPC endpoint on the target platform.

## Controls

Choose a user-private absolute directory, prevent cross-repository collisions, validate ownership and permissions, and retain a non-fsmonitor verification lane.

## Implementation

Set fsmonitor.socketDir in controlled config, restart the daemon, verify status and full scans, and remove stale sockets only after ownership checks.

## Tests

Test multiple worktrees, users, repository moves, stale sockets, permission denial, reboot, fallback scans, and disabling fsmonitor.

## Gotchas

The option is platform-dependent; deleting an active socket can disrupt another process.

## Official sources

- [Official documentation](https://git-scm.com/docs/git-config#Documentation/git-config.txt-fsmonitorsocketDir)
