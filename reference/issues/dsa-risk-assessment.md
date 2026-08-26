# dsa-risk-assessment

**Issue:** EU DSA risk assessment for VLOPs and VLOSEs
**Date:** 2026-08-09
**Status:** documented (compliance checklist)

## Symptom
Your platform is a "Very Large Online Platform" (VLOP) under
the DSA. You haven't done a formal risk assessment. The
European Commission asks for one. You're out of compliance.

## Root cause
The Digital Services Act (DSA) requires VLOPs and VLOSEs to:
- Conduct an annual **risk assessment** of systemic risks
- Implement **mitigation measures** for identified risks
- Submit to **independent audit** of risk mitigation
- Share data with **researchers** and authorities on request

The first deadline was August 2024 for entities designated
before then; new designations have 4 months.

**Source:** DSA text:
https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:32022R2065

## When are you a VLOP?

The Commission designates VLOPs based on:
- Number of EU users (threshold: 45M / ~10% of EU population)
- Public health, public security, or public debate impact
- Systemic risks to society

As of 2024, the designated VLOPs include AliExpress, Amazon,
App Store, Booking.com, Facebook, Google Play, Instagram,
LinkedIn, Pinterest, Snapchat, TikTok, X, YouTube, Zalando.

For a social platform with 45M+ EU users, you are likely a VLOP.

## Risk assessment scope

The DSA defines 4 categories of systemic risks:

### 1. Illegal content
- CSAM (child sexual abuse material)
- Terrorism content
- Hate speech
- Counterfeit goods
- IP infringement

### 2. Fundamental rights
- Freedom of expression
- Right to privacy
- Right to non-discrimination
- Rights of the child

### 3. Civic discourse and elections
- Election interference
- Disinformation
- Coordinated inauthentic behavior
- Manipulation of public debate

### 4. Public health, minors, well-being
- Addictive design
- Mental health impacts (especially for minors)
- Eating disorder content
- Self-harm content

## Mitigation measures

For each risk, document:
- **Risk description**
- **Affected user groups**
- **Probability and severity**
- **Existing mitigations** (content moderation, age gates, etc.)
- **Gaps and planned mitigations**
- **Effectiveness measurement** (KPIs)

Example:
```markdown
## Risk: CSAM in user uploads
- Affected users: All platform users, especially minors
- Probability: Medium
- Severity: Critical
- Existing mitigations:
  - Hash-based detection (PhotoDNA integration — pending)
  - User reporting
  - Trained T&S team
- Gaps:
  - Hash-based detection not yet integrated (vendor onboarding
    in progress, see open issue)
  - No proactive discovery (relies on user reports)
- Planned mitigations:
  - Vendor integration (Q4 2026)
  - Proactive discovery via ML (2027)
- KPIs:
  - Time-to-detect (target: < 24h for known content)
  - Time-to-remove (target: < 1h)
  - NCMEC reports filed per quarter
```

## Annual audit

The DSA requires an independent audit of risk mitigation.
The audit is paid for by the platform and conducted by an
auditor accredited by the Commission.

The audit report is public.

## Data sharing with researchers

VLOPs must share data with **vetted researchers** who study
systemic risks. The researchers apply via the Commission's
"researcher access" portal.

For implementation, see the data access layer in
`engine/researcher_access/`.

## Verification
- **Test:** Annual risk assessment is documented and approved
  by the legal team
- **Live:** The risk assessment is published (or accessible
  to the Commission on request)
- **Audit:** Annual third-party audit of the assessment +
  mitigations

## Gotchas
- **The risk assessment is not a checkbox.** It's a living
  document. Update when new risks emerge (e.g. new
  product features, new attack vectors).
- **The mitigation measures must be effective, not just
  documented.** A documented plan with no implementation is
  non-compliant.
- **The 4-month deadline for new designations is strict.**
  If the Commission designates you, you have 4 months to
  complete the first assessment.
- **Crisis response plans are required.** The DSA mandates
  a crisis response mechanism for events affecting public
  health, security, or elections.
- **Transparency reports are required.** Publish quarterly
  transparency reports covering: content moderation actions,
  government requests, recommender system changes.

## Related
- `audit-log-mandatory.md` (the data for the report)
- `csrd-reporting-deadline.md` (related EU regulation)
- `compliance/store-region-matrix.md` (where DSA applies)
- DSA text: https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:32022R2065
