# ai-incident-disclosure-2026

**Issue:** An AI system at a bank is hijacked via prompt injection. Customer data is exfiltrated. The team must report the incident. To whom? In what timeframe? What format? The regulatory landscape is fragmented: NIS2, EU AI Act, GDPR, sectoral laws.
**Date:** 2026-08-10
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Symptom

An AI incident requires reporting. The team has to navigate NIS2 (24h early warning, 72h notification), EU AI Act (serious incident reporting for high-risk), GDPR (data breach 72h), and sectoral laws (DORA for financial, HIPAA-equivalent for healthcare). The timelines and formats don't align.

## Root cause

Three regulatory frameworks require AI incident reporting in the EU. Each has its own scope, timeline, and format. A team operating in scope of multiple frameworks must report to multiple authorities, with different content requirements.

## The 4 frameworks for AI incident reporting (EU)

| Framework | Scope | Timeline | Authority | Format |
|---|---|---|---|---|
| NIS2 (Directive 2022/2555) | Essential and important entities in 18 sectors | 24h early warning, 72h notification, 1-month final report | National CSIRT or competent authority | Common templates adopted 26 May 2026 |
| EU AI Act (Article 73) | Providers of high-risk AI systems | "Any serious incident" — no specific timeline in the Act, but typically 15 days | National market surveillance authority | Implementing acts specify format |
| GDPR (Article 33) | Personal data breaches involving AI systems | 72h to supervisory authority; 72h to data subjects if high risk | National DPA | Per Article 33 |
| DORA (Regulation 2022/2554) | Financial entities, ICT-related incidents | Initial notification, intermediate, final | National competent authority | ESMA RTS 7 specifics |

A team in scope of multiple frameworks must report to multiple authorities, with different content and timelines.

## The NIS2 4-stage cascade (Article 23)

A significant incident triggers:

1. **Early warning (24 hours):** Within 24 hours of becoming aware, submit early warning to CSIRT or competent authority. Indicates suspected cause, geographic spread, cross-border impact.
2. **Incident notification (72 hours):** Update with severity, impact, indicators of compromise.
3. **Intermediate report (on request):** Status update during incident handling.
4. **Final report (one month):** Detailed description, threat type, root cause, mitigations, cross-border impact.

The NIS2 Cooperation Group adopted common templates for incident reporting at its 39th Plenary (26 May 2026, Cyprus). The Commission intends to make templates binding through an implementing act.

## The EU AI Act serious incident reporting (Article 73)

Providers of high-risk AI systems must report "any serious incident" to the market surveillance authorities of the Member States where the incident occurred.

"Serious incident" is defined (Article 3(49)) as "any incident that directly or indirectly leads to, or may lead to, any of the following: (a) the death of a person or serious damage to a person's health; (b) a serious and irreversible disruption of the management or operation of critical infrastructure; (c) a breach of fundamental rights; (d) serious harm to property or the environment."

The implementing acts specify the timeline. In the absence of an implementing act, the practical deadline is "without undue delay" — typically interpreted as 15 days.

## The 5-step unified incident response

A team that is in scope of multiple frameworks needs a unified response process:

1. **Detect and classify.** Use monitoring (refusal rate, leak rate, guardrail rate, tool call volume). Classify by type: security (prompt injection, model exfiltration), safety (harmful output, bias incident), privacy (data leak), availability (system outage).
2. **Triage and assess.** Within 60 minutes: is this significant? Cross-border impact? Personal data? Critical infrastructure?
3. **Contain.** Disable the affected system, route around the failure, or activate the deterministic fallback. Do not wait for full root cause.
4. **Notify.** Per the relevant framework: NIS2 24h early warning; GDPR 72h; DORA initial; EU AI Act 15d. Multiple authorities may need parallel notifications.
5. **Document and learn.** Full report at the framework-specific deadline. Post-incident review within 2 weeks.

## The per-AI-request record format

NIS2 Article 32 inspections require the per-AI-request record:

- Workforce member or agent identity
- Role and access policy that authorized the request
- Data classification of the prompt
- AI vendor and model called
- Policy version
- Decision outcome
- Timestamp

This record must be queryable within 24 hours of an awareness event. A team that does not have this record format cannot meet the NIS2 24h early warning deadline.

## The 7 fields for AI incident reporting

