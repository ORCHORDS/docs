# Linux memory-deny-write-execute boundary

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Problem

PR_SET_MDWE can prevent future writable-executable mappings, but enabling it late or without compatibility testing leaves gaps or breaks runtimes.

## When to use

Use for processes that do not require JIT compilation or other writable-to-executable transitions.

## Controls

Enable before untrusted code, probe kernel support, inventory executable-memory needs, and treat unsupported enforcement as a policy decision.

## Implementation

Set PR_SET_MDWE with inherited enforcement during early startup, verify status, then exec the workload under the same boundary.

## Tests

Test mmap and mprotect transitions, exec inheritance, plugins, language runtimes, crash reporting, unsupported kernels, and rollback.

## Gotchas

MDWE is irreversible for the process and does not replace seccomp, W^X-aware builds, or executable-file controls.

## Official sources

- [Official documentation](https://man7.org/linux/man-pages/man2/PR_SET_MDWE.2const.html)
