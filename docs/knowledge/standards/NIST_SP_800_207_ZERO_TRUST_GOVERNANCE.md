---
title: "NIST SP 800-207 Zero Trust Architecture Version Governance"
owner: "Security Architecture"
status: "active"
classification: "public"
last-reviewed: "2026-08-22"
review-cycle: "annual"
next-review: "2027-08-22"
source: "NIST SP 800-207 (Feb 2020); SP 800-207A; SP 800-63; SP 800-53 Rev. 5"
---

# NIST SP 800-207 Zero Trust Architecture Version Governance

## Purpose

NIST SP 800-207, *Zero Trust Architecture* (February 2020), defines the zero-trust model for enterprise security: every access request is authenticated, authorized, and encrypted regardless of network location. Zero trust shifts the trust boundary from the network perimeter to individual subjects, assets, and resources. SP 800-207A extends the architecture to multi-cloud environments. Profiles that govern access control or network architecture should reference SP 800-207 and SP 800-207A and bind to NIST SP 800-63 (identity), NIST SP 800-53 Rev. 5 (access-control family), and the IETF OAuth 2.1 / OpenID Connect Core 1.0 / FAPI 2.0 references.

## Current context and source status

NIST SP 800-207 was published in February 2020. SP 800-207A (multi-cloud extension) was published later. NIST SP 800-207 Rev. 2 is in development as of September 5, 2026, with proposed refinements to the logical components (policy engine, policy administrator, policy enforcement point).

## Governance pattern

1. Cite SP 800-207 (and SP 800-207A for multi-cloud) in zero-trust architecture documents and access-control policy.
2. Define the logical components: policy engine (PE), policy administrator (PA), policy enforcement point (PEP).
3. Define the access decision inputs: subject identity, asset identity, requested action, and request context.
4. Establish continuous verification: every access request is evaluated, not just the first request in a session.
5. Establish least-privilege access: subjects receive the minimum permissions required for the current task.
6. Establish micro-segmentation: network segmentation at the workload or application level, not just the network perimeter.
7. Bind to NIST SP 800-63 Rev. 3 for the identity assurance level (IAL), authenticator assurance level (AAL), and federation assurance level (FAL).
8. Bind to NIST SP 800-53 Rev. 5 access-control family for the control catalog.
9. Bind to IETF OAuth 2.1 and OpenID Connect Core 1.0 for the authentication and authorization framework.
10. Bind to FAPI 2.0 for high-risk or regulated APIs.
11. Document deviations with approver, scope, expiration, compensating controls, and review schedule.

## Zero trust core principles

- **Never trust, always verify**: every access request is authenticated and authorized.
- **Least privilege**: subjects receive the minimum permissions required.
- **Assume breach**: design as if the perimeter is already compromised.
- **Continuous verification**: trust is not persistent; trust is re-established on every access request.
- **Micro-segmentation**: network segmentation at the workload or application level.

## Logical components

- **Policy Engine (PE)**: evaluates access requests against policy; produces an allow/deny decision.
- **Policy Administrator (PA)**: orchestrates the PE decision; configures the PEP.
- **Policy Enforcement Point (PEP)**: enforces the decision at the resource boundary.

## Validation and evidence

Compliance evidence includes:

- Zero-trust architecture document that cites SP 800-207 and identifies the PE, PA, and PEP per resource type.
- Access-control policy that explicitly binds to SP 800-207.
- Identity-assurance-level assessment per SP 800-63 Rev. 3.
- Micro-segmentation topology with PEP enumeration per workload.
- Continuous-verification configuration: session TTL, re-authentication triggers, context-aware policy.
- Audit records of policy decisions and PEP actions.

Evidence that omits the logical components, the continuous-verification configuration, or the micro-segmentation topology does not establish SP 800-207 conformance.

## Companion Documents

- [NIST SP 800-207A Multi-Cloud Version Guide](../reference/NIST_SP_800_207A_MULTI_CLOUD.md)
- [NIST SP 800-53 Rev. 5 Access Control Family](../reference/NIST_SP_800_53_REV_5_ACCESS_CONTROL_FAMILY.md)
- [NIST SP 800-63 Digital Identity Governance](NIST_SP_800_63_DIGITAL_IDENTITY_GOVERNANCE.md)
- [IETF OAuth 2.1 Authorization Framework](../reference/IETF_OAUTH_2_1_AUTHORIZATION_FRAMEWORK.md)
- [OpenID Connect Core 1.0](../reference/OPENID_CONNECT_CORE_1_0.md)
- [FAPI 2.0 Security Profile](../reference/FAPI_2_0_SECURITY_PROFILE.md)
