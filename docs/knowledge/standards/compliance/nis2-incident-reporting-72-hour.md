# NIS2 Incident Reporting: 72-Hour Notification Runbook

**Date:** 2026-08-17
**Author:** the platform team
**Status:** published

## Symptom

A production incident may qualify as a "significant
incident" under NIS2. The on-call engineer needs to know
within the first hour whether formal reporting is required,
who to notify, and what to document, without waiting for
a compliance team response.

## Context

Directive (EU) 2022/2555 (NIS2) replaced the original NIS
Directive and expanded its scope significantly. EU member
states were required to transpose NIS2 into national law
by 17 October 2024. NIS2 applies to entities providing
services in sectors listed in Annexes I and II and that
meet the size thresholds (50+ employees or €10M+ turnover).
Even below those thresholds, specific categories (DNS
providers, TLD registries, cloud providers, CDN providers,
managed-security providers) are in scope regardless of size.

Entity scope:

| Category          | Sector examples (Annex I/II)              |
|-------------------|--------------------------------------------|
| Essential entities| Energy, transport, banking, health, water, |
|                   | digital infrastructure, space              |
| Important entities| Postal, waste, manufacturing, chemicals,   |
|                   | food, digital providers, research          |

"Digital providers" (cloud, CDN, online marketplaces,
search engines, social platforms) are always "important
entities" under Art. 3(1)(f) regardless of size when
serving EU users.

## 1. What Counts as a Significant Incident

Art. 23(3) defines a significant incident as one that:

```
Criterion A — Impact on service delivery:
  Availability: service disruption ≥ 1 hour for more than
  a defined number of affected users (set by national law;
  typically ≥ 5 000 users for important entities)

Criterion B — Impact on other entities:
  The incident has caused or could cause significant damage
  to other entities or to public order, safety, or health

Criterion C — Financial loss:
  Material financial loss to the entity

Criterion D — Data breach:
  Actual or potential unauthorised access to, or
  destruction / alteration of, data processed by the entity
```

Decision tree for on-call use:

```
START
  │
  ├─ Availability impact ≥ 1 hour? ──YES──► significant (A)
  │
  ├─ Suspected unauthorised access to data? ──YES──► significant (D)
  │
  ├─ Could affect other organisations / critical infra? ──YES──► significant (B)
  │
  └─ None of the above ──► NOT significant — document and close
```

When in doubt, report. Late reporting is a violation;
over-reporting is not.

## 2. The Three-Stage Reporting Timeline

NIS2 Art. 23 mandates three successive notifications:

```
Hour 0   — Incident detected / declared
    │
    ├── Hour 24 — EARLY WARNING to national CSIRT
    │    Content: initial notice, whether it is suspected
    │    to be malicious, cross-border impact, initial
    │    severity assessment
    │
    ├── Hour 72 — INCIDENT NOTIFICATION to CSIRT + authority
    │    Content: updated assessment, initial impact data,
    │    indicators of compromise, mitigation measures taken
    │
    └── Month 1 — FINAL REPORT to CSIRT + authority
         Content: detailed incident description, threat type,
         root cause, measures taken and planned, cross-border
         impact, financial impact estimate
```

The clock starts at the moment the entity "becomes aware"
of the incident, not when the incident is confirmed or
the root cause is known.

ENISA contact hub for cross-border incidents and EU-level
coordination:

- ENISA NIS Cooperation: https://www.enisa.europa.eu/topics/incident-response
- EU-CyCLONe (Large-scale incidents): https://www.enisa.europa.eu/topics/cyber-crisis-management

Each member state designates a national CSIRT. Report to
your national CSIRT first. Major national CSIRTs:

