# Self-hosted runner version enforcement

**Issue**

Self-hosted runners must stay compatible with Actions service changes and newer action runtimes; disabling automatic updates transfers the full rollout obligation to the operator.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Controls

- Inventory runner versions and compare them with the official actions/runner release feed.
- If `--disableupdate` is used for immutable images, rebuild and canary images on a defined cadence.
- Drain runners before replacement and keep warm compatible capacity.
- Block image promotion unless registration, a representative action matrix, and required-check reporting pass.

## Verification

1. Canary newest and oldest-supported images against checkout, cache, artifacts, containers, and required gates.
2. Simulate an outdated runner and alert before jobs stop being accepted.
3. Roll back the image without rolling back workflow security fixes.

## Gotchas

- Runner binaries and runner OS images have separate lifecycles.
- Automatic update can change startup time.
- Version pinning without an owner becomes forced downtime.

## Official sources

- [GitHub self-hosted runner reference](https://docs.github.com/en/actions/reference/runners/self-hosted-runners)
- [Official runner releases](https://github.com/actions/runner/releases)
