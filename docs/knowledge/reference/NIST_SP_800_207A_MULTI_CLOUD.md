---
title: "NIST SP 800-207A Zero Trust Architecture for Multi-Cloud Environments Reference Card"
standard: "NIST SP 800-207A"
publisher: "National Institute of Standards and Technology (NIST)"
category: "reference"
subcategory: "zero-trust"
canonical_url: "https://csrc.nist.gov/pubs/sp/800/207/a/final"
status: "approved"
classification: "public"
audience: "Security architects, cloud platform engineers, identity engineers"
last-reviewed: "2026-09-05"
review-cycle: "180 days"
next-review: "2027-03-04"
---

# NIST SP 800-207A Zero Trust Architecture for Multi-Cloud Environments Reference Card

## Profile

NIST SP 800-207A extends NIST SP 800-207 (Zero Trust Architecture) with guidance specific to multi-cloud deployments that span two or more cloud service providers (for example, AWS, Azure, GCP). SP 800-207A addresses the additional challenges introduced by multi-cloud: identity fragmentation across cloud-provider identity systems, inconsistent policy enforcement, network egress asymmetry, and data-residency constraints. Profiles that govern multi-cloud or hybrid-cloud deployments should cite SP 800-207A and bind to SP 800-207, SP 800-63 (identity), and SP 800-53 Rev. 5 (access control).

## Identifier

| Field | Value |
| --- | --- |
| Primary document | NIST SP 800-207A, *Zero Trust Architecture for Multi-Cloud Environments* |
| Publisher | NIST Computer Security Resource Center (CSRC) |
| Status | Published |
| Companion artifacts | NIST SP 800-207, NIST SP 800-63 Rev. 3, NIST SP 800-53 Rev. 5, NIST SP 800-204C |
| Source URL | https://csrc.nist.gov/pubs/sp/800/207/a/final |

## Current context and source status

SP 800-207A was published to address multi-cloud adoption patterns that exceeded the original SP 800-207 scope. No successor revision is published as of September 5, 2026.

## Governance pattern

1. Cite SP 800-207A in multi-cloud zero-trust architecture documents, identity-federation policies, and policy-decision-point (PDP) / policy-enforcement-point (PEP) inventories.
2. Establish a single logical identity provider or federation hub rather than relying on per-cloud identity systems.
3. Centralize policy decision points so that PEPs in each cloud consult the same authoritative policy.
4. Use standardized attribute schemas (for example, SCIM, SAML assertions, OIDC claims) across clouds.
5. Apply consistent policy enforcement across egress paths, including inter-cloud egress and on-premises egress.
6. Bind to SP 800-207 for the general zero-trust principles (subject, resource, action, context).
7. Bind to SP 800-63 Rev. 3 for the identity assurance level (IAL), authenticator assurance level (AAL), and federation assurance level (FAL).
8. Bind to SP 800-53 Rev. 5 access-control family for the control catalog.
9. Document data-residency and regulatory constraints and reflect them in the policy.
10. Document deviations with approver, scope, expiration, compensating controls, and review schedule.

## Multi-cloud specific considerations

- **Identity fragmentation**: Federate identities via OIDC or SAML to a single IdP rather than duplicating users in each cloud.
- **Policy consistency**: Use a single PDP (for example, OPA, Cedar) that PEPs in each cloud can consult.
- **Network egress**: Apply consistent egress controls across cloud-to-cloud, cloud-to-on-premises, and cloud-to-internet paths.
- **Data residency**: Encode data-residency constraints as policy attributes that the PDP evaluates on every access request.
- **Observability**: Aggregate audit logs from each cloud into a single SIEM; ensure consistent time, format, and field names.
- **Incident response**: Maintain a multi-cloud incident response runbook that addresses cross-cloud lateral movement and federated-identity compromise.

## Validation and evidence

Compliance evidence includes:

- Identity-provider architecture diagram showing federation relationships across clouds.
- Policy-decision-point inventory with PEP enumeration across clouds.
- Access-control policy that explicitly binds to SP 800-207A.
- Egress-control configuration across each cloud and inter-cloud paths.
- Audit-log aggregation topology with consistent time and format.
- Multi-cloud incident-response runbook.

Evidence that omits the federation hub, the centralized PDP, or the egress-control treatment does not establish SP 800-207A conformance.

## Companion Documents

- [NIST SP 800-207 Zero Trust Governance](../standards/NIST_SP_800_207_ZERO_TRUST_GOVERNANCE.md)
- [NIST SP 800-53 Rev. 5 Access Control Family](NIST_SP_800_53_REV_5_ACCESS_CONTROL_FAMILY.md)
- [NIST SP 800-63 Digital Identity Governance](../standards/NIST_SP_800_63_DIGITAL_IDENTITY_GOVERNANCE.md)
- [IETF OAuth 2.1 Authorization Framework](IETF_OAUTH_2_1_AUTHORIZATION_FRAMEWORK.md)
- [OpenID Connect Core 1.0](OPENID_CONNECT_CORE_1_0.md)