| Country    | CSIRT / Authority            | Portal                          |
|------------|------------------------------|---------------------------------|
| Germany    | BSI / CERT-Bund              | https://www.bsi.bund.de         |
| France     | ANSSI / CERT-FR              | https://www.cert.ssi.gouv.fr    |
| Netherlands| NCSC-NL                      | https://www.ncsc.nl             |
| Ireland    | NCSC-IE                      | https://www.ncsc.gov.ie         |
| Sweden     | NCSC-SE / CERT-SE            | https://www.cert.se             |

## 3. Engineering Runbook — Incident Detection to 72 Hours

```
T+0: Incident declared in PagerDuty / incident channel
  ├─ Create incident ticket in Jira / Linear
  ├─ Assign NIS2 decision-tree (see §1)
  └─ If significant: page compliance lead + CISO immediately

T+1h: Assemble response team
  ├─ Incident commander assigned
  ├─ Communications lead assigned
  ├─ Engineering lead assigned
  └─ Evidence preservation: snapshot logs NOW before rotation

T+4h: Initial technical assessment
  ├─ Confirm affected services and user count
  ├─ Estimate duration of disruption
  ├─ Determine if data access / exfiltration is suspected
  └─ Draft early warning content (24-hour notice)

T+24h: EARLY WARNING submitted to national CSIRT
  ├─ Submit via CSIRT portal or secure email
  ├─ Copy: CISO, Legal, DPO (if data breach suspected)
  └─ Archive submission confirmation in incident ticket

T+48h: Technical investigation continues
  ├─ Root cause analysis in progress
  ├─ Containment measures in place
  └─ Draft 72-hour notification content

T+72h: INCIDENT NOTIFICATION submitted
  ├─ Submit to national CSIRT + supervisory authority
  ├─ Include: IoCs, affected user count, mitigation steps
  └─ Archive submission

T+30 days: FINAL REPORT submitted
  ├─ Root cause confirmed
  ├─ Corrective measures implemented or planned
  ├─ Cross-border impact assessment
  └─ Archive in incident register (retain ≥ 5 years)
```

Preserve the following evidence from T+0:

```bash
# Snapshot CloudFlare logs for the incident window
curl "https://api.cloudflare.com/client/v4/zones/${ZONE_ID}/logs/received" \
  -H "Authorization: Bearer ${CF_API_TOKEN}" \
  -G \
  -d "start=$(date -u -d '4 hours ago' +%s)" \
  -d "end=$(date -u +%s)" \
  -d "fields=ClientIP,ClientRequestHost,ClientRequestPath,EdgeResponseStatus,EdgeStartTimestamp" \
  > "incident-${INCIDENT_ID}-cf-logs.ndjson"

# Export D1 audit log for the window
npx wrangler d1 execute production \
  --command "SELECT * FROM audit_logs
             WHERE created_at >= datetime('now', '-4 hours')
             ORDER BY created_at ASC" \
  --json > "incident-${INCIDENT_ID}-audit.json"
```

Store evidence snapshots in an immutable location
(R2 bucket with Object Lock enabled, or S3 WORM). Do not
rely on live logs — log rotation may destroy evidence
before the 30-day final report is due.

## 4. 72-Hour Notification Template

```
TO:   [National CSIRT secure submission portal / email]
CC:   [Supervisory authority]

SUBJECT: NIS2 Art. 23 Incident Notification — [Entity name]
         — Incident ID: [INC-YYYYMMDD-NNN]

1. ENTITY DETAILS
   Name:             [Legal entity name]
   NIS2 category:    [Essential / Important]
   Sector:           [Annex I/II sector]
   Contact:          [CISO name, email, phone]

2. INCIDENT DETAILS
   First detected:   [ISO 8601 datetime UTC]
   Reporting time:   [ISO 8601 datetime UTC]
   Nature:           [Availability / Confidentiality / Integrity]
   Cause (if known): [Ransomware / DDoS / Misconfiguration / Unknown]

3. IMPACT ASSESSMENT
   Services affected:        [List]
   Estimated users affected: [Number or range]
   Geographic scope:         [Member states affected]
   Duration of disruption:   [hh:mm or ongoing]
   Data breach suspected:    [Yes / No / Unknown]
   Cross-border impact:      [Yes / No / Unknown]

4. MEASURES TAKEN
   [Bulleted list of containment and mitigation steps]

5. INDICATORS OF COMPROMISE (if available)
   [IP addresses, file hashes, domains — TLP:AMBER]

6. FURTHER INFORMATION
   Final report expected by: [Date = detection + 30 days]
```

