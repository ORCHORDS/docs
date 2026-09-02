# ITIL 4 Service Desk Practice Governance

## Purpose

Govern the ITIL 4 service desk practice so that users have a single, known entry point for issues and requests, demand is captured accurately at intake, and the desk operates as a quality-gated interface between users and the rest of the service value chain.

## Scope

The practice applies to the studio's user-facing support function: channels, intake, categorization, escalation, and closure. It does not cover incident resolution technique (incident management) or request fulfilment workflow design (request management).

## Workflow

1. Publish the supported channels (portal, email, chat, phone) with hours of service and expected response targets per channel.
2. Capture every contact as a ticket with requester, channel, urgency, impact, and a description sufficient for later analysis; walk-ins and hallway requests enter the same system.
3. Apply categorization and a priority matrix at intake so that routing and reporting rest on consistent data.
4. Apply tiered support: first-line resolution within defined limits, structured escalation to specialist teams with required handover content.
5. Keep requesters informed on the committed cadence for their ticket's priority, especially when the news is "no progress yet."
6. Close tickets only with requester confirmation or a documented attempt to confirm; auto-closure without notice is prohibited.
7. Analyze ticket trends by category, channel, and team to find recurring demand that belongs in problem management or self-service.

## Controls and evidence

- Channel catalogue with service hours and response targets.
- Intake field schema with mandatory categorization and priority derivation rule.
- Escalation matrix with handover content requirements and tier boundaries.
- Ticket trend report by category, channel, and team, reviewed on the practice cadence.
- Closure policy and the requester-confirmation evidence trail.

## Validation

- Sample 10 closed tickets and confirm closure met the confirmation policy.
- Confirm priority assignments in the sample follow the priority matrix without manual overrides that lack rationale.
- Confirm the trend analysis ran on cadence and produced at least one improvement action per cycle.

## Failure correction

- **Tickets closed without requester confirmation** → reopen the affected tickets, notify requesters, and enforce the closure gate.
- **Intake data quality poor (missing category or impact)** → make the fields mandatory, retrain intake staff, and audit weekly until quality recovers.
- **Recurring demand not routed to problem management** → transfer the trend finding, open a problem record, and link the recurring incidents to it.

## Limitations

- The desk captures demand; it does not fix systemic causes. Value is realized when trend findings flow into problem management and self-service.
- Response targets are operational commitments, not contractual SLAs; contract commitments live elsewhere.
- Tier boundaries decay as skills grow; review them when escalation latency rises.

## Scope note

This article is part of the operations leaf and pairs with incident management and service level management practices. Cross-reference: `itil-4-incident-and-problem-management-practice.md`, `SRE_RELEASE_COORDINATION_ERROR_BUDGET_GOVERNANCE.md`, and `ITIL_4_SERVICE_DESIGN_PRACTICE_GOVERNANCE.md`.

## Canonical sources

- AXELOS, *ITIL Foundation, ITIL 4 edition* (2019), service desk practice: https://www.axelos.com/certifications/itil-service-management
- ITIL 4 Practices — Service Desk: https://www.axelos.com/certifications/itil-service-management/itil-4-practices
- ISO 10002:2018 — Quality management — Customer satisfaction — Guidelines for complaints handling in organizations: https://www.iso.org/standard/63352.html
- HDI — Support Center Practices: https://www.thinkhdi.com/
- ISO/IEC 20000-1:2018 — Service management — Requirements: https://www.iso.org/standard/73686.html
