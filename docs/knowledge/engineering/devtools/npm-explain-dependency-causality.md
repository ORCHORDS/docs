# npm explain dependency causality

**Issue:** A package appears in `node_modules`, an audit, or a bundle, but changing the nearest `package.json` does not remove it because another dependency path still requires that installation.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Controls

Run `npm explain <package-spec>` (alias `npm why`) from the same workspace root, npm version, lockfile, configuration, and installed tree that produced the observation. Use an exact package spec or `node_modules` path when duplicate versions exist. Capture the complete root-to-package chains and classify each edge as production, development, optional, peer, workspace, alias, or nested installation before choosing an override or removal.

Pair the explanation with the lockfile diff and `npm query` when enforcing a structural invariant. `npm explain` answers why an installed node exists; it does not establish that the version is trusted, reachable in a production bundle, exploitable, or removable without compatibility testing.

## Verification

Build fixtures with hoisted duplicates, nested versions, peers, optional dependencies, aliases, and multiple workspaces. Confirm the expected causal chains before and after a lockfile-only change and a clean `npm ci`. Require an empty or changed explanation only alongside the intended manifest and lockfile diff.

## Gotchas

- Results describe the installed dependency tree and can differ from a stale or absent install.
- Workspace scope changes which roots are reported.
- An override can hide rather than solve an incompatible dependency constraint.

## Official source

- [npm explain](https://docs.npmjs.com/cli/commands/npm-explain/)
