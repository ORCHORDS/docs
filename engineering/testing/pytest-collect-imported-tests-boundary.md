# pytest imported-test collection boundary

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Problem

Collecting tests imported into another test module can duplicate execution or make collection depend on import side effects.

## When to use

Use when upgrading or configuring pytest collection behavior for suites that re-export test objects.

## Controls

Set collect_imported_tests explicitly, forbid import-time external effects, keep unique node IDs, and compare collected manifests.

## Implementation

Capture pytest --collect-only output before and after the setting, remove accidental re-exports, and gate the expected test manifest in CI.

## Tests

Test package and import modes, aliases, plugins, duplicate names, deselection, xdist, and clean environments.

## Gotchas

A larger collected count is not necessarily more coverage; imported objects may represent the same test.

## Official sources

- [Official documentation](https://docs.pytest.org/en/stable/reference/reference.html#confval-collect_imported_tests)