## 5. Cross-Reference with DORA

For entities also subject to DORA (Regulation (EU) 2022/2554
— Digital Operational Resilience Act, applicable to
financial entities from 17 January 2025), NIS2 and DORA
incident reporting overlap but are not identical:

| Dimension          | NIS2                          | DORA                               |
|--------------------|-------------------------------|------------------------------------|
| Scope              | All sectors in Annex I/II     | Financial sector only              |
| Early warning      | 24 hours                      | 4 hours (ICT-related)              |
| Intermediate report| 72 hours                      | 72 hours                           |
| Final report       | 1 month                       | 1 month                            |
| Authority          | National CSIRT + NCA          | Financial supervisory authority    |
| Thresholds         | National law (availability)   | DORA RTS (financial impact)        |

If your entity is a financial entity (bank, payment
institution, investment firm) or a critical ICT third-party
provider to a financial entity, both frameworks may apply.
Submit to both authorities; coordinate content so reports
are consistent. DORA's 4-hour early-warning window is
stricter — use it as the default trigger for any
financially-relevant incident.

## Anti-patterns

- Waiting for root cause before notifying — the clock
  starts at awareness, not at diagnosis.
- Reporting only to the CISO and assuming they will handle
  it — engineering owns evidence preservation from T+0.
- Deleting or rotating logs before the 30-day final report
  window closes.
- Treating a DDoS that lasted under 1 hour as non-
  reportable without checking data-breach criterion (D).
- Using the national CSIRT email only — most authorities
  have a structured web portal that provides a receipt
  and tracking number needed for your records.

## Gotchas

- "Significant incident" thresholds (affected-user counts,
  financial loss values) are set by national transposing
  legislation and vary by member state. The thresholds
  applicable to your entity depend on where you are
  established and which member states' markets you serve.
- NIS2 notifications are typically NOT public — they go
  to authorities under confidentiality protections. Do
  not conflate with public breach notifications under
  GDPR Art. 34.
- If the incident also triggers GDPR Art. 33 (personal
  data breach), a separate notification to the DPA is
  required within 72 hours of the controller becoming
  aware. The GDPR 72-hour clock is independent.

## Verification

1. Run a tabletop exercise: inject a mock "availability
   down for 2 hours for 10 000 users" scenario and time
   how long it takes to reach the Early Warning stage
   in the runbook. Target: < 4 hours from incident
   declaration to draft Early Warning content.
2. Confirm the incident ticket template in Jira / Linear
   includes fields for: NIS2 category, affected user
   count, detection time, and CSIRT submission URL.
3. Verify log preservation: create a test snapshot using
   the Bash commands in §3 and confirm files land in
   the WORM bucket.
4. Confirm the CISO and DPO are PagerDuty responders on
   the "NIS2 Significant Incident" escalation policy.

## Related

- `/compliance/nis2-directive.md`
- `/compliance/nis2-article-23-incident-reporting-playbook.md`
- `/compliance/dora-digital-operational-resilience.md`
- `/compliance/gdpr-breach-notification-72h.md`
- `/compliance/security-incident-response-plan.md`
- `/compliance/audit-log-mandatory.md`

## Source URLs (verified 2026-08-17)

- https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:32022L2555
- https://www.enisa.europa.eu/topics/incident-response/reporting
- https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:32022R2554
- https://www.enisa.europa.eu/publications/enisa-nis-investments-report
- https://digital-strategy.ec.europa.eu/en/policies/nis2-directive
