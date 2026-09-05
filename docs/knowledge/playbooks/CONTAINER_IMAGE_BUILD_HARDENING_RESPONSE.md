---
title: "Container Image Build Hardening Playbook"
owner: "Container Platform Owner"
status: "approved"
classification: "public"
last-reviewed: "2026-09-04"
review-cycle: "90 days"
next-review: "2026-12-03"
---

# Container Image Build Hardening Playbook

## Trigger

Use this playbook when a container image is being built, modified, promoted across environments, or audited and the security baseline of the build pipeline, base image, or runtime configuration must be established or re-validated.

## Scope

Apply the process to application container images, init/sidecar images, build-time images, and supporting infrastructure-as-code that produces or distributes those images, including the build host, registry, and supply chain.

## Inputs

- image build manifest (Dockerfile, Buildpack descriptor, Cloud Native Buildpacks project.toml, or equivalent);
- base image identifier, digest, and provenance attestation;
- dependency lockfiles and SBOM inputs;
- runtime security profile and deployment manifest;
- applicable organizational security baseline (CIS Docker Benchmark, NIST SP 800-190, SLSA level).

## Steps

1. **Pin and verify the base image.** Use immutable digests rather than floating tags; verify the publisher's signature or attestation; reject images with no verifiable provenance.
2. **Minimize the image surface.** Use distroless, minimal, or scratch bases; remove shells, package managers, compilers, and unnecessary libraries from the final layer; prefer multi-stage builds that exclude build tooling from the runtime layer.
3. **Run as a non-root user.** Define a dedicated, low-privileged user and group; set `USER` to that identity; ensure filesystem permissions do not require root for startup.
4. **Declare a read-only root filesystem.** Set `readOnlyRootFilesystem: true` in the pod spec; mount writable scratch space on tmpfs or named volumes only where the application requires it.
5. **Drop unnecessary Linux capabilities.** Begin with `drop: [ALL]` and add only the capabilities the application has demonstrated it needs, justified in the image's security context documentation.
6. **Enforce resource limits.** Set CPU, memory, ephemeral storage, and process limits; prevent fork bombs and resource starvation between co-resident workloads.
7. **Inject secrets through runtime mounts, not layers.** Bind secrets from external secret managers via tmpfs volumes; never `COPY` secrets into the image and never bake credentials into environment variables at build time.
8. **Generate and publish SBOM and provenance.** Emit an SPDX or CycloneDX SBOM and a SLSA provenance attestation at build completion; verify them at admission and at deploy time.
9. **Scan continuously.** Run vulnerability, malware, secret, and license scans at build, on registry push, on a recurring schedule, and on schedule-driven rebuild; fail promotion on findings above the documented threshold.
10. **Sign and attest.** Cosign-sign the image digest; attach VEX, SBOM, and provenance attestations; configure admission controllers to require both signature and attestation before scheduling.
11. **Version and retain.** Retain prior signed image digests for rollback; do not mutate tags; record lifecycle events in the audit log.

## Escalation

Escalate to the Container Platform Owner and Application Security Lead when:
- a base image fails provenance verification;
- a critical or exploitable vulnerability is detected without a documented exception;
- runtime capabilities are required beyond the documented baseline;
- image build cannot complete SBOM or attestation generation.

## Evidence

- signed image digest and attestation identifiers;
- SBOM (SPDX or CycloneDX) artifact and integrity hash;
- vulnerability scan output with severity counts and threshold compliance;
- admission controller decision log for the promoted image;
- exception records, expiration dates, and compensating controls.

## Completion Criteria

The image is considered hardened when:
- base image digest is pinned and verified;
- all mandated hardening controls (non-root, read-only root, dropped capabilities, resource limits) are present;
- SBOM and provenance attestation are generated and verified;
- vulnerability scans meet the documented threshold;
- the image is signed and admission policy accepts it.

## Exceptions

Document any deviation from the baseline with the technical justification, scope, expiration date, and compensating controls. Review exception records at every image rebuild and at least quarterly.

## Related Documents

- [NIST SP 800-190 Application Container Security Guide](../reference/NIST_SP_800_190_APPLICATION_CONTAINER_SECURITY_GUIDE.md)
- [SLSA Build Level 3 Governance](../reference/SLSA_BUILD_LEVEL_3_GOVERNANCE.md)
- [CIS Docker Benchmark Review](../reference/CIS_DOCKER_BENCHMARK_REVIEW.md)
- [Supply Chain Levels for Software Artifacts](../reference/SUPPLY_CHAIN_LEVELS_SOFTWARE_ARTIFACTS.md)
