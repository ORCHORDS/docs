# pytest JUnit duration-report policy

**Problem**

JUnit duration can report only call time or total setup/call/teardown time, changing performance gates and dashboards.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## When to use

Use when pytest XML drives test-duration SLOs or shard balancing.

## Controls

- Set `junit_duration_report` explicitly.
- Keep raw phase timing available for diagnosis.
- Version dashboard semantics with the configuration.

## Implementation

- Configure in the canonical pytest file, not an ad hoc wrapper.
- Use total duration for capacity unless consumers require call-only.
- Preserve test correctness independently of timing.

## Tests

- Create slow setup, call, and teardown fixtures and assert XML values.
- Compare serial and worker runs.

## Gotchas

- Changing mode creates apparent regressions.
- Teardown cost can reveal leaks.
- Consumer rounding may differ.

## Official sources

- [Official documentation](https://docs.pytest.org/en/stable/reference/reference.html#confval-junit_duration_report)
