# Docker build checks as a CI gate

**Issue:** Dockerfile build checks run during a normal build but report warnings by default, so a green image build can still ship a known configuration violation.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Controls

Pin Dockerfile syntax and a Buildx version that supports the checks required by the repository. Run `docker build --check` as a fast review gate and configure intentional failures with `# check=error=true` or the equivalent governed build argument. Treat every `skip` as a narrow, named exception with an owner, rationale, and removal condition; do not use `skip=all` as routine policy.

Keep experimental checks in a separate canary lane until their identifiers and behavior are accepted. Run the real hermetic image build as another required job: configuration checks validate Dockerfile/build options, not source compilation, tests, base-image provenance, or runtime behavior.

## Verification

Add a fixture that violates a required rule and prove the check lane exits nonzero. Test a documented skip, syntax-version upgrade, multi-stage file, generated Dockerfile, and GitHub annotation output. Verify the built image digest and smoke tests in the independent build lane.

## Gotchas

- Normal builds may only warn unless error behavior is configured.
- `--check` checks configuration without producing the deployable image.
- Newly added rules can change results after unpinned tool upgrades.

## Official sources

- [Docker build checks](https://docs.docker.com/build/checks/)
- [Docker build-check reference](https://docs.docker.com/reference/build-checks/)
