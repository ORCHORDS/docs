# nis2-incident-reporting

**Issue:** NIS2 Directive incident reporting timeline
**Date:** 2026-08-09
**Status:** documented (compliance checklist)

## Symptom
Your platform has a security incident. 6 hours pass. The
regulator expects a "early warning" notification. You didn't
send one. You're in violation.

## Root cause
NIS2 (the EU's updated Network and Information Security
Directive) requires incident reporting on a strict timeline:
- **24 hours:** Early warning (incident occurred, suspected cause)
- **72 hours:** Incident notification (severity, impact, indicators
  of compromise)
- **1 month:** Final report (root cause, remediation, lessons)

**Source:** NIS2 text:
https://www.enisa.europa.eu/topics/nis-directive

> "Significant incidents shall be notified to the competent
> authority or CSIRT within 24 hours of becoming aware of them."

## When does it apply?

NIS2 applies to:
- **Essential entities:** energy, transport, banking, health,
  digital infrastructure (cloud, DNS, etc.)
- **Important entities:** postal services, waste management,
  digital services (social networks, online marketplaces)

For a digital platform with > 10M users or significant digital
infrastructure, you're in scope.

## What counts as a "significant" incident?

Per NIS2 Article 23:
- The incident causes or is capable of causing severe operational
  disruption of the services or financial loss for the entity
  concerned
- The incident affects or is capable of affecting other natural
  or legal persons by causing considerable material or
  non-material damage

In practice: any breach affecting user data, any service
disruption > 4 hours, any unauthorized access to systems.

## Fix
A runbook for the 3-stage reporting:

### Stage 1: Early warning (24h)
```ts
// 1. Detect the incident
// 2. Confirm severity (criteria above)
// 3. Notify regulator via the national CSIRT portal
//    (e.g. for EU: BSI for DE, ANSSI for FR, NCSC for UK)

const earlyWarning = {
  timestamp: incident.detectedAt,
  entities_affected: incident.affectedUserCount,
  suspected_cause: incident.initialAssessment,
  cross_border_impact: incident.isCrossBorder,
  assistance_required: incident.needsRegulatorHelp,
};
```

### Stage 2: Incident notification (72h)
```ts
const incidentNotification = {
  ...earlyWarning,
  severity: incident.severity,  // 'low' | 'medium' | 'high' | 'critical'
  impact_assessment: incident.userImpact,
  indicators_of_compromise: incident.iocs,
  affected_systems: incident.systems,
  data_exfiltration: incident.isPiiExfiltrated,
  supply_chain: incident.isSupplyChainCompromised,
};
```

### Stage 3: Final report (1 month)
```ts
const finalReport = {
  ...incidentNotification,
  detailed_root_cause: incident.rootCauseAnalysis,
  remediation_actions: incident.remediationPlan,
  lessons_learned: incident.postMortem,
  prevent_recurrence: incident.preventiveMeasures,
};
```

## What to track internally

### Detection
- **Time of detection** = when the team first became aware
- **Time of impact** = when the incident actually started
  (may be earlier; relevant for "duration")
- **Detection method** = SIEM alert, user report, vendor report

### Response
- **Time to triage** (target: < 1h)
- **Time to containment** (target: < 24h for critical)
- **Time to remediation** (target: < 1 week)

### Reporting
- **Time of early warning** (must be < 24h from detection)
- **Time of incident notification** (must be < 72h from
  detection)
- **Time of final report** (must be < 1 month from detection)

## Verification
- **Test:** Annual tabletop exercise simulating a 6-hour delay;
  verify the team knows the 24h/72h/1mo deadlines
- **Live:** The CSIRT portal is bookmarked; the on-call has
  credentials
- **Audit:** Annual third-party review of incident response
  capability

## Gotchas
- **The 24h clock starts at DETECTION, not at IMPACT.** A
  breach that started 3 months ago but was detected yesterday
  still has a 24h window from yesterday.
- **The CSIRT portal may be in the local language.** For
  multi-country incidents, you may need to notify multiple
  CSIRTs in their respective languages.
- **"Significant" is not "any" incident.** A spam complaint
  is not a NIS2 reportable incident. A data breach of
  10k users' emails is.
- **The incident may be ongoing at the 24h mark.** The early
  warning is "we're working on it, here's what we know so far."
  The 72h is the more detailed update.
- **Supply chain incidents** count. If a vendor you use has
  a breach, you may need to report it (depending on impact).
- **The 1-month deadline can be extended** if the investigation
  is complex. Document the extension request.

## Related
- `audit-log-mandatory.md` (the data needed for the report)
- `secrets-rotation-runbook.md` (post-incident response)
- ENISA: https://www.enisa.europa.eu/topics/nis-directive
- NIS2 full text: https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:32022L2555
