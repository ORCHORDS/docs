---
title: "NIST SP 800-190 Application Container Security Guide"
owner: "Reference Documentation"
status: "approved"
classification: "public"
last-reviewed: "2026-09-05"
review-cycle: "180 days"
next-review: "2027-03-04"
source: "NIST SP 800-190 (September 2017); https://csrc.nist.gov/publications/detail/sp/800-190/final"
---

# NIST SP 800-190 Application Container Security Guide

## Scope

Reference card for NIST Special Publication 800-190, *Application Container Security Guide* (September 2017). The publication remains the canonical NIST reference for container security. Profiles that govern containerized applications should reference SP 800-190 by version and bind it to the CIS Docker Benchmark, the Kubernetes hardening guidance (CIS Kubernetes Benchmark, NSA/CISA Kubernetes Hardening Guide), NIST SSDF (SP 800-218), SLSA, and the CNCF supply-chain best practices.

## Identifier table

| Field | Value |
| --- | --- |
| Primary document | NIST SP 800-190 (September 2017) |
| Status | Final; current edition |
| Companion artifacts | CIS Docker Benchmark, CIS Kubernetes Benchmark, NSA/CISA Kubernetes Hardening Guide, NIST SSDF (SP 800-218), SLSA, CNCF supply-chain best practices |
| Source URL | https://csrc.nist.gov/publications/detail/sp/800-190/final |

## Plan

1. Reference SP 800-190 by version whenever a profile governs container security.
2. Apply the SP 800-190 image hardening controls: minimal base image, vulnerability scanning, signed images, and the registry policy.
3. Apply the SP 800-190 runtime hardening controls: runtime security, isolation, network segmentation, resource limits, and the orchestration platform hardening.
4. Apply the SP 800-190 host OS hardening controls: container-aware host OS, kernel hardening, and the daemon configuration.
5. Bind to CIS Docker Benchmark for Docker-specific hardening and to CIS Kubernetes Benchmark / NSA-CISA Kubernetes Hardening Guide for Kubernetes.
6. Bind to SLSA Build Level 3 and SLSA provenance for the build pipeline.
7. Document deviations with the approver, scope, expiration, compensating controls, and review schedule.

## Inputs

- SP 800-190 normative sections: 4 (image), 5 (registry), 6 (orchestrator), 7 (host OS), 8 (runtime).
- CIS Docker Benchmark (current published version), CIS Kubernetes Benchmark, NSA/CISA Kubernetes Hardening Guide.
- Internal image inventory, registry configuration, orchestrator configuration, and host-OS baseline.

## ORCHORDS Profile

ORCHORDS treats SP 800-190 as the canonical NIST reference for container security. Profiles that reference container security should cite the standard by version, identify the controls in scope, and bind to the CIS benchmarks, NIST SSDF, and SLSA.

A profile that references "container security" without binding to a recognized framework is non-conformant.

## Implementation Notes

- SP 800-190 covers the image, registry, orchestrator, host OS, and runtime; each layer has its own threat model.
- Minimal base images reduce the attack surface but require runtime libraries to be added explicitly.
- Image scanning should be integrated into the build pipeline, not applied after the fact.
- Runtime security (for example gVisor, Kata Containers, AppArmor) is a defense-in-depth measure, not a replacement for image hardening.
- Container-aware host OS reduces the attack surface; the daemon configuration should be hardened per the CIS Docker Benchmark.

## Companion Documents

- [NIST SSDF SP 800-218 Secure Software Development Framework](NIST_SSDF_SP_800_218.md)
- [CIS Docker Benchmark](CIS_DOCKER_BENCHMARK_REVIEW.md)
- [Supply Chain Levels for Software Artifacts (SLSA)](SUPPLY_CHAIN_LEVELS_SOFTWARE_ARTIFACTS.md)
- [SLSA Build Level 3 Governance](SLSA_BUILD_LEVEL_3_GOVERNANCE.md)
- [NIST SP 800-161 C-SCRM](NIST_SP_800_161_C_SCRM.md)
- [Container Image Build Hardening Response Playbook](../playbooks/CONTAINER_IMAGE_BUILD_HARDENING_RESPONSE.md)
