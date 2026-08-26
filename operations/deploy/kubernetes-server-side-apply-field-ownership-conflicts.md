# Kubernetes server-side apply field-ownership conflicts

**Issue:** Multiple reconcilers can silently fight over object fields or force ownership changes that overwrite another controller's intent.

**Date:** 2026-08-17
**Author:** ORCHORDS
**Status:** documented

## Guidance

Server-Side Apply records field ownership in `managedFields` by field manager. Treat conflicts as design feedback: change ownership boundaries or coordinate managers before using force.

## Controls and verification

- Give every automation actor a stable, descriptive field-manager name.
- Inspect managed fields on conflict.
- Avoid force unless the ownership transfer is intentional and reviewed.
- Keep defaults and mutating admission in the ownership model.
- Test upgrades that change rendered fields.
- Apply concurrently in a test cluster and verify convergence without oscillation.

## Sources

- [Kubernetes: Server-Side Apply](https://kubernetes.io/docs/reference/using-api/server-side-apply/)
- [Kubernetes: Declarative management](https://kubernetes.io/docs/tasks/manage-kubernetes-objects/declarative-config/)
