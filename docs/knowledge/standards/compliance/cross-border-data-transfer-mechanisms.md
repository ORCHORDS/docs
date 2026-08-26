# cross-border-data-transfer-mechanisms

**Issue:** Overview of lawful mechanisms for international personal data transfers across major privacy regimes
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Multiple privacy regimes regulate cross-border data transfers. Organizations operating globally need a map of available transfer mechanisms per jurisdiction pair.

## Pattern / Solution
Transfer mechanism comparison:

| From \ To | US | UK | Brazil | Japan | Canada |
|-----------|----|----|--------|-------|--------|
| EU        | DPF / SCCs + TIA | UK Adequacy + IDTA | SCCs + TIA | Adequacy | Commercial PIPEDA adequacy |
| UK        | UK-US DPB / IDTA | N/A | IDTA | UK adequacy | IDTA |
| Brazil    | Contractual clauses (ANPD) | Contractual clauses | N/A | Contractual clauses | Contractual clauses |

Mechanism types:
1. Adequacy decision: no additional safeguards needed; simplest path
2. Standard contractual clauses (SCCs): most versatile; requires TIA for EU and UK
3. Binding corporate rules (BCRs): for intra-group; DPA approval required; 12-24 month process
4. Consent (derogation): for occasional, one-off transfers only; not systematic
5. Contractual necessity: only for transfers directly necessary for contract with data subject

Processor vs. Controller transfers:
- Controller-to-processor: data processing agreement + SCCs Module 2 (EU) or equivalent
- Processor-to-sub-processor: SCCs Module 3 or sub-processor clauses
- Controller-to-controller: SCCs Module 1 or adequacy

Key actions:
- Build a transfer mapping: source country -> destination country -> data category -> mechanism -> status
- Review transfer mapping quarterly
- Execute SCCs before data flows, not retrospectively

## Gotchas
- "Transfer" includes remote access by staff in another country — VPN access to EU system from non-adequate country is a transfer
- Processor in adequate country does not automatically cover sub-processors in non-adequate countries
- SCCs are jurisdiction-specific: EU SCCs do not cover UK; UK IDTA does not cover EU
- Emergency access by support staff in non-adequate country must be governed by transfer mechanism

## Related
- `gdpr-international-transfers-schrems2.md`
- `data-localization-requirements.md`
- `lgpd-brazil-compliance.md`
