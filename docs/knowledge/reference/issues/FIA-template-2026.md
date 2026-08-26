# FRIA-template-2026

**Issue:** A public-sector deployer launches a high-risk AI system for benefits eligibility. EU AI Act Article 27 requires a Fundamental Rights Impact Assessment (FRIA) before deployment. The official template from the AI Office is not yet published. The team has 30 days to first use.
**Date:** 2026-08-10
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Symptom

EU AI Act Article 27 mandates a Fundamental Rights Impact Assessment (FRIA) for certain deployers of high-risk AI systems before first use. The official AI Office template (Article 27(5)) is required to be developed, but **as of June 2026 has not yet been published**. Its absence does not excuse the obligation. Deployers must structure the assessment around the six required elements from Article 27(1).

## Root cause

FRIA is a systematic evaluation process to identify, assess, and mitigate potential adverse impacts of high-risk AI systems on individuals' fundamental rights. It applies to:

- **Public bodies** deploying high-risk AI systems (Article 6(2) Annex III)
- **Private entities providing public services** deploying high-risk AI systems
- **Deployers of AI for credit scoring** (Annex III point 5(b))
- **Deployers of AI for life and health insurance risk assessment** (Annex III point 5(c))
- **Annex III point 2 (critical infrastructure) is excluded** from the FRIA obligation

## The 6 mandatory FRIA sections (Article 27(1))

| Section | What to document | Basis |
|---|---|---|
| 1. System description and intended purpose | Deployer's processes, intended purpose, provider, operational context | Art 27(1)(a) |
| 2. Duration and frequency of use | Start date, duration, frequency, volume, geographic scope | Art 27(1)(b) |
| 3. Categories of affected persons | Direct subjects, third parties, vulnerable groups | Art 27(1)(c) |
| 4. Specific risks to fundamental rights | Risk register: each right, harm scenario, likelihood, severity, mitigation, residual risk | Art 27(1)(d) |
| 5. Human oversight measures | Oversight roles, intervention powers, qualifications, training | Art 27(1)(e) |
| 6. Measures if risks materialise | Technical and organizational measures, complaint/redress, authority notification | Art 27(1)(f) |

The official AI Office template (when published) will likely map directly to these six sections.

## The 10-step implementation pattern

1. **Determine FRIA applicability.** Confirm the system is high-risk under Article 6 and Annex III. Confirm the deployer type (public body, private public services, or 5(b)/5(c) deployer).
2. **Gather information from the provider.** Per Articles 11-13: technical documentation (Annex IV), instructions for use, capabilities and limitations, known risks and mitigations, training dataset info.
3. **Assemble the assessment team.** Legal/compliance, DPO, technical experts, domain experts (HR, healthcare, finance), affected community representatives, risk management.
4. **Map affected individuals and rights.** Direct subjects, third parties, vulnerable groups (children, elderly, disabled, minorities, low digital literacy).
5. **Conduct the risk assessment per right.** EU Charter rights: human dignity (Art 1), non-discrimination (Art 21), privacy (Art 7-8), effective remedy (Art 47), freedom of expression, etc.
6. **Design mitigation measures.** Technical (bias testing, accuracy thresholds, logging), organizational (governance, training), procedural (human review, complaint mechanisms).
7. **Document human oversight.** Designated individuals, qualifications, intervention capabilities, escalation procedures, monitoring protocols.
8. **Establish complaint and redress.** Internal complaint mechanism, accessible to affected persons, with defined SLAs.
9. **Obtain sign-off.** Assessment lead, legal/compliance, senior management.
10. **Notify the market surveillance authority.** Per Article 27(3), submit the FRIA results to the MSA using the Article 27(5) template (when available).

## The 6 fundamental rights to assess

For each high-risk AI system, assess impact on:

1. **Human dignity (EU Charter Art 1)** — can the system reduce people to a score or profile?
2. **Non-discrimination (Art 21)** — does the system process data on protected characteristics? Has bias testing been performed?
3. **Privacy and data protection (Art 7-8)** — does the system process personal data? Is a DPIA required? Legal basis?
4. **Effective remedy (Art 47)** — can affected persons contest decisions? Is there human review? Complaint procedure?
5. **Freedom of expression and information (Art 11)** — does the system filter, moderate, or restrict content?
6. **Consumer protection (Art 38)** — is the system used in commercial contexts affecting consumer rights?

