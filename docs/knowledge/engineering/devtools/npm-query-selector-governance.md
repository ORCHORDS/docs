# npm dependency-query selector governance

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Problem

npm query selectors can drive audits and automation, but broad or version-sensitive selectors can silently change their result set.

## When to use

Use to inventory dependency subsets from a pinned lockfile and npm version.

## Controls

Pin npm, store reviewed selectors, bound scope, treat output as untrusted metadata, and fail on parse errors.

## Implementation

Run npm query in a clean locked install, serialize stable identifying fields, diff against an approved baseline, and review changes with the lockfile.

## Tests

Test workspaces, aliases, peer edges, omitted dependencies, empty matches, malformed selectors, and npm upgrades.

## Gotchas

Selector syntax resembles CSS but dependency relationships and pseudo-classes have npm-specific semantics.

## Official sources

- [Official documentation](https://docs.npmjs.com/cli/commands/npm-query)
