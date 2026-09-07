---
title: Harbor Container Registry Version Governance
owner: Knowledge Engineering
status: approved
classification: public
last-reviewed: 2026-09-08
review-cycle: 180 days
next-review: 2027-03-07
source: Harbor project (goharbor/harbor); CNCF graduated; Harbor documentation at goharbor.io
---

# Harbor Container Registry Version Governance

## 1. Purpose

This card governs how `orchords-docs` evaluates Harbor across versions, storage backends, replication topology, vulnerability scanning integration, and OCI artifact support. It is the reference input for any KB card that cites container registry, image distribution, SBOM storage, or container scanning.

## 2. Scope

In scope:

- Harbor v2.11+ (apiVersion `core/v2` for OCI, registry REST API v2.0).
- Components: core, portal, jobservice, registryctl, trivy-adapter (replaced by Trivy operator in v2.6+), nginx, redis, postgresql.
- Storage backends: local filesystem, S3 (AWS, MinIO), Azure Blob, GCS, OSS.
- Replication: pull-based and push-based, with rule filters by tag and label.
- Scanning: Trivy (vulnerability), Cosign (signature), Notary v2 (attestation).
- OCI 1.1 artifacts: SBOMs, VEX, sigstore bundles, Helm charts, WASM modules.

Out of scope:

- Distribution (CNCF Distribution) — Harbor ships its own registry distribution binary.
- External notary signing (see `NOTARY_V2_VERSION_GOVERNANCE.md`).
- Image scanning engine lifecycle (see `TRIVY_VERSION_GOVERNANCE.md`).

## 3. Versioning policy

- Pin to a specific minor (e.g. `v2.11.1`) and verify the digest against the published SBOM.
- Support the current minor and the previous minor (N-1); security backports only on N-1.
- Always upgrade core, jobservice, registryctl, and portal in lockstep; never split versions across components.
- The online upgrade procedure is required; offline upgrades must use the documented air-gapped path.
- Upgrade window: ≤ 60 days after a new minor; 14 days for security releases.

## 4. Compatibility matrix

| Harbor | Released | Status | Trivy DB | Notes |
|---|---|---|---|---|
| 2.13.x | August 2026 | current | 2 | OCI 1.1 conformance; CVE allowlist in OPA |
| 2.12.x | May 2026 | N-1 | 2 | stable; replication v2 filters |
| 2.11.x | February 2026 | N-2 | 2 | legacy; no backports |
| 2.10.x | November 2025 | EoL | 2 | EoL |

References: `https://github.com/goharbor/harbor/releases`, `https://goharbor.io/docs/`.

## 5. Storage backend selection

- Production: object storage (S3 / Azure Blob / GCS / OSS) with versioning and lifecycle policies; local filesystem only for single-node air-gapped setups.
- Always enable KMS-managed encryption at rest on the storage backend; Harbor does not re-encrypt blobs beyond the storage backend.
- For multi-region replication, use cross-region object storage plus push-based replication.

## 6. Replication topology

- Pull-based for cross-cloud mirror sites; push-based for hub-and-spoke distribution.
- Always pin a replication resource to a specific destination registry namespace and a tag/label filter.
- Honor `--replication-trigger` (`manual`, `event-based`, `scheduled`); prefer `event-based` for low-latency distribution.
- Validate the destination supports the OCI artifact types (cosign signatures, SBOMs) you intend to replicate.

## 7. Scanning and policy

- Use the Trivy scanner; pin the Trivy DB refresh cadence to ≤ 24 h.
- Promote a CVE to `allowlist` only via documented risk acceptance with a CVE-expiry timestamp.
- Enable `prevent_vulnerable_images_from_running` at the project level; keep `severity` thresholds per environment (staging: HIGH; production: CRITICAL).
- Use Cosign/Notary v2 policy enforcement to reject unsigned images in production projects.

## 8. Upgrade procedure

1. Snapshot the database and the storage backend.
2. Pull the new minor and re-tag images for air-gapped sites.
3. Apply the Helm/Operator upgrade with `--dry-run --debug` to staging.
4. Run `harbor-core` migration job; observe `database migration complete`.
5. Roll to production one Harbor instance at a time; preserve prior `--database-secret` and `--storage-credentials` for one cycle.

## 9. Rollback procedure

1. Restore the database snapshot taken pre-upgrade.
2. Roll the Helm/Operator release back to the prior chart revision.
3. Confirm `kubectl get jobs` (or `docker service ps`) show prior jobservice replicas.
4. Re-validate replication: `harbor replication execution list --rule <id>`.
5. Document the rollback cause in the change ticket; re-apply any DB migrations before the next upgrade attempt.

## 10. Observability

Required metrics:

- `harbor_core_http_request_total{method,code}` (counter).
- `harbor_core_artifact_pull_total{project,repository}` (counter).
- `harbor_jobservice_task_total{job_type,status}` (counter).
- `harbor_registry_storage_bytes{project}` (gauge).

One alert:

- `HarborJobserviceBacklog` — page when `harbor_jobservice_task_total{status="pending"}` rises > 1000 sustained 10 minutes; also page on `harbor_registry_storage_bytes` growing > 1.5x baseline for 1 hour (signals stale artifact GC).

References: `https://goharbor.io/docs/main/administration/monitor/`, `https://github.com/goharbor/harbor/blob/master/README.md`.

## 11. References

- Harbor docs: `https://goharbor.io/docs/`
- Harbor repo: `https://github.com/goharbor/harbor`
- Releases: `https://github.com/goharbor/harbor/releases`
- OCI conformance: `https://github.com/opencontainers/oci-conformance`
- CNCF Harbor: `https://www.cncf.io/projects/harbor/`