A FRIA is per-system and per-deployment-context. The same system deployed by different organizations requires separate FRIAs because the affected persons and risks differ.

## The vulnerable group assessment

Article 27(1)(c) requires identifying categories of persons likely to be affected. Vulnerable groups requiring special attention:

- Children (under 18)
- Elderly (over 65)
- Persons with disabilities (physical, cognitive, sensory)
- Socioeconomically disadvantaged groups
- Minority ethnic or religious groups
- Non-native language speakers
- Individuals with limited digital literacy
- Workers (in employment-related AI)
- Patients (in healthcare AI)
- Consumers (in credit/insurance AI)

For each vulnerable group, assess: how they are affected, special risks, additional mitigation measures.

## The 5 mitigation categories

1. **Technical measures** — bias testing, accuracy thresholds, data quality controls, explainability mechanisms, logging, audit trails
2. **Organizational measures** — governance structures, policies, training, review cycles, accountability
3. **Procedural safeguards** — right to human review, complaint mechanisms, accessible redress channels, fallback procedures
4. **Communication measures** — transparency to affected persons, accessible information
5. **Monitoring measures** — post-deployment monitoring, drift detection, incident response

## The notification and update obligation

After completing the FRIA, the deployer must:

- **Notify the market surveillance authority** of the results (Article 27(3))
- **Update the FRIA** when:
  - The AI system is significantly modified
  - New risks are identified
  - The intended use changes
  - Relevant regulations change
- **Review at minimum annually**
- **Retain for the lifetime of the AI system + 5 years** (per typical retention policy)

## The civil-society guidance

While the official AI Office template is pending, civil society has published practitioner guidance:

- **ECNL (European Center for Not-for-Profit Law)** and **Danish Institute for Human Rights** published *A Guide to Fundamental Rights Impact Assessments* (December 2025)
- The guide includes a downloadable template and five-phase methodology built directly on Article 27(1) elements
- **Microsoft Agent Governance Toolkit** has a FRIA template focused on agent systems
- **kla.digital** and **aiactblog.nl** provide practical templates until the official one ships

These are practitioner guidance, not binding. They are useful for structuring the assessment in the absence of the official template.

## Verification

The tell that FRIA practice is working:

- Every in-scope deployment has a signed FRIA, completed before first use
- The FRIA covers all 6 mandatory sections from Article 27(1)
- Vulnerable groups are explicitly identified with additional mitigations
- Human oversight is documented with named individuals and intervention powers
- The MSA has been notified (per Article 27(3))
- The FRIA is updated when the system changes; minimum annual review
- Affected persons have a documented complaint mechanism

The tell it isn't:

- A high-risk system is in production without a completed FRIA
- The FRIA is a template-fill with no analysis of the specific deployment context
- Vulnerable groups are not identified
- Human oversight is "we'll figure it out when there's an issue"
- The MSA was not notified

## Gotchas

- **The official template's absence does not excuse the obligation.** Deployers must structure the assessment around Article 27(1).
- **FRIA is per-deployment-context.** A system used by 3 different organizations requires 3 FRIAs.
- **Vulnerable groups require additional mitigation.** Standard mitigations may not protect children, elderly, or disabled persons adequately.
- **Article 27(3) notification is mandatory.** Failing to notify the MSA is itself a compliance breach.
- **The retention is lifetime + 5 years.** Not 5 years total; lifetime plus 5.
- **Updates are triggered by events, not just calendar.** A model change or a new vulnerability disclosure triggers an update.
- **The FRIA does not replace the DPIA.** GDPR Article 35 DPIA is also required when personal data is processed. The two can be combined but have different scopes and audiences.

## Related

- `compliance/eu-ai-act-code-of-practice-2026.md` — full Act
- `issues/eu-ai-act-annex-iii-2026.md` — high-risk classification
- `issues/eu-ai-act-ai-sandbox-2026.md` — pre-market testing alternative
- `issues/gdpr-article-22-automated-decisions-2026.md` — related but distinct

## Source URLs (verified 2026-08-10)

- https://artificialintelligenceact.eu/article/27/
- https://microsoft.github.io/agent-governance-toolkit/compliance/fria-template/
- https://kla.digital/blog/fria-template-eu-ai-act
- https://www.aiactblog.nl/en/templates/fria
- https://www.aiactblog.nl/en/posts/fria-template-article-27-ai-act
