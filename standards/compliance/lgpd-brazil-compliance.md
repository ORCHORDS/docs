# lgpd-brazil-compliance

**Issue:** Brazil Lei Geral de Protecao de Dados (Law 13.709/2018) compliance requirements
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
LGPD applies to any organization processing personal data of individuals in Brazil regardless of the organization location. Enforced by ANPD (Autoridade Nacional de Protecao de Dados).

## Pattern / Solution
Lawful bases (10 total, broader than GDPR):
- Consent, Contract, Legal obligation, Public policy execution, Research (anonymized if possible), Contract performance, Legitimate interest, Credit protection, Life/safety protection, Health protection

Key compliance steps:
- Map all personal data flows involving Brazilian residents
- Identify lawful basis for each processing activity (document in ROPA equivalent)
- Appoint Encarregado (DPO equivalent) — always mandatory regardless of company size; publish contact on website
- Privacy notice in Portuguese covering: controller identity, purposes, legal basis, rights, contact
- Data subject rights response within 15 days for access requests
- International transfers: use contractual clauses or ANPD-approved mechanisms (no formal adequacy list yet)
- Breach notification: notify ANPD within a reasonable timeframe (target 72 hours) if likely to cause harm; notify data subjects when severe
- RIPD (Data Protection Impact Report): required for high-risk processing; ANPD can request it

Penalties: up to 2% of Brazil revenue in prior year (group companies), max R$50M per violation. Suspension of processing allowed.

## Gotchas
- "Credit protection" basis is unique to LGPD and allows credit bureaus to process data without consent
- ANPD is still developing secondary regulations — monitor official guidance actively
- Brazil does not have a formal adequacy list; model international transfer clauses on GDPR SCCs
- Encarregado must be a person (natural or legal entity) — cannot be just an email address

## Related
- `gdpr-international-transfers-schrems2.md`
- `cross-border-data-transfer-mechanisms.md`
