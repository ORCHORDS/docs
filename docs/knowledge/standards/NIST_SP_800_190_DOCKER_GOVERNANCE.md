---
title: NIST SP 800-190 Application Container Security Guide Governance
owner: Knowledge Engineering
status: approved
classification: public
last-reviewed: 2026-09-05
review-cycle: 180 days
next-review: 2027-03-04
source: NIST SP 800-190 (September 2017) — Application Container Security Guide; https://csrc.nist.gov/publications/detail/sp/800-190/final
---

# NIST SP 800-190 Application Container Security Guide Governance

## Scope

This card governs how `orchords-docs` evaluates application container security against NIST SP 800-190. It is the reference input for any KB card that describes container security, image hardening, container runtime isolation, or orchestration security.

## Why this card exists

NIST SP 800-190 is the canonical US federal guide for application container security. It organizes container security into image, registry, orchestrator, container, and host OS layers. Without an explicit card, the KB cites container security practices that do not survive a NIST-aligned audit.

## Document set

- **NIST SP 800-190** (September 2017) — Application Container Security Guide.

References: `https://csrc.nist.gov/publications/detail/sp/800-190/final`.

## Five countermeasure categories

### 1. Image countermeasure

| Control | Description |
|---|---|
| 1.1 | Use trusted base images |
| 1.2 | Vulnerability scanning |
| 1.3 | Image integrity (cosign / Notation) |
| 1.4 | Image provenance |
| 1.5 | Minimal image footprint (distroless, scratch) |
| 1.6 | No sensitive data in image |
| 1.7 | No clear-text secrets in image |
| 1.8 | Multi-stage build (no build tools in runtime) |

### 2. Registry countermeasure

| Control | Description |
|---|---|
| 2.1 | Registry access control |
| 2.2 | Image scanning on push |
| 2.3 | Image retention policy |
| 2.4 | Replication policy |

### 3. Orchestrator countermeasure

| Control | Description |
|---|---|
| 3.1 | RBAC |
| 3.2 | Pod Security Admission |
| 3.3 | Network Policy |
| 3.4 | Secrets management |
| 3.5 | Audit logging |

### 4. Container countermeasure

| Control | Description |
|---|---|
| 4.1 | Resource limits (CPU, memory) |
| 4.2 | Read-only root filesystem |
| 4.3 | Drop capabilities |
| 4.4 | no-new-privileges |
| 4.5 | seccomp profile |
| 4.6 | AppArmor / SELinux profile |
| 4.7 | Run as non-root |
| 4.8 | Image pinning (digest, not tag) |

### 5. Host OS countermeasure

| Control | Description |
|---|---|
| 5.1 | Container runtime isolation |
| 5.2 | Kernel hardening |
| 5.3 | Host OS minimal |
| 5.4 | Host OS patching |
| 5.5 | Runtime threat detection (Falco / Tetragon) |

## Image hardening

Per SP 800-190 § 4.1:

- Use minimal base images (alpine, distroless, scratch).
- Multi-stage builds: build in one image, copy artifacts to a runtime image.
- Remove package managers and shells from runtime images.
- Run as non-root UID/GID.

## Container isolation

Per SP 800-190 § 4.4:

- Linux kernel namespaces (PID, network, mount, UTS, IPC, user).
- Linux kernel cgroups (resource limits).
- Linux capabilities (drop unnecessary capabilities).
- seccomp (filter syscalls).
- AppArmor / SELinux (mandatory access control).
- no-new-privileges flag.

## Mandatory pre-flight (before adopting a new containerized reference architecture)

1. The image is from a trusted source.
2. The image is scanned.
3. The image is signed.
4. The registry enforces access control.
5. The orchestrator enforces RBAC, PSA, NetworkPolicy.
6. The container is hardened (resource limits, read-only root, capabilities, seccomp).
7. The host OS is hardened.
8. Runtime threat detection is wired.

## Cross-reference

| Domain | Card |
|---|---|
| Container runtime | `OCI_RUNTIME_VERSION_GOVERNANCE.md` |
| Supply chain | `SLSA_VERSION_GOVERNANCE.md` |
| Kubernetes security | `CNCF_CKS_KUBERNETES_GOVERNANCE.md` |
| Zero Trust | `NIST_SP_800_207_ZERO_TRUST_GOVERNANCE.md` |
| Logging | `NIST_SP_800_92_LOG_GOVERNANCE.md` |

## Self-attestation cycle

Every 180 days:

1. Walk every container reference card.
2. Confirm the five countermeasure categories are addressed.
3. Update the next-review date.

## Sources

- NIST SP 800-190: `https://csrc.nist.gov/publications/detail/sp/800-190/final`
- CIS Docker Benchmark: `https://www.cisecurity.org/benchmark/docker`
- CIS Kubernetes Benchmark: `https://www.cisecurity.org/benchmark/kubernetes`
- Kubernetes Pod Security Standards: `https://kubernetes.io/docs/concepts/security/pod-security-standards/`
