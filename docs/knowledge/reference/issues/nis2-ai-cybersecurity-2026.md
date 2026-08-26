# nis2-ai-cybersecurity-2026

**Issue:** A team operates an AI system that processes customer data in a financial services company. The team has no incident response process. A model is hijacked via prompt injection and exfiltrates customer data. The team has 24 hours to report under NIS2.
**Date:** 2026-08-10
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Symptom

NIS 2 (Directive (EU) 2022/2555) is the EU's baseline cybersecurity framework, replacing the original NIS Directive (2016/1148). Adopted 14 December 2022, transposed into Member State law by 17 October 2024, obligations in force from 18 October 2024. NIS 2 covers essential and important entities across 18 sectors; AI workloads supporting operations in those sectors fall under Article 21 (cybersecurity risk management) and Article 23 (incident reporting).

## Root cause

NIS 2 does not regulate AI directly. It regulates cybersecurity for entities operating in critical sectors. AI is one technology category the entities use to deliver covered services. The Article 21 risk management measures and Article 23 incident reporting obligations apply to the entire ICT estate of the entity, with AI as one component.

The four-stage reporting cascade (24h early warning, 72h notification, intermediate report, final report at one month) is materially more demanding than legacy notification frameworks.

## The 10 minimum measures (Article 21(2))

NIS 2 Article 21 lists 10 minimum measures essential and important entities must implement:

1. Policies on risk analysis and information system security
2. Incident handling
3. Business continuity, including backup management, disaster recovery, and crisis management
4. Supply chain security, including security-related aspects of relationships with direct suppliers and service providers
5. Security in network and information systems acquisition, development, and maintenance, including vulnerability handling and disclosure
6. Policies and procedures to assess the effectiveness of cybersecurity risk management measures
7. Basic cyber hygiene practices and cybersecurity training
8. Policies and procedures regarding the use of cryptography and, where appropriate, encryption
9. Human resources security, access control policies, and asset management
10. Use of multi-factor authentication or continuous authentication solutions where appropriate

For AI deployments, the measures with operational weight at the request layer are the access control policies under measure (i), the multi-factor authentication requirement under measure (j), the supply chain security under measure (d), and the incident handling under measure (b).

## The 4-stage incident reporting cascade (Article 23)

A "significant incident" is one that has caused or is capable of causing severe operational disruption of the services or financial loss for the entity, OR has affected or is capable of affecting other natural or legal persons by causing considerable material or non-material damage.

The cascade:

1. **Early warning (24 hours):** Within 24 hours of becoming aware, the entity must submit an early warning to the CSIRT or competent authority. Indicates whether the incident is suspected to be caused by malicious actors and whether it could have cross-border impact.
2. **Incident notification (72 hours):** Within 72 hours, a more detailed notification updating the initial assessment, indicating severity, impact, and indicators of compromise.
3. **Intermediate report (on request):** A status update may be requested by the competent authority during the incident.
4. **Final report (one month):** Within one month of the incident notification, a final report with detailed description, type of threat, root cause, mitigation measures applied, and cross-border impact. For ongoing incidents, a progress report with the final report submitted within one month of incident handling completion.

For AI workloads, the significance threshold triggers include:

- Unauthorized disclosure of personal data through AI prompts
- AI vendor outages that disrupt covered services
- Manipulation of AI outputs producing financial harm
- Supply chain attacks reaching the AI infrastructure

## The 18 covered sectors

NIS 2 covers essential and important entities across 18 sectors: energy, transport, banking, financial market infrastructures, healthcare, drinking water, wastewater, digital infrastructure, ICT service management, public administration, space, postal and courier services, waste management, manufacture of chemicals, food production, manufacture of medical devices, manufacture of motor vehicles, and digital providers.

AI workloads supporting operations in those sectors fall under Article 21 and Article 23. A company outside these sectors does not directly fall under NIS 2, but its AI vendor (in scope) may have NIS 2 obligations that flow through the contract.

## The penalties (Article 34)

| Entity type | Maximum fine |
|---|---|
| Essential entities | €10 million or 2% of global annual turnover, whichever is higher |
| Important entities | €7 million or 1.4% of global annual turnover, whichever is higher |

For a global enterprise at €1B turnover, the fine is €20M for essential entities.

Senior management is personally accountable. Penalties apply for failure to oversee cybersecurity risk management, including failure to approve necessary measures.

## The 24/7/365 record requirement

Article 32 gives competent authorities power to conduct on-site inspections and off-site supervision. The inspection covers compliance with Article 21 and Article 23.

The records that support Article 21 access control, Article 23 reporting, and Article 32 inspection requests share a common format. Per AI request, the record contains:

- The workforce member or agent identity
- The role and access policy that authorized the request
- The data classification of the prompt
- The AI vendor and model called
- The policy version
- The decision outcome
- The timestamp

The records must be available within 24 hours of an awareness event to feed the early warning. Application logs that record the API call without the upstream context fail the inspection.

## The AI-specific incident handling runbook

For AI incidents, the runbook covers:

