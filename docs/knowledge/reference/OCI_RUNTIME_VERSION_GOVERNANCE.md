---
title: Container Runtime, Image Format and Registry Version Governance (OCI)
owner: Knowledge Engineering
status: approved
classification: public
last-reviewed: 2026-09-05
review-cycle: 180 days
next-review: 2027-03-04
source: Open Container Initiative (https://opencontainers.org/); OCI Runtime Specification v1.2; OCI Image Format Specification v1.1; OCI Distribution Specification v1.1; containerd (https://containerd.io/); CRI-O (https://cri-o.io/)
---

# Container Runtime, Image Format and Registry Version Governance (OCI)

## Scope

This card governs how `orchords-docs` evaluates container runtime, image format, and registry versions. It is the reference input for any KB card that cites containerized workloads, containerd, CRI-O, OCI images, or container registries.

## Why this card exists

OCI is the standards body that governs container runtime, image format, and registry distribution. containerd and CRI-O are the canonical container runtimes. A KB card that cites "container" or "Docker" without binding to the OCI specs and the runtime versions produces a deployment that drifts on first dependency update.

## Document set

- **OCI Runtime Specification v1.2** — container lifecycle, hooks, mounts.
- **OCI Image Format Specification v1.1** — manifest, image index, image config, image layer.
- **OCI Distribution Specification v1.1** — registry HTTP API.

References: `https://github.com/opencontainers/runtime-spec`, `https://github.com/opencontainers/image-spec`, `https://github.com/opencontainers/distribution-spec`.

## Runtime version support matrix

| Runtime | Status | Notes |
|---|---|---|
| containerd 1.7.x | stable | production-ready |
| containerd 1.8.x | stable | production-ready |
| containerd 2.0.x | emerging (2026-09) | early adopters |
| CRI-O 1.27.x | stable | production-ready |
| CRI-O 1.28.x | stable | production-ready |
| Docker (dockershim) | removed in Kubernetes 1.24 | not for new deployments |

Policy:

- containerd ≥ 1.7 is the preferred runtime.
- CRI-O ≥ 1.27 is preferred for OpenShift.
- Docker (via moby / dockerd) may be used for development but not in production.

## Image format

| Field | Description |
|---|---|
| Manifest | `application/vnd.oci.image.manifest.v1+json` |
| Image Index | `application/vnd.oci.image.index.v1+json` (multi-arch) |
| Image Config | `application/vnd.oci.image.config.v1+json` |
| Image Layer | `application/vnd.oci.image.layer.v1.tar+gzip` (or `+zstd`) |
| Manifest List | older Docker term, equivalent to Image Index |

Multi-arch images are delivered via the Image Index (or Manifest List).

## Distribution API

The OCI Distribution API defines:

- `GET /v2/` — API check.
- `GET /v2/<name>/manifests/<reference>` — fetch manifest.
- `HEAD /v2/<name>/manifests/<reference>` — check existence.
- `GET /v2/<name>/blobs/<digest>` — fetch blob.
- `HEAD /v2/<name>/blobs/<digest>` — check existence.
- `POST /v2/<name>/blobs/uploads/` — start upload.
- `PATCH /v2/<name>/blobs/uploads/<reference>` — chunked upload.
- `PUT /v2/<name>/blobs/uploads/<reference>?digest=<digest>` — finalize upload.

References: `https://github.com/opencontainers/distribution-spec/blob/main/spec.md`.

## Image signing and verification

| Tool | Standard |
|---|---|
| cosign | Sigstore / OCI artifact |
| Notation | Notary v2 |
| Docker Content Trust | Notary v1 (deprecated) |

Policy:

- Image signing is mandatory for production.
- Cosign (Sigstore) is the preferred tool.
- Public key verification is wired into the admission controller (Kyverno, OPA).

## Image scanning

| Tool | Notes |
|---|---|
| Trivy | filesystem + image scanning |
| Grype | image scanning |
| Clair | image scanning |
| Snyk | image scanning + license + dependency |
| Anchore | image scanning + policy |

Policy:

- Image scanning is wired into the CI pipeline.
- Critical / High CVEs block the build.
- SBOM is generated per image.

## SBOM

Per `NIST_CSWP_23_2024_SSB_GOVERNANCE.md`:

- SPDX or CycloneDX format.
- Generated at build time.
- Stored with the image.
- Used for vulnerability tracking.

## Mandatory pre-flight (before adopting a new container runtime / registry)

1. The runtime version is within the support matrix.
2. The image format is OCI-compliant.
3. The distribution API is versioned.
4. Image signing is configured.
5. Image scanning is wired into CI.
6. SBOM is published.

## Container registry options

| Registry | Status |
|---|---|
| Docker Hub | public; rate-limited |
| GitHub Container Registry (ghcr.io) | public + private |
| Amazon ECR | private; integrated with AWS IAM |
| Azure Container Registry | private; integrated with Entra ID |
| Google Artifact Registry | private; integrated with GCP IAM |
| Quay (Red Hat) | public + private |
| Harbor | private; self-hosted |
| Distribution (CNCF) | private; self-hosted |

## Observability

- `container_runtime_version` (gauge).
- `image_pulls_total` (counter, per image).
- `image_builds_total` (counter).
- `image_vulnerabilities_total` (counter, by severity).
- `image_signatures_total` (counter).
- `runtime_operations_total` (counter, by operation).

## Sources

- OCI Runtime Specification: `https://github.com/opencontainers/runtime-spec`
- OCI Image Format Specification: `https://github.com/opencontainers/image-spec`
- OCI Distribution Specification: `https://github.com/opencontainers/distribution-spec`
- containerd: `https://containerd.io/`
- CRI-O: `https://cri-o.io/`
- cosign: `https://github.com/sigstore/cosign`
- Notation: `https://github.com/notaryproject/notation`
