# Harbor Container Registry Migration Playbook

## Purpose

Migrate an existing container registry (Docker Registry, ECR, GCR, JFrog Artifactory) to a self-hosted Harbor registry while preserving image pull URLs, signing, replication, and vulnerability scanning.

## Audience

Platform engineers, security engineers, application teams with active image pull workflows.

## Pre-conditions

- Harbor >= 2.11 deployed and reachable (see Batch 104 reference card `HARBOR_VERSION_GOVERNANCE.md`).
- Replication rules configured between the legacy registry and Harbor.
- Trivy scanner integrated into Harbor.
- Project quota and retention policies defined per team.

## Procedure

1. **Provision Harbor projects**: create one project per team, with quotas and RBAC aligned to the legacy registry.
2. **Configure replication**: set up push-based replication from the legacy registry to Harbor. Verify at least one image replicates correctly.
3. **Migrate pull secrets**: update Kubernetes `imagePullSecret` references and the cluster's `image-credential-provider` to use the Harbor registry.
4. **Mirror in-place**: re-tag and push the most-pulled 50 images to Harbor. Tag them with the same digest to avoid cache invalidation.
5. **Cut over by namespace**: per namespace, set up a temporary pull-through cache from Harbor to the legacy registry. After 7 days of clean pulls, remove the cache.
6. **Decommission legacy registry**: after 30 days of zero reads, take the legacy registry offline. Retain backups for 90 days.
7. **Document**: update `docs/operations/registry.md` with the new pull URLs and on-call contacts.

## Rollback

- Re-enable the pull-through cache from Harbor to the legacy registry. Image pulls continue from the legacy registry transparently.
- Re-issue any image pull secrets if credentials were rotated.
- Replication remains in place; new images pushed during the rollback are automatically pulled from the legacy registry.

## References

- Harbor docs — https://goharbor.io/docs/
- Internal reference card: `HARBOR_VERSION_GOVERNANCE.md`.
- Replication rules — https://goharbor.io/docs/administration/configuring-replication/
