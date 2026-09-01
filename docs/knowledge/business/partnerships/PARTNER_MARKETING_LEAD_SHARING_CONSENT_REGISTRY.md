# Partner Marketing Lead-Sharing Consent Registry

## Scope

This article governs the registered record of consent and the operational signal that controls when a marketing lead may be passed from one organization to another in a partnership program. It is scoped to consent-based lead sharing, where the data subject's prior, specific, informed, and freely-given agreement is the lawful basis for the onward transfer. It is not a substitute for the lead-source organization's own privacy notice, lawful-basis record, or data-subject-rights process, and it does not address other lawful bases that may apply (contract, legitimate interest, vital interest, legal obligation, public task).

The registry sits between the consent capture on the lead-source side and the partner-side ingestion. Its purpose is to ensure that no lead is shared without a current, attributable, and verifiable consent signal; that the signal is interpreted consistently between the parties; and that withdrawal, objection, or expiry is propagated quickly enough to prevent unauthorized further use by the partner.

The design intent follows the Transparency and Consent Framework (TCF) v2 of the Interactive Advertising Bureau Europe (IAB Europe), which defines a structured consent string carried alongside advertising and marketing signals. While TCF v2 is specific to the digital advertising ecosystem, its core discipline — a machine-readable consent record bound to a transparent purpose taxonomy, a vendor list, and a defined technical surface — is reusable for partnership lead sharing wherever consent is the chosen basis.

## Workflow or implementation guidance

1. Establish a single consent taxonomy across the partnership, defining each purpose for which a lead may be shared (for example: contact about a co-branded offer, inclusion in a partner nurture program, attribution analytics, retargeting on partner channels). Each purpose must have a stated lawful basis and a stated retention limit.
2. Capture consent at the lead-source surface using a method that records who, what, when, where, why, and how. The record should include a versioned privacy notice reference, the purposes selected, the consent string (where TCF v2 is in use), the user-agent and timestamp, and a stable identifier linking back to the lead.
3. Encode consent in a registry that can be queried at lead-sharing time. The query must return a current signal — not a stale cache. The partner should not rely on lead freshness alone; it should query the registry or accept a structured consent payload with the lead.
4. When a partner is treated as a downstream recipient under the chosen lawful basis, ensure the partner is listed (where required by transparency rules), that the purposes for which the partner may use the lead are limited, and that the partner is contractually bound to honour the same purposes and the same withdrawal mechanism.
5. Propagate withdrawal, objection, and expiry from the registry to all partners and to the partner-side systems. Define a propagation SLA. A withdrawal recorded today must not still be in use tomorrow.
6. For TCF v2 contexts, ensure the consent string remains valid: respect the vendor list version, refresh consent at the interval required by local law, and treat expired or unverifiable strings as no consent.
7. Reconcile the registry against partner-side ingestion logs to detect leads received without a current consent signal. Treat the absence of a signal as a defect, not as implicit consent.
8. Subject the registry itself to access control, change management, and audit logging. The registry is a record of decisions that affect individuals; tampering with it is a serious incident.
9. Review the consent taxonomy, the partner list, and the propagation SLAs at least annually, and on any change to applicable law, to the TCF specification, or to the partnership scope.
10. Maintain documented retention and deletion procedures. When consent is withdrawn, the lead should not merely stop being shared — it should be handled in line with the data subject's request and the privacy notice.

## Controls

Controls fall into four families. Capture controls ensure consent is specific, informed, and freely given; that pre-ticked boxes, bundled consents, and conditional service access are not used. Encoding controls ensure the registry's data model, identifiers, and timestamps are consistent across parties. Propagation controls ensure withdrawal and expiry are pushed to every system that holds or uses the lead. Reconciliation controls detect drift between the registry and partner-side systems, and between the registry and the consent capture surface.

## Validation evidence

Validation evidence should include a sample of lead records traceable from the partner-side ingestion log to the registry and back to the consent capture event; a sample of withdrawal events traceable to deletion or suppression at the partner; an audit of the consent taxonomy version versus the privacy notice in force at the time of capture; reconciliation reports comparing the partner ingestion log to the registry's current consent state; and evidence of vendor-list version handling where TCF v2 is in use.

Evidence should be drawn from independent sources where possible, not only from the registry itself. A registry that reports "all leads have consent" is not assurance unless the report can be reconciled against the source-of-truth surfaces and the partner-side logs.

## Failure modes and correction

Common failure modes include consent captured for one purpose being reused for another; consent strings ignored at the boundary because the partner's ingestion system does not enforce them; partner-side suppression lists out of date with the registry; registry queries answered from caches that have not been refreshed; consent given by a minor without the verification required by applicable law; consent given on a pre-ticked surface or as a condition of unrelated service; and vendors added to the partner roster without updating the registry. A subtle but serious failure is consent captured by a sub-processor without the data controller's record-keeping, leaving the controller unable to evidence the basis on which it shared the lead.

Correction requires immediate cessation of sharing for affected leads, attribution of root cause (capture defect, propagation defect, partner-side defect, or taxonomy defect), and remediation of the underlying control. Where the failure has caused unauthorized use of personal data, the parties must assess notification duties under GDPR and other applicable rules, and may need to revise the partnership contract or terminate the lead-sharing program for the affected purpose.

## Limitations

This article covers consent-based lead sharing. It does not address legitimate-interest or other lawful bases, which require their own evidence and balancing tests. It is not legal advice and does not establish that any particular consent capture, registry design, or sharing mechanism complies with the GDPR, the ePrivacy Directive, the UK's data-protection regime, or any other jurisdiction's rules. Where TCF v2 is in use, the latest specification, vendor list, and policy version govern; consult the IAB Europe published materials.

## Canonical sources

- IAB Europe — Transparency and Consent Framework (TCF) v2: https://iabeurope.eu/tcf-for-vendors/
- GDPR — Article 7 (Conditions for consent) and Article 6 (Lawfulness of processing): https://gdpr-info.eu/art-7-gdpr/
