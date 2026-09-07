# NIST SP 800-210 General Access Control Governance

## 1. Scope

This card governs ORCHORDS adoption of NIST SP 800-210 ("General Access Control Guidance for Cloud Systems") as the technical access-control baseline for cloud-resident workloads, supplementing NIST SP 800-53 Rev. 5 AC controls.

## 2. Normative references

- NIST SP 800-210 (2020).
- NIST SP 800-53 Rev. 5 — Access Control family.
- NIST SP 800-63B — Digital identity guidelines (authentication and lifecycle).
- ISO/IEC 27002:2022 §8 — Asset and access control.
- ORCHORDS Zero-Trust Reference Architecture (internal).

## 3. Access control model

1. **Subject**: human user, service account, workload identity (SPIFFE/SPIRE).
2. **Object**: data asset, resource, service endpoint.
3. **Action**: read, write, execute, delete, admin.
4. **Context**: IP range, time-of-day, device posture, geolocation, risk score.
5. **Policy**: ABAC rule combining subject, object, action, context into a decision.

## 4. Control families

| Family | Implementation | Owner |
| --- | --- | --- |
| Identification | Workforce ID + service account inventory, MFA for all humans | IAM |
| Authentication | SSO via OIDC/SAML + workload identity for services | IAM |
| Authorization | ABAC layer (e.g. Cerbos, OPA) plus IAM role assumption | App |
| Session management | Short-lived tokens (≤ 1 hour); JWT or mTLS | IAM |
| Audit logging | Every access decision logged to immutable audit store | SRE |
| Review | Quarterly access review; automated dormant-account cleanup | IAM |

## 5. Cloud-specific extensions

- Use cloud IAM as a **coarse-grained** layer; delegate fine-grained decisions to the application's policy engine.
- Mandate **just-in-time elevation** for admin operations; require approval + ticketing evidence.
- Apply **deny-by-default** for new IAM bindings; explicit allow-list for exceptions.
- Cross-account access via **Resource Access Manager (RAM)** or **AWS RAM**; never use long-lived access keys.

## 6. Special access types

| Access type | Policy |
| --- | --- |
| Privileged admin | Break-glass account, dual-control approval, time-bound ≤ 4 hours |
| Cross-cloud workload | Workload identity federation (IRSA / WIF), no static keys |
| Third-party contractor | Time-bound service account, scoped permissions, audit trail |
| Data export | Approved data-export review board; data egress monitoring on |

## 7. Audit and metrics

- Daily: review anomalous access patterns (geolocation, time, frequency).
- Weekly: reconcile active accounts vs. HR system; disable orphans within 24 hours.
- Quarterly: review privileged accounts and rotate credentials.
- Annually: third-party access-control attestation.

## 8. Review cadence

This card is reviewed every 180 days. The next scheduled review is 2027-03-06. NIST SP 800-210 revisions and major IAM platform changes trigger out-of-cycle updates.
