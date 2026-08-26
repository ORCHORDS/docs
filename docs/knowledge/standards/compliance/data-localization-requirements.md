# data-localization-requirements

**Issue:** Navigating country-specific data localization laws that prohibit cross-border transfers
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Data localization laws require that certain categories of personal data be stored and processed within national borders. These laws create architectural constraints for global SaaS products.

## Pattern / Solution
Major localization requirements by jurisdiction:

Russia (Federal Law 242-FZ): personal data of Russian citizens must be stored on servers in Russia. Roskomnadzor can block non-compliant services. Implement a dedicated Russian database tier.

China (PIPL + DSL + CSL):
- Personal information: consent-based cross-border transfer rules OR store locally
- Important data: must store in China; cross-border transfer requires security assessment by CAC
- Critical information infrastructure: all data must stay in China
- Implementation: China-region deployment (separate from global), data residency tagging

India (DPDP Act 2023): Central government may restrict transfer of personal data to certain countries (restricted list not yet published). Monitor for notification. Sensitive financial and health data: localization likely required by regulation.

Indonesia (PP 71/2019): strategic personal data must be stored in Indonesia. Electronic system operators must have local servers for strategic data.

Vietnam (Decree 13/2023): important personal data (health, financial, location, personal relations) must be stored in Vietnam for at least 24 hours; long-term copy can be abroad.

Architecture pattern for localization:
```
Global App -> Geo-routing layer -> detect user jurisdiction ->
  if Russia: write to Russia DB (ru-central)
  if China: write to China DB (isolated VPC, CN region)
  if India: write to India DB (ap-south-1) or global until notified
  else: write to global DB
```

Data residency tags: tag all records with storage_jurisdiction; enforce in access layer.

## Gotchas
- Localization often applies to the primary copy — analytics/backups may also need to be local
- Localization and GDPR are sometimes in conflict — legal review required for EU citizens in China
- China's regulations are complex and evolving; engage local legal counsel
- Failure to comply can result in service blocking, fines, or criminal liability for local representatives

## Related
- `cross-border-data-transfer-mechanisms.md`
- `gdpr-international-transfers-schrems2.md`
- `store-region-matrix.md`
