# JUnit temporary-directory factory isolation

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Problem

JUnit's default `@TempDir` location is convenient, but suites needing a dedicated filesystem, quota boundary, or runner-owned parent should not rewrite global JVM temporary-directory state. A custom `TempDirFactory` chooses where test data is created and receives a lifecycle callback; unsafe implementations can cross test boundaries, follow hostile paths, or conceal failures.

## When to use

Use a custom factory only for a documented requirement such as exercising a particular filesystem or keeping data inside a per-job volume. Keep the standard factory for ordinary unit tests. This lesson governs allocation and isolation, not retention policy.

## Controls

- Keep `TempDirFactory` small, reviewed, and constructible through a public no-argument constructor.
- Take the parent only from administrator-controlled configuration. Resolve its canonical path and reject roots, shared production paths, symlink escapes, and locations outside the assigned job workspace.
- Create a new unpredictable child for every factory instance; never share a static directory across tests or workers.
- Apply least-privilege permissions and runner-enforced disk budgets.
- Preserve the primary test failure when also reporting allocation or `close()` errors.
- Prefer an annotation-local factory. If `junit.jupiter.tempdir.factory.default` is global, pin and review it as suite-wide infrastructure.
- Preserve all required tests, scanning, and cleanup checks.

## Implementation

1. Provision a unique absolute parent for the job.
2. In `createTempDirectory(AnnotatedElementContext, ExtensionContext)`, validate the parent before securely creating a child beneath it.
3. Log only a non-sensitive run identifier and allocated path.
4. Apply the factory to the smallest necessary `@TempDir` declaration.
5. Use `close()` for factory-owned resources. Do not race JUnit cleanup with another recursive deleter.
6. Let runner cleanup remove only the validated per-job parent after tests and approved artifact collection.

## Tests

- Run multiple tests and parallel workers; assert unique directories below the assigned parent.
- Try relative, root, symlinked, and out-of-workspace parents; require fail-closed behavior before writes.
- Exercise constructor, allocation, test, cleanup, and `close()` failures; retain primary and secondary diagnostics.
- Confirm local factory configuration and the global default have the intended precedence and scope.
- Test permission denial, long paths, cancellation, and every supported operating system/filesystem.
- Confirm interrupted-run cleanup cannot remove another job's files.
- Scan retained diagnostics for credentials and private data.

## Gotchas

- JUnit can instantiate factories repeatedly; static mutable state is unsafe under parallel execution.
- The API documents one creation call followed by one `close()` call per instance on the same thread; this is not a suite-wide singleton guarantee.
- A declaration-specific factory overrides the global default.
- Changing `java.io.tmpdir` affects unrelated libraries and is not an equivalent boundary.
- Windows junctions, network filesystems, containers, and macOS volumes need platform-specific canonical-path tests.
- Failed-test directories may contain secrets; publish only allowlisted artifacts with expiration.

## Official sources

- [JUnit User Guide — temporary directories](https://docs.junit.org/current/user-guide/#writing-tests-built-in-extensions-TempDirectory)
- [JUnit API — TempDir](https://docs.junit.org/current/api/org.junit.jupiter.api/org/junit/jupiter/api/io/TempDir.html)
- [JUnit API — TempDirFactory](https://docs.junit.org/current/api/org.junit.jupiter.api/org/junit/jupiter/api/io/TempDirFactory.html)
