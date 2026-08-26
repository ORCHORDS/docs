# Go test shuffle for order-dependency detection

**Issue:** Tests can pass only in declaration order because they leak global state, environment changes, files, ports, or timing assumptions.

**Date:** 2026-08-17
**Author:** ORCHORDS
**Status:** documented

## Guidance

Use Go's `go test -shuffle` mode in repeated diagnostic runs to expose order dependencies. Preserve the reported shuffle seed so a failure can be replayed. Shuffling complements race detection and isolation; it does not create safe parallelism.

## Controls and verification

- Reset global state and environment with cleanup hooks.
- Use unique temporary directories and ports.
- Record Go version, package, seed, and flags on failure.
- Keep an authoritative deterministic full-suite run.
- Do not dismiss a seed-specific failure as random.
- Run many seeds, reproduce a failure with its exact seed, fix isolation, and confirm both shuffled and normal suites pass.

## Sources

- [Go command: test flags](https://pkg.go.dev/cmd/go#hdr-Testing_flags)
- [Go testing package](https://pkg.go.dev/testing)
