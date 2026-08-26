# github-actions-service-container-integration-tests

**Issue:** Integration tests pass locally but fail in GitHub Actions because service-container health checks, ports, or networking assumptions differ by job execution mode.
**Date:** 2026-08-11
**Author:** ORCHORDS
**Status:** documented

## Root cause

GitHub Actions service containers have different connection rules for runner jobs and container jobs. A service must also be healthy before tests begin; starting the test command immediately turns startup timing into a flaky failure.

**Source:** [GitHub Docs — PostgreSQL service containers](https://docs.github.com/en/actions/tutorials/use-containerized-services/create-postgresql-service-containers).

## Fix

- declare a service health check and wait for it before the test phase;
- use the mapped localhost port from a runner job;
- use the service label/port from a container job;
- provide required test configuration through scoped CI secrets or disposable values;
- isolate schema/data per run and collect service logs on failure;
- keep the service version explicit and test upgrades intentionally.

## Verification

- The test suite passes in both local containerized and CI service modes.
- A deliberately unhealthy service fails with diagnostics rather than timeout noise.
- Parallel runs do not share state.
- Connection configuration is correct for the chosen job mode.

## Related

- `testing/test-containers-docker.md`
- `github/github-actions-reusable-workflows.md`
