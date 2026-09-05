---
title: CNCF CKS Kubernetes Security Governance
owner: Knowledge Engineering
status: approved
classification: public
last-reviewed: 2026-09-05
review-cycle: 180 days
next-review: 2027-03-04
source: CNCF Certified Kubernetes Security Specialist (CKS) curriculum; Kubernetes SIG Security; CIS Kubernetes Benchmark v1.10 (March 2024); NSA / CISA Kubernetes Hardening Guide v1.2 (August 2022)
---

# CNCF CKS Kubernetes Security Governance

## Scope

This card governs how `orchords-docs` evaluates Kubernetes security against the CNCF CKS curriculum, the CIS Kubernetes Benchmark, and the NSA/CISA Kubernetes Hardening Guide. It is the reference input for any KB card that cites Kubernetes security.

## Why this card exists

Kubernetes security is a moving target: API deprecation, container-runtime changes, network-policy evolution. The CKS curriculum, CIS Benchmark, and NSA/CISA guide are the canonical references. A KB card that recommends Kubernetes security practices without binding to these documents produces a deployment that does not survive a Kubernetes security audit.

## Document set

- **CNCF CKS curriculum** — the body of knowledge for the CKS exam.
- **CIS Kubernetes Benchmark v1.10** (March 2024) — prescriptive hardening.
- **NSA / CISA Kubernetes Hardening Guide v1.2** (August 2022) — federal hardening guidance.

References: `https://www.cncf.io/certification/cks/`, `https://www.cisecurity.org/benchmark/kubernetes`, `https://media.defense.gov/2022/Aug/29/2003096659/-1/-1/0/CTR_KUBERNETES_HARDENING_GUIDANCE_1.2_20220829.PDF`.

## CIS Kubernetes Benchmark v1.10 — high-impact controls

| Section | Control |
|---|---|
| 1 — Control Plane | API server, controller-manager, scheduler hardening |
| 2 — Worker Nodes | kubelet hardening |
| 3 — Policies | Pod Security Standards, NetworkPolicy, RBAC |
| 4 — Managed Services | EKS / AKS / GKE specific |
| 5 — etcd | encryption-at-rest, peer authentication |

Critical controls:

- **1.2.x** — disable anonymous auth.
- **1.3.x** — enable RBAC with least privilege.
- **1.4.x** — restrict API server access via TLS.
- **2.1.x** — kubelet authentication (`--anonymous-auth=false`).
- **2.2.x** — kubelet authorization (`--authorization-mode=Webhook`).
- **3.1.x** — Pod Security Admission (`restricted` profile).
- **3.2.x** — NetworkPolicy default-deny.
- **3.3.x** — secret encryption at rest.
- **5.x** — etcd encryption.

References: `https://www.cisecurity.org/benchmark/kubernetes`.

## NSA / CISA Hardening Guide

The NSA/CISA guide recommends:

| Threat | Mitigation |
|---|---|
| Supply chain | image scanning, SBOM, signed images |
| Threat actor | RBAC, network segmentation, runtime security |
| Insider threat | audit logging, admission control |
| Misconfiguration | CIS Benchmark conformance, automated scanning |

References: `https://media.defense.gov/2022/Aug/29/2003096659/-1/-1/0/CTR_KUBERNETES_HARDENING_GUIDANCE_1.2_20220829.PDF`.

## CKS body of knowledge

| Topic | Description |
|---|---|
| 1 — Cluster Setup | 10% |
| 2 — Cluster Hardening | 15% |
| 3 — System Hardening | 15% |
| 4 — Microservices Vulnerabilities | 20% |
| 5 — Supply Chain Security | 20% |
| 6 — Runtime Security | 20% |
| 7 — Monitoring and Logging | 10% |

## Mandatory pre-flight (before adopting a new Kubernetes cluster)

1. CIS Benchmark v1.10 is current.
2. NSA/CISA guide is current.
3. RBAC is enabled.
4. Pod Security Admission is configured (`restricted` profile).
5. NetworkPolicy is configured (default-deny).
6. Secrets are encrypted at rest.
7. Image signing is configured.
8. Image scanning is wired into CI.
9. Runtime security is configured (Falco / Tetragon).
10. Audit logging is wired.

## Cross-reference

| Domain | Card |
|---|---|
| Containers | `OCI_RUNTIME_VERSION_GOVERNANCE.md` |
| Supply chain | `SLSA_VERSION_GOVERNANCE.md` |
| Zero Trust | `NIST_SP_800_207_ZERO_TRUST_GOVERNANCE.md` |
| Microservices | `NIST_SP_800_204_CMS_GOVERNANCE.md` |
| Logging | `NIST_SP_800_92_LOG_GOVERNANCE.md` |

## Self-attestation cycle

Every 180 days:

1. Walk every Kubernetes reference card.
2. Confirm CIS Benchmark conformance.
3. Confirm RBAC, PSA, NetworkPolicy, secrets, image signing are wired.
4. Update the next-review date.

## Sources

- CNCF CKS: `https://www.cncf.io/certification/cks/`
- CIS Kubernetes Benchmark: `https://www.cisecurity.org/benchmark/kubernetes`
- NSA / CISA Kubernetes Hardening Guide: `https://media.defense.gov/2022/Aug/29/2003096659/-1/-1/0/CTR_KUBERNETES_HARDENING_GUIDANCE_1.2_20220829.PDF`
- Kubernetes SIG Security: `https://github.com/kubernetes/community/tree/master/sig-security`
