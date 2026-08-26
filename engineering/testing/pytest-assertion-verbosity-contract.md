# pytest assertion-verbosity contract

**Problem**

Changing assertion verbosity alters diagnostic detail, log volume, and possible exposure of sensitive values.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## When to use

Use when CI needs controlled assertion diffs distinct from general verbosity.

## Controls

- Set assertion verbosity explicitly in trusted CI.
- Redact secrets before assertion values.
- Keep concise default output and detailed artifacts only for failures.

## Implementation

- Configure through canonical pytest settings.
- Separate console and retained artifact policy.
- Cap collection/log size.

## Tests

- Fail scalar, sequence, mapping, long text, and secret-bearing assertions at each level.

## Gotchas

- More detail can leak data.
- Plugins may format differently.
- Verbosity does not change correctness.

## Official sources

- [Official documentation](https://docs.pytest.org/en/stable/how-to/output.html)
