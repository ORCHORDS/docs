# Go fuzzing corpus and regression promotion

**Issue:** Parsers and boundary-heavy Go code can contain input bugs missed by examples, while unbounded fuzzing creates nondeterministic CI duration.

**Date:** 2026-08-17
**Author:** ORCHORDS
**Status:** documented

## Guidance

Go's native coverage-guided fuzzing mutates seed inputs and minimizes failures. Keep fuzz targets fast, deterministic, isolated, and free of state that survives an invocation. Commit valuable minimized failures under the test corpus so ordinary `go test` preserves them as regressions.

## Controls and verification

- Pin Go and set explicit fuzz time and parallelism.
- Never fuzz destructive production endpoints.
- Bound input-derived allocation and time.
- Reproduce every failure with the saved corpus entry.
- Separate long fuzz campaigns from required deterministic unit tests.
- Sanitize artifacts before sharing sensitive inputs.

## Sources

- [Go: Fuzzing](https://go.dev/doc/security/fuzz/)
- [Go: Fuzzing tutorial](https://go.dev/doc/tutorial/fuzz)
