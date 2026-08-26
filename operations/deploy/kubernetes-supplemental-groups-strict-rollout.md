# Kubernetes Strict supplemental-group rollout

**Issue:** Image /etc/group membership can silently add supplementary GIDs that grant unintended access to shared volumes.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Controls

On Kubernetes 1.35 or later, set `spec.securityContext.supplementalGroupsPolicy: Strict` where only manifest-declared `runAsGroup`, `fsGroup`, and `supplementalGroups` should apply. Inventory images and volume permissions before changing from default Merge behavior. Enforce the field with admission policy and verify node support.

## Verification

Compare `id` and `containerStatuses[].user.linux` under Merge and Strict. Test each volume, init/sidecar container, image UID, and rolling update.

## Gotchas

- Strict can remove group access an image expected.
- The status reports initial process identity.
- Privileged processes may later change identity.

## Official source

- [Kubernetes supplemental group controls](https://kubernetes.io/docs/tasks/configure-pod-container/security-context/#configure-fine-grained-supplementalgroups-control-for-a-pod)
