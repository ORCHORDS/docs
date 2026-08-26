# Linux Landlock scoped-signal policy

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Problem

Landlock process-scoping can restrict signals and process inspection, but incorrect domain construction can break supervision or leave sibling processes reachable.

## When to use

Use when sandboxed workloads must be prevented from signaling processes outside their Landlock domain.

## Controls

Probe ABI support, use no-new-privileges, define the smallest scoped rights, preserve a supervisor control path, and fail closed where required.

## Implementation

Create the ruleset before untrusted code, apply scoped process rights, then spawn the workload; record kernel capability without treating unsupported systems as protected.

## Tests

Test parent/child/sibling signals, PID reuse, ptrace paths, unsupported ABI, nested domains, cancellation, and supervisor shutdown.

## Gotchas

Landlock restrictions stack and cannot be relaxed; namespaces and traditional permissions still apply.

## Official sources

- [Official documentation](https://docs.kernel.org/userspace-api/landlock.html)
