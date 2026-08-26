# EU Cybersecurity Reserve provider evidence

**Issue:** The EU Cybersecurity Reserve is a coordinated pool of incident-response and initial-recovery services from selected trusted managed security service providers. A private affected entity cannot assume it can invoke the Reserve directly, and an incident team cannot wait for a crisis to establish evidence-handling and authority boundaries.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Applicability and controls

- Identify the legally eligible requester: Member State cyber-crisis authority or CSIRT, CERT-EU, or an eligible competent authority of a Digital Europe Programme-associated third country.
- Determine whether the affected entity and incident fall within the current Regulation, national process, and request-prioritization rules before representing support as available.
- For a prospective trusted provider, map procurement criteria, selected service scope, geographic and language capacity, qualified personnel, integrity, secure handling, subcontractors, and deployment time to evidence.
- Pre-negotiate an incident authority matrix covering access, containment, evidence acquisition, privileged actions, data location, confidentiality, liability, return or deletion, and handback.
- Keep service credentials short-lived and least-privileged; log provider actions independently of the provider’s own systems.
- Preserve chain of custody, decision records, deliverables, results, and lessons needed for the applicable reporting and oversight process.
- Maintain an internal and commercial incident-response fallback because Reserve capacity and approval are not guaranteed.

## Implementation and tests

Run a tabletop in which the organization asks its competent authority for support, transfers a scoped incident package, grants emergency access, receives provider findings, and revokes access. Test unavailable capacity, a rejected request, cross-border data restrictions, an unapproved subcontractor, destructive remediation, evidence needed for litigation, and provider handoff to the internal team.

## Gotchas and legal caveat

Reserve “users” in Regulation (EU) 2025/38 are public authorities and CERT-EU categories, not every affected company. Services are limited to qualifying response and initial recovery use, and specific agreements include liability conditions. Procurement, national-security, privacy, employment, sector, and professional-secrecy rules may also apply.

Verify the current implementing process and selection documents. This article is operational readiness guidance, not legal advice or a claim of eligibility.

## Official sources

- [EUR-Lex: Regulation (EU) 2025/38](https://eur-lex.europa.eu/eli/reg/2025/38/oj/eng)
- [ENISA: EU Cybersecurity Reserve](https://www.enisa.europa.eu/topics/cyber-crisis-management/eu-cybersecurity-reserve)