- **Detection:** monitoring on refusal rate drop, leak rate spike, guardrail trigger rate anomaly, tool-call volume anomaly
- **Triage:** classify as significant (cross-border impact, PII disclosure, financial harm) within the first 60 minutes
- **Containment:** disable the affected system or route around the failed component
- **Eradication:** identify the root cause (model hijack, supply chain, prompt injection)
- **Recovery:** restore from clean state, verify through independent test
- **Reporting:** 24h early warning, 72h notification, monthly final report

The 24h early warning requires initial assessment even before root cause is known. "We are investigating" is a valid early warning; the 72h notification requires more detail.

## The supply chain security obligation

Article 21(2)(d) requires supply chain security for direct suppliers. For AI workloads, this means:

- AI vendor security assessment before contract execution
- Notification clauses in AI vendor contracts for security incidents
- Right to audit the AI vendor
- SBOM (Software Bill of Materials) for AI components where possible
- Periodic re-assessment (at minimum annually)

The Cyber Resilience Act (CRA), in force 11 December 2027, provides product security evidence such as SBOMs that also supports NIS 2 supply chain requirements.

## The implementation cadence

| Phase | Activities |
|---|---|
| Month 1-2 | AI inventory aligned to covered services; Article 21 measures per AI workload |
| Month 3-4 | Access control policies; per-AI-request record format; incident handling runbooks |
| Month 5-6 | 24/7/365 monitoring; per-AI-request log retention for inspection; tabletop exercise |
| Month 7-9 | Supply chain assessments for AI vendors; contract update for notification clauses |
| Month 10-12 | First internal audit; management review; gap remediation |

For a mid-size entity in scope, the implementation takes 9-12 months. Smaller teams with focused scope can compress to 6 months.

## The international dimension

NIS 2 reporting requires cross-border impact assessment. If the incident affects entities or persons in other EU Member States, the early warning must indicate the geographic spread. The NIS Cooperation Group adopted common templates for incident reporting at its 39th Plenary (26 May 2026, Cyprus), making cross-border reporting uniform.

## The DORA interaction

For financial entities, the Digital Operational Resilience Act (DORA, Regulation (EU) 2022/2554) applies from 17 January 2025. DORA's incident management requirements are particularly stringent:

- Classification and reporting of major ICT-related incidents to competent authorities without undue delay
- Digital Operational Resilience Testing, including threat-led penetration testing (TLPT)
- ICT Third-Party Risk Management
- Information sharing

DORA and NIS 2 overlap. A team subject to both follows the stricter requirement. For most AI workloads, NIS 2 is the broader framework; DORA adds specific financial-sector requirements.

## Verification

The tell that NIS 2 AI compliance is working:

- An AI inventory is aligned to covered services, signed by the accountable executive
- Per-AI-request records are retained with the 7 fields, queryable within 24 hours
- The incident handling runbook includes AI-specific scenarios (model hijack, prompt injection breach, AI-driven misinformation, AI-enabled phishing)
- The 24/72-hour reporting cascade has been tested in a tabletop exercise
- Supply chain assessments are signed for every AI vendor
- A team member can produce the AI inventory, the access policies, the runbook, and the records on demand from a regulator

The tell it isn't:

- The team cannot name which AI workloads fall under NIS 2
- Logs record API calls but not upstream context (workforce, role, data classification)
- A tabletop exercise has never been run; the team would miss the 24h deadline
- AI vendor contracts have no notification clauses
- The CSIRT contact is unknown

## Gotchas

- **24 hours is a hard deadline, not a target.** The early warning must be submitted within 24 hours of becoming aware. "We're investigating" is acceptable; "we missed the deadline" is not.
- **Per-AI-request records are operational, not aspirational.** They must be queryable within 24 hours of an awareness event.
- **Senior management is personally accountable.** Penalties include personal liability.
- **NIS 2 does not regulate AI directly; it regulates entities.** AI is one component of the entity's ICT estate.
- **The cascade is sequential but each stage has its own deadline.** Missing the 24h early warning doesn't pause the 72h notification clock.
- **DORA and NIS 2 overlap for financial entities.** Follow the stricter requirement, not the union.
- **AI vendor contracts must include notification clauses.** Without them, the entity cannot meet its own reporting obligations.
- **Tabletop exercises are required, not optional.** Run at minimum annually; on any major AI system change.

## Related

- `issues/eu-ai-act-annex-iii-2026.md` — the EU AI Act for high-risk AI systems
- `issues/gdpr-article-22-automated-decisions-2026.md` — automated decision rights
- `lessons/prompt-injection-defense-2026.md` — defense in depth
- `lessons/ai-red-teaming-2026.md` — adversarial testing

## Source URLs (verified 2026-08-10)

- https://www.nis-2-directive.com/
- https://nisd2.eu/en/wiki/timelines-and-status/nis2-timeline
- https://www.areebi.com/compliance/nis2-directive-ai
- https://www.aigovhub.io/guides/ai-powered-cybersecurity-incident-response-nis2-dora-compliance-guide-2026
- https://www.deepinspect.ai/blog/nis2-ai-requirements