For a serious AI incident, the report should include:

1. **System identification:** Name, version, provider, deployer
2. **Incident description:** What happened, when detected, when occurred
3. **AI Act classification:** Risk tier (prohibited / high-risk / limited / minimal)
4. **Affected persons:** Number, categories, vulnerable groups
5. **Harm assessment:** Severity, reversibility, cross-border impact
6. **Mitigation:** Immediate actions taken, planned remediation
7. **Root cause:** What went wrong in the AI system specifically (model, prompt, integration, etc.)

The format aligns with NIS2 and EU AI Act; specific fields for DORA or GDPR are added as required.

## The cross-framework timeline matrix

| Time | NIS2 | EU AI Act | GDPR | DORA |
|---|---|---|---|---|
| 24h | Early warning | — | — | Initial (significant ICT) |
| 72h | Notification | — | Personal data breach | — |
| 15d | — | Serious incident | — | — |
| 1 month | Final report | — | — | — |
| Per request | — | — | — | Intermediate, final |

A team must track all applicable deadlines. A single incident may trigger 4 different reports.

## The US equivalent (federal)

The US has no single AI incident reporting law. The closest is:

- **CIRCIA** (Cyber Incident Reporting for Critical Infrastructure Act, 2022) — requires CISA reports within 72 hours for covered entities; final rules pending
- **State breach notification laws** — vary by state; typically 30-60 days
- **Sectoral laws** — HIPAA (60 days), GLBA (5 days for unauthorized access), SEC (4 business days for material cyber incidents on Form 8-K)
- **Executive Order 14110** (rescinded January 2025) — required federal AI safety incident reporting; status unclear under new administration

A US team must navigate a 50-state patchwork on breach notification, plus federal sectoral laws.

## The 5-step preparedness pattern

1. **Maintain the per-AI-request record.** Continuous logging of identity, role, classification, model, outcome. Queryable within 24h.
2. **Define the incident classification.** What counts as a "significant" incident? Align with NIS2 thresholds.
3. **Pre-draft notification templates.** For NIS2 early warning, GDPR breach, DORA initial, AI Act serious incident. Fill in the blanks at notification time.
4. **Identify the authorities.** CSIRT, DPA, market surveillance, sectoral regulator. Each Member State and sector has different contacts.
5. **Tabletop exercise annually.** Test the 24h response; verify the per-AI-request record is queryable; identify gaps.

## The verification

The tell that AI incident disclosure is working:

- The per-AI-request record is queryable within 24h
- A tabletop exercise met the NIS2 24h deadline
- Notification templates are pre-drafted
- The team can name the authorities for each framework
- An incident at 14:00 results in early warning at 09:00 the next day (well within 24h)

The tell it isn't:

- "Who do we report to?" is a question the team can't answer
- The per-AI-request record is application logs, not security logs
- A tabletop exercise has never been run
- A real incident exceeded the 24h deadline

## Gotchas

- **The frameworks don't align.** Different timelines, different authorities, different content. Plan for all.
- **The 24h clock starts at "awareness."** The moment the team knows, the clock runs.
- **Personal data breach triggers GDPR + AI Act.** The 72h and 15d run in parallel; both must be met.
- **The per-AI-request record is the bottleneck.** Without it, the team cannot produce a report in 24h.
- **Cross-border impact widens notification.** A single affected person in another Member State triggers cross-border reporting.
- **NIS2 fine is 2% of turnover for important entities.** At €1B turnover, that's €20M per incident.
- **Tabletop exercises are not optional.** The 24h response cannot be figured out for the first time during a real incident.

## Related

- `issues/nis2-ai-cybersecurity-2026.md` — full NIS2 framework
- `issues/eu-ai-act-annex-iii-2026.md` — high-risk classification
- `issues/gdpr-article-22-automated-decisions-2026.md` — data breach notification
- `lessons/ai-red-teaming-2026.md` — pre-deployment adversarial testing

## Source URLs (verified 2026-08-10)

- https://www.nis-2-directive.com/
- https://artificialintelligenceact.eu/article/73/
- https://gdpr-info.eu/art-33-gdpr/
- https://www.eba.europa.eu/regulation-and-policy/internal-governance/digital-operational-resilience-act-dora
- https://www.deepinspect.ai/blog/nis2-ai-requirements
