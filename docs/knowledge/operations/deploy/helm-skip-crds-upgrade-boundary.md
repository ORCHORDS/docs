# Helm CRD skip boundary

**Issue**

Skipping CRD installation changes ownership and upgrade responsibility but does not remove chart dependencies on CRD versions.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Controls

- Use `--skip-crds` only when a separate reviewed CRD lifecycle exists.
- Apply CRDs before dependent resources and verify served/storage versions.
- Keep rollback and conversion-webhook plans.

## Verification

1. Install on empty and existing clusters.
2. Upgrade across schema versions.
3. Test rollback and stored-object conversion.

## Gotchas

- Helm does not upgrade CRDs automatically in ordinary chart flow.
- Deleting CRDs deletes data.
- Schema readiness precedes controller readiness.

## Official source

- [Official documentation](https://helm.sh/docs/chart_best_practices/custom_resource_definitions/)
