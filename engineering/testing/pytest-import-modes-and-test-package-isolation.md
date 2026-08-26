# pytest import modes and test-package isolation

**Issue:** Test import behavior can shadow installed packages, collide on duplicate module names, or accidentally test the source tree instead of the built distribution.

**Date:** 2026-08-17
**Author:** ORCHORDS
**Status:** documented

## Guidance

pytest supports `prepend`, `append`, and `importlib` import modes with different path and test-module implications. Select a mode alongside a deliberate source layout and packaging test strategy.

## Controls and verification

- Test the built or installed artifact in at least one authoritative job.
- Avoid duplicate bare test-module names where the selected mode requires uniqueness.
- Keep imports explicit; do not mutate `sys.path` ad hoc.
- Match local and CI invocation.
- Confirm helper modules remain importable under the chosen layout.
- Run from a clean environment without the repository package already installed accidentally.

## Sources

- [pytest: Import mechanisms and sys.path](https://docs.pytest.org/en/stable/explanation/pythonpath.html)
- [pytest: Good integration practices](https://docs.pytest.org/en/stable/explanation/goodpractices.html)
