# pdpa-thailand-compliance

**Issue:** Thailand Personal Data Protection Act B.E. 2562 (2019) full enforcement compliance
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Thailand PDPA (fully effective June 2022) applies to any entity processing personal data of individuals in Thailand, regardless of entity location. Regulator: PDPC (Personal Data Protection Committee).

## Pattern / Solution
Lawful bases: Consent, Contractual necessity, Vital interests, Legal obligation, Public task, Legitimate interest
Sensitive data (requires explicit consent): race, ethnic origin, political opinion, religion/belief, sexual behavior, criminal records, health, disability, trade union, genetic data, biometric data for identification.

Implementation checklist:
- Privacy notice in Thai (or English with Thai summary for local users)
- Consent: freely given, specific, informed, unambiguous — pre-ticked boxes invalid
- Separate consent for each purpose; consent must be as easy to withdraw as to give
- Written Data Processing Agreement with every processor
- No mandatory DPO in PDPA, but recommended for large-scale processing
- Cross-border transfers: destination country must have equivalent protection (no formal adequacy list) or use contractual clauses
- Breach notification: notify PDPC within 72 hours; notify data subjects without undue delay when high risk
- Data subject rights: access, rectification, deletion, restriction, portability, objection — respond within 30 days

Penalties: Administrative up to 5M THB. Criminal: imprisonment up to 1 year and/or fine up to 1M THB. Civil: actual damages plus punitive up to 2x.

## Gotchas
- Cookie consent must comply with PDPA — analytics and advertising cookies require opt-in
- PDPC has issued sector-specific guidance that can override general PDPA requirements
- No formal adequacy framework yet — do not rely on GDPR SCCs directly; adapt for Thai law
- Thai companies outsourcing overseas processing must still take responsibility as data controller

## Related
- `gdpr-consent-management.md`
- `cross-border-data-transfer-mechanisms.md`
