# pytest strict marker and configuration gates

**Issue**

Misspelled markers or configuration keys can silently skip intended selection and weaken CI policy.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Controls

- Enable `--strict-markers` and `--strict-config` in the canonical CI invocation.
- Register every marker with purpose and ownership in pytest configuration.
- Keep selection expressions in version control and test that protected suites collect nonzero tests.
- Treat warnings as errors only after an explicit allowlist.

## Verification

1. Introduce a misspelled marker and unknown config key and require CI failure.
2. Run `pytest --markers` and compare registered policy markers.
3. Assert collection counts for smoke, integration, and security lanes.

## Gotchas

- Marker registration does not prove tests use the intended semantics.
- Shell quoting can change `-m` expressions.
- Zero selected tests may still exit successfully in wrappers that swallow status.

## Official source

- [Official documentation](https://docs.pytest.org/en/stable/how-to/mark.html)
