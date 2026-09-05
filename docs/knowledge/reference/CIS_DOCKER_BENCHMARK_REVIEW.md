---
title: "CIS Docker Benchmark Review Reference Card"
owner: "Reference Documentation"
status: "approved"
classification: "public"
last-reviewed: "2026-09-05"
review-cycle: "180 days"
next-review: "2027-03-04"
source: "Center for Internet Security (CIS) Docker Benchmark; https://www.cisecurity.org/benchmark/docker"
---

# CIS Docker Benchmark Review Reference Card

## Scope

Reference card for the CIS Docker Benchmark, which provides prescriptive configuration recommendations for the Docker daemon, container images, container runtime, networking, and storage. Profiles that govern Docker-based container deployments should adopt the CIS Docker Benchmark recommendations, automate the verification with Docker Bench for Security or equivalent tooling, and bind to NIST SP 800-190 (Application Container Security) and the Supply Chain Levels for Software Artifacts (SLSA).

## Identifier table

| Field | Value |
| --- | --- |
| Primary source | CIS Docker Benchmark (current published version) |
| Companion artifacts | NIST SP 800-190, SLSA, CIS Kubernetes Benchmark, OWASP Top 10 |
| Source URL | https://www.cisecurity.org/benchmark/docker |

## Plan

1. Reference the CIS Docker Benchmark by current version whenever a profile governs Docker deployments.
2. Apply host-level controls: audit Docker daemon configuration, restrict the Docker socket, enforce user-namespace remapping, enable live restore.
3. Apply image-level controls: use minimal base images, pin digests, scan for vulnerabilities, enforce multi-stage builds, do not embed secrets.
4. Apply container-runtime controls: run as non-root user, drop all capabilities by default, set `--read-only` filesystem, set `--security-opt=no-new-privileges`, restrict network mode to bridge or none.
5. Apply network controls: avoid host network mode, avoid host PID namespace, restrict inter-container communication with network policies.
6. Apply storage controls: mount only required volumes, use `tmpfs` for ephemeral data, avoid mounting sensitive host directories.
7. Automate verification with Docker Bench for Security, Falco, or Trivy in CI/CD.
8. Bind to NIST SP 800-190 for the application-container-security context.
9. Bind to SLSA for the supply-chain integrity context.
10. Document deviations with approver, scope, expiration, compensating controls, and review schedule.

## Inputs

- CIS Docker Benchmark (current version).
- Docker daemon configuration inventory.
- Container image inventory and vulnerability scan results.
- CI/CD pipeline definitions.
- Risk-management framework (NIST CSF, ISO 27001) and the threat model.

## ORCHORDS Profile

ORCHORDS treats the CIS Docker Benchmark as the canonical configuration baseline for Docker deployments. Profiles that govern Docker should cite the benchmark by version, apply host-, image-, and runtime-level controls, automate verification in CI/CD, and bind to NIST SP 800-190 and SLSA.

A profile that governs Docker without binding to the CIS Docker Benchmark is non-conformant.

## Implementation Notes

- The CIS Docker Benchmark covers Docker Engine configuration; container-orchestration (Kubernetes) controls are in the CIS Kubernetes Benchmark.
- Rootless Docker mode addresses several host-level controls (for example, daemon privilege escalation) and should be evaluated.
- Image-digest pinning (for example, `image@sha256:...`) prevents tag-mutation attacks; tag-only references are non-conformant.
- `--security-opt=no-new-privileges` is a defense-in-depth control that prevents setuid binaries from gaining privileges.
- Read-only container filesystems prevent persistence for many attacker techniques; writable directories should be explicit (`tmpfs`, named volumes).

## Companion Documents

- [NIST SP 800-190 Application Container Security Guide](NIST_SP_800_190_APPLICATION_CONTAINER_SECURITY_GUIDE.md)
- [Supply Chain Levels for Software Artifacts (SLSA)](SUPPLY_CHAIN_LEVELS_SOFTWARE_ARTIFACTS.md)
- [NIST SP 800-161 C-SCRM](NIST_SP_800_161_C_SCRM.md)
- [NIST SSDF SP 800-218](NIST_SSDF_SP_800_218.md)
