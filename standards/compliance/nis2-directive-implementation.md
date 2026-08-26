# nis2-directive-implementation

**Issue:** Implementing NIS2 Directive (EU 2022/2555) requirements for essential and important entities
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
NIS2 replaced NIS1 with broader scope, stronger requirements, and personal liability for management. Member states transposed NIS2 into national law by October 2024. Covers essential entities (energy, transport, health, infrastructure) and important entities (digital, postal, manufacturing).

## Pattern / Solution
Article 21 security measures (ten mandatory categories):
1. Risk analysis and information system security policies
2. Incident handling (detection, response, recovery)
3. Business continuity and crisis management
4. Supply chain security (including ICT supplier security)
5. Security in network and information systems acquisition, development, and maintenance
6. Policies and procedures to assess effectiveness of cybersecurity measures
7. Basic cyber hygiene practices and training
8. Policies and procedures on use of cryptography and encryption
9. Human resources security (background checks, security awareness)
10. Use of multi-factor authentication and secure communications

Incident notification:
- Early warning to national CSIRT within 24 hours of significant incident
- Incident notification within 72 hours (with initial assessment)
- Intermediate report (if requested by CSIRT)
- Final report within 1 month

Significant incident thresholds (any one sufficient):
- Severely disrupts service delivery
- Caused significant financial loss
- Affected other entities or individuals significantly

Management liability (Article 20):
- Management bodies must approve cybersecurity measures
- Management can be held personally liable for NIS2 violations
- Mandatory security training for management

Penalties:
- Essential entities: up to EUR 10M or 2% of global turnover (whichever higher)
- Important entities: up to EUR 7M or 1.4% of global turnover

## Gotchas
- National transposition differs across EU member states — check local law for specific obligations
- Supply chain security requirement is broad — may require security assessments of key ICT suppliers
- "Significant incident" definition can be expansive; when in doubt, notify
- NIS2 and DORA overlap for financial sector — DORA lex specialis applies first

## Related
- `nis2-directive.md`
- `dora-regulation.md`
- `security-incident-response-plan.md`
