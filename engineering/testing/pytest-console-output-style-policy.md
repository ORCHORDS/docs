# pytest console-output style policy

**Problem**

Console output style changes CI readability and parser assumptions without changing test correctness.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## When to use

Use when standardizing human-readable progress across local and CI environments.

## Controls

- Set `console_output_style` explicitly.
- Keep machine consumers on JUnit/JSON artifacts.
- Do not parse decorative console progress for gates.

## Implementation

- Choose classic, progress, count, or times based on terminal/log behavior.
- Preserve exit code and failure sections.
- Pin pytest.

## Tests

- Test TTY/non-TTY, parallel workers, retries, failures, and very large suites.

## Gotchas

- Plugins can alter output.
- Times style adds overhead/noise.
- Console format is not a stable API.

## Official sources

- [Official documentation](https://docs.pytest.org/en/stable/reference/reference.html#confval-console_output_style)
