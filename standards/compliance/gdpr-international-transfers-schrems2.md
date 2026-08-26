# gdpr-international-transfers-schrems2

**Issue:** Lawful mechanisms for transferring EU personal data after Schrems II invalidated Privacy Shield
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
CJEU Schrems II (C-311/18, 2020) invalidated EU-US Privacy Shield. All transfers to third countries require a Chapter V mechanism plus a Transfer Impact Assessment (TIA).

## Pattern / Solution
Available mechanisms in priority order:
1. Adequacy decision (Art. 45): EU-US Data Privacy Framework (2023), UK, Switzerland, Japan, Israel, Canada (commercial), New Zealand, South Korea
2. Standard Contractual Clauses (SCCs): 2021 modular SCCs — four modules for controller-controller, controller-processor, processor-controller, processor-processor
3. Binding Corporate Rules (BCRs): approved by lead DPA; for intra-group transfers
4. Derogations (Art. 49): explicit consent (one-off, not systematic), contract performance, vital interests — narrow, last resort only

Transfer Impact Assessment (TIA) steps:
- Map all personal data flows to third countries (data mapping tool)
- Identify transfer mechanism for each flow
- Assess destination country legal framework: surveillance laws, government access, remedies
- Determine if supplementary measures are needed: end-to-end encryption (keys in EU), pseudonymization, contractual commitments not to comply with unlawful access requests
- Document residual risk acceptance at board/DPO level
- Review annually or when laws change

## Gotchas
- EU-US DPF applies only to US entities that have self-certified — verify at dataprivacyframework.gov
- SCCs must be used verbatim — no material modifications
- A TIA is required even when using SCCs or DPF
- UK has its own SCCs (IDTA / Addendum) — EU SCCs alone do not cover UK transfers
- Sub-processor chains: every link must have compliant transfer mechanism

## Related
- `gdpr-dpa-standard-contractual-clauses.md`
- `cross-border-data-transfer-mechanisms.md`
