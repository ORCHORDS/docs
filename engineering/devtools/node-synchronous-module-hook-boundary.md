# Node.js synchronous module-hook boundary

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Problem

Synchronous module customization hooks run inside module loading and can rewrite resolution or source for the whole process.

## When to use

Use only for tightly scoped loaders that require synchronous CommonJS and ESM interception.

## Controls

Register before application imports, allowlist URLs and formats, pin Node, avoid network I/O, and fail closed without exposing secrets.

## Implementation

Implement deterministic resolve/load hooks, preserve nextHook chaining, add recursion guards, and run in a dedicated process boundary where possible.

## Tests

Test builtin modules, CommonJS, ESM, cycles, malformed source, hook exceptions, worker threads, and unregistration.

## Gotchas

Hooks affect trusted-code loading and can undermine integrity checks; API stability depends on the pinned Node release.

## Official sources

- [Official documentation](https://nodejs.org/api/module.html#moduleregisterhooksoptions)
