# ai-incident-disclosure-deep-2026

**Issue:** An AI system in production produces harmful output (medical advice, financial recommendation, election misinformation). The team debates incident reporting obligations. The team reads about NIS2, EU AI Act serious incident reporting, GDPR breach notification. The team needs the 2026 reference.

**Date:** 2026-08-10
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## The 5 incident reporting regimes

1. **NIS2 Directive (EU, effective Oct 2024, full application Oct 2026).** Essential entities (health, energy, transport, banking, digital infrastructure) report significant incidents to CSIRT within 24h early warning, 72h notification, 1-month final report.
2. **EU AI Act serious incident reporting (Article 73).** Providers and deployers of high-risk AI report serious incidents to market surveillance authorities of the Member States where the incident occurred.
3. **GDPR Article 33.** Personal data breach notification to supervisory authority within 72h.
4. **US state laws.** Various; e.g., Colorado AI Act requires notice of algorithmic discrimination.
5. **Voluntary frameworks.** AI Incident Database (Partnership on AI), OECD AI Observatory.

## The 5 NIS2 timeline details

1. **24h - early warning.** "Significant impact on continuity of essential services." Initial report; can be brief.
2. **72h - incident notification.** "Assessment of the significant impact." Including severity, impact, indicators of compromise.
3. **1 month - final report.** Detailed description, severity, type of threat, mitigation applied.
4. **Ongoing - intermediate reports.** As requested by CSIRT.
5. **Final - upon closure.** Status when incident is fully resolved.

## The 5 EU AI Act incident types (Article 73)

1. **Death** of a person.
2. **Serious damage** to health.
3. **Serious and irreversible damage** to property or the environment.
4. **Serious and irreversible disruption** of critical infrastructure.
5. **Breach of fundamental rights** as defined in EU law.

## The 5-step incident response pattern

1. **Detect** - monitoring, user reports, internal audit.
2. **Triage** - severity assessment, scope, jurisdiction.
3. **Contain** - stop the harm (model rollback, kill switch, traffic blocking).
4. **Notify** - within 24h/72h to relevant authorities.
5. **Review** - root cause, post-mortem, public communication.

## The 5 anti-patterns

1. **"AI hallucinations aren't incidents"** - some are serious incidents under Article 73.
2. **No pre-built notification templates** - 24h SLA impossible to meet.
3. **Single-jurisdiction notification list** - multi-jurisdiction incidents need multi-agency notice.
4. **Public denial before internal assessment.** Destroys trust.
5. **No incident database** to track patterns over time.

## The 5 best practices

1. **Pre-build notification templates** for each regime (NIS2 24h, GDPR 72h, AI Act serious incident).
2. **Maintain authority contact list** by jurisdiction, updated quarterly.
3. **AI Incident Database submission** for public pattern tracking.
4. **Disclosure policy** with graduated transparency (private to authorities, then public).
5. **Post-incident review** published (in responsible-disclosure style).

## Verification

The tell that incident response is real:

- Notification templates pre-built for NIS2, GDPR, AI Act
- Authority contact list current and tested
- 24h/72h SLAs documented and exercised in tabletop
- Incident database with severity, scope, response timeline
- Public disclosure policy graduated (private to public)
- Post-mortem template with root cause + corrective action

The tell it isn't:

- "We'd figure it out when something happens"
- No template, no list, no SLA
- Single contact, single jurisdiction
- No post-mortem practice

## Gotchas

- AI Act serious incident is broader than "physical harm" - includes fundamental rights breaches.
- NIS2 essential entities include digital infrastructure (cloud providers, data centers).
- 24h is calendar time, not business hours.
- Public disclosure and regulatory notification are different; the latter often must come first.
- Voluntary AI Incident Database submission can support both learning and regulatory defense.

## Source URLs (verified 2026-08-10)

- https://www.enisa.europa.eu/topics/nis-directive
- https://artificialintelligenceact.eu/article/73/
- https://gdpr-info.eu/art-33-gdpr/
- https://incidentdatabase.ai/
- https://oecd.ai/
