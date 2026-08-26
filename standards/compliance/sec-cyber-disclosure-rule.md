# sec-cyber-disclosure-rule

**Issue:** SEC cybersecurity incident disclosure and governance rules (effective December 2023)
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
SEC final rules require public companies (domestic and foreign private issuers) to disclose material cybersecurity incidents within 4 business days of determining materiality, and to disclose cybersecurity risk management and governance annually.

## Pattern / Solution
Incident disclosure (Item 1.05 on Form 8-K):
- Trigger: determine that a cybersecurity incident is "material" (would a reasonable investor consider it important?)
- Timeline: file Form 8-K within 4 business days of materiality determination (NOT discovery)
- Content: nature, scope, timing, material impact or reasonably likely material impact
- Disclosure may be delayed only if Attorney General certifies national security/public safety risk

Annual disclosure (Form 10-K, Item 106):
- Risk management: describe processes for assessing, identifying, and managing material risks from cybersecurity threats
- Governance: describe Board oversight of cybersecurity risks; describe management role (CISO, committee)
- Material incidents from prior year: describe any incidents disclosed on 8-K during fiscal year

Materiality assessment process:
```
Incident detected -> CISO/Legal triage (24-48h) ->
    Assess: financial impact, operational disruption, customer harm,
            regulatory consequences, reputational damage ->
    Legal materiality determination ->
    If material: 8-K filed within 4 business days
    Document decision with date and rationale regardless of outcome
```

Board reporting template:
- Quarterly cyber risk briefing to board or audit committee
- Documented minutes; board members with cyber expertise identified in proxy

## Gotchas
- "4 business days" starts from materiality determination, not incident discovery — document determination date explicitly
- Ransomware: paying may be material; investigate before determining non-material
- Foreign Private Issuers use Form 20-F (annual) and Form 6-K (material events) — different timeline
- Companies must also assess supply chain incidents for materiality — not just own systems

## Related
- `security-incident-response-plan.md`
- `audit-log-mandatory.md`
