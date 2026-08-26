# appi-japan-compliance

**Issue:** Japan Act on the Protection of Personal Information (APPI) 2022 amendments compliance
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
APPI (revised effective April 2022) introduced extraterritorial scope, stricter consent for sensitive data, mandatory opt-out registration for third-party provision, and breach notification requirements. Japan has EU adequacy status.

## Pattern / Solution
Key 2022 changes:
- Extraterritorial scope: foreign businesses handling Japanese residents data to provide goods/services
- Sensitive personal information (yohairyo kojin joho): race, creed, social status, medical history, criminal record, disability — requires explicit consent; no opt-out available
- Pseudonymously processed information (kamei kako joho): allows internal analytics without individual consent; cannot be provided to third parties
- Opt-out for non-sensitive third-party provision: must register with PPC before transferring; data subjects can opt out via PPC
- Breach notification: notify PPC promptly (initial report 3-5 days; full report within 30 days); notify individuals without delay when risk of harm

Data subject rights:
- Disclosure, correction, cessation of use, deletion
- Third-party provision records disclosure
- Right to opt out of opt-out provisions

Cross-border transfers:
- Adequacy (EU, UK): direct transfer permitted
- Other countries: individual consent OR ensure equivalent protection with written agreement and PPC verification

## Gotchas
- Cookie-based behavioral advertising may constitute third-party provision requiring PPC opt-out registration
- Sensitive PI rules are stricter than GDPR — no legitimate interest exception
- Japan-EU adequacy is mutual — Japanese data protection standards must be maintained for EU data
- PPC actively enforces and publishes guidance annually

## Related
- `gdpr-international-transfers-schrems2.md`
- `pdpa-thailand-compliance.md`
