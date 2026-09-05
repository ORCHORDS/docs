---
title: ISO/TS 22600:2014 Health Informatics — Privilege Management and Access Control Governance
owner: Knowledge Engineering
status: approved
classification: public
last-reviewed: 2026-09-05
review-cycle: 180 days
next-review: 2027-03-04
source: ISO/TS 22600-1:2014 (Principles and policies), ISO/TS 22600-2:2014 (Formal models), ISO/TS 22600-3:2014 (Implementation guidance); https://www.iso.org/standard/62653.html, https://www.iso.org/standard/62654.html, https://www.iso.org/standard/62655.html
---

# ISO/TS 22600:2014 Health Informatics — Privilege Management and Access Control Governance

## Scope

This card governs how `orchords-docs` evaluates health-informatics reference architectures against ISO/TS 22600:2014 — the technical specification for privilege management and access control. It is the reference input for any KB card that touches healthcare data (PHI / ePHI), clinical information systems, or healthcare interoperability standards.

## Why this card exists

ISO/TS 22600 is the bridge between the ISO/IEC 27000 series (general ISMS) and the HL7 / IHE / ISO 13606 health-informatics stack. Without a card binding to 22600, the KB recommends health-care patterns that the auditor cannot reconcile to the standard.

## Document set

- **ISO/TS 22600-1:2014** — Principles and policies (overview, concepts).
- **ISO/TS 22600-2:2014** — Formal models (RBAC, attribute-based access control).
- **ISO/TS 22600-3:2014** — Implementation guidance (data structures, certificate format, message exchange).

References: `https://www.iso.org/standard/62653.html` (Part 1), `https://www.iso.org/standard/62654.html` (Part 2), `https://www.iso.org/standard/62655.html` (Part 3).

## Core concepts

- **Role** — abstract identifier of an activity (e.g., "physician", "nurse", "patient", "admin").
- **Privilege** — atomic right to perform an action (e.g., "view record", "amend record", "sign order").
- **Permission** — the assignment of a privilege to a role.
- **Authorization** — the dynamic decision to allow a subject (in a role) to act on an object.
- **Subject** — a user or system principal.
- **Object** — a clinical resource (patient record, order, observation).
- **Policy** — a set of rules defining authorization decisions.
- **Security label** — a classification tag attached to data (e.g., "Restricted", "Confidential", "Normal").

## Privilege Management Infrastructure (PMI)

ISO/TS 22600 specifies a PMI that mirrors the PKI concept:

- **Attribute Authority (AA)** — issues privilege attributes to subjects.
- **Privilege Holder (PH)** — the subject that holds the privilege attribute.
- **Resource Manager (RM)** — enforces access decisions.
- **Policy Decision Point (PDP)** — evaluates the access policy.
- **Policy Enforcement Point (PEP)** — enforces the PDP decision.

The PMI uses X.509 attribute certificates (RFC 5755) to bind role + privilege + validity window to a subject.

## RBAC and ABAC

ISO/TS 22600 supports both:

- **RBAC (Role-Based Access Control)** — permissions are assigned to roles, roles are assigned to users. Static decision.
- **ABAC (Attribute-Based Access Control)** — decisions are based on attributes of subject, object, action, environment. Dynamic decision.

A reference architecture that handles PHI must specify which model is in scope. The KB reference card must state:

- The model (RBAC or ABAC).
- The attribute set (subject attributes, object attributes, environment attributes).
- The policy language (XACML, ALFA, Rego).
- The decision-making latency budget (synchronous ≤ 50ms, asynchronous ≤ 5s).

## Break-glass access

22600 recognizes break-glass (emergency override) access. Policy:

- Break-glass access is allowed only when the regular access path is unavailable.
- Break-glass must be logged in an immutable audit log within 5 seconds of use.
- The audit log entry must include: subject, role assumed, object accessed, justification, time.
- A post-hoc review of the break-glass event must occur within 24 hours.
- Break-glass accounts are limited to a maximum of 2 per shift and audited weekly.

## Consent and purpose-of-use

22600 references ISO 13606 and HL7 CDA for consent recording. Policy:

- Every PHI access requires a recorded purpose of use (`purpose_of_use` code from the HL7 v3 vocabulary).
- Consent records are versioned; consent withdrawal must propagate to all systems within 4 hours.
- Consent records are accessible to the data subject on request.

## Mandatory pre-flight (before adopting a new health-informatics component)

1. The component is conformant to ISO/TS 22600 (or a profile thereof).
2. The role catalog is published and reviewed.
3. The PMI hierarchy is documented (Root AA, Subordinate AAs, leaf AAs).
4. Break-glass access is governed by the policy above.
5. Consent and purpose-of-use enforcement is wired end-to-end.
6. The audit log is immutable and exportable.

## Cross-reference to other standards

| 22600 control | Maps to |
|---|---|
| Privilege Management | ISO/IEC 27001 A.9 (Access control), NIST SP 800-53 AC-3 |
| Security labels | ISO 13606-1, HL7 CDA confidentiality codes, ISO/TS 14441 |
| Attribute certificates | RFC 5755 (X.509 AC profile), IETF RFC 5280 |
| Policy decision | XACML 3.0 (OASIS), NIST SP 800-162 (ABAC) |
| Purpose of use | HL7 v3, ISO 13606-1, ISO/TS 14441 |
| Healthcare directory | IHE PIX / PDQ, HL7 FHIR PractitionerRole |

## Self-attestation cycle

Every 180 days:

1. Walk every health-informatics reference card and confirm 22600 conformance is documented.
2. Confirm the role catalog is current.
3. Confirm break-glass audit log is reviewed.
4. Update the next-review date.

## Sources

- ISO/TS 22600-1:2014: `https://www.iso.org/standard/62653.html`
- ISO/TS 22600-2:2014: `https://www.iso.org/standard/62654.html`
- ISO/TS 22600-3:2014: `https://www.iso.org/standard/62655.html`
- RFC 5755 (Attribute Certificate Profile): `https://www.rfc-editor.org/rfc/rfc5755`
- ISO 13606 (EHR communication): `https://www.iso.org/standard/67868.html`
- HL7 FHIR Consent resource: `http://hl7.org/fhir/consent.html`
