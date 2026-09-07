# CIS Kubernetes Benchmark v1.9 Governance

## 1. Scope

This card governs ORCHORDS adoption of the Center for Internet Security (CIS) Kubernetes Benchmark v1.9 (covering Kubernetes ≥ 1.28 and ≤ 1.31) as the technical baseline for cluster hardening across all managed Kubernetes distributions. It applies to EKS, GKE, AKS, on-prem kubeadm clusters, and Rancher/RKE2 clusters operated by ORCHORDS.

## 2. Normative references

- CIS Kubernetes Benchmark v1.9.0 (2025-04 release).
- CIS Distribution Independent Linux Benchmark v2.0 for control-plane host OS.
- NIST SP 800-190 (Container Security Guide).
- Kubernetes Pod Security Standards (PSS) — `restricted` profile as default.

## 3. Section coverage and ownership

| CIS section | Recommendation count | Owner | Acceptance gate |
| --- | --- | --- | --- |
| 1 — Control Plane Components | 32 | Platform Eng | kube-bench score ≥ 95 %, blockers = 0 |
| 2 — Worker Nodes | 15 | Platform Eng | kube-bench score ≥ 95 %, blockers = 0 |
| 3 — Policies | 7 | Security Eng | Kyverno/OPA bundles applied, drift alert on |
| 4 — Managed Services (EKS/GKE/AKS) | 18 (cumulative) | Cloud Platform | Cloud-specific checks automated via Prowler/Steampipe |
| 5 — RBAC & ServiceAccounts | 6 | IAM | Quarterly access review |
| 6 — Pod Security | 9 | Platform Eng | PSS restricted profile default; warnings on baseline |
| 7 — Network Policies | 5 | NetEng | Default-deny on every namespace |
| 8 — Secrets Management | 4 | Security Eng | etcd encryption enabled; KMS-rotated keys |
| 9 — Logging | 4 | SRE | Control-plane audit logs shipped to SIEM |
| All | 102 (approx) | — | Drift alert SLO 99 % pass-rate over 7 days |

## 4. Scanning and evidence

- Run **kube-bench** ≥ 0.10 against every cluster on a daily cron; submit JSON output to the compliance evidence store.
- Run **Trivy** (operator) against cluster manifests in CI; gate on `CRITICAL` findings.
- Run **Kubescape** for CIS + NSA-CISA hardening as a secondary signal.

## 5. Drift handling

- A nightly job compares the running cluster configuration to the codified cluster definition in the platform repo; deviations open a P3 ticket automatically.
- P0/P1 CIS findings (blockers in §3) page on-call within 15 minutes.

## 6. Exceptions

- Document exceptions in `policies/exceptions/cis-k8s/<control-id>.md` with compensating controls.
- Approve exceptions at the **Security Council** level only; review quarterly.

## 7. Adoption cadence

- New clusters ship with the v1.9 baseline from day one; no opt-out.
- Existing clusters have a 90-day remediation window from this card's effective date.

## 8. Review cadence

This card is reviewed every 180 days. The next scheduled review is 2027-03-06. CIS releases a new Kubernetes Benchmark roughly every 9-12 months; the card is updated within 30 days of an upstream minor bump.
