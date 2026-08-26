# pytest required-plugin contract

**Problem**

A missing pytest plugin can silently remove markers, hooks, fixtures, or enforcement and still leave a partial suite running.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## When to use

Use when plugin-provided behavior is part of the required test contract.

## Controls

- Declare `required_plugins` with compatible versions.
- Pin plugin dependencies in the test environment.
- Fail before collection when the contract is unmet.

## Implementation

- Keep configuration in the canonical pytest file.
- List only correctness-critical plugins.
- Publish resolved versions.

## Tests

- Remove, downgrade, and replace plugins; verify startup failure.
- Test wrapper exit propagation.

## Gotchas

- Requiring every convenience plugin makes upgrades brittle.
- Package and plugin names can differ.
- Presence does not validate configuration.

## Official sources

- [Official documentation](https://docs.pytest.org/en/stable/reference/reference.html#confval-required_plugins)
