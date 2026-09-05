---
title: "EU AI Act — General Purpose AI (GPAI) Obligations Version Guide"
standard: EU Regulation 2024/1689 Articles 51–56
publisher: European Parliament and Council
category: reference
subcategory: ai-governance
canonical_url: https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:32024R1689
status: approved
classification: public
audience: ai-governance, legal, platform-engineering, model-providers
last-reviewed: 2026-09-05
review-cycle: 12 months
next-review: 2027-09-05
---

## Scope

Articles 51–56 of the EU AI Act impose obligations on providers of
general-purpose AI (GPAI) models and on downstream providers integrating
GPAI into high-risk AI systems. Additional obligations apply to GPAI models
classified as posing systemic risk.

This guide captures the GPAI obligations, the systemic-risk threshold, the
downstream provider duties, and how ORCHORDS profiles GPAI adoption.

## Identifier Table

| Field | Value |
| --- | --- |
| Instrument | Regulation (EU) 2024/1689 |
| Articles | 51, 52, 53, 54, 55, 56 |
| Title | General-purpose AI models |
| Applicability | GPAI obligations 2 August 2025; systemic-risk GPAI 2 August 2025 |
| Companion | Article 25 (deployer duties for embedded high-risk), Annex XI (technical docs for systemic risk) |

## Plan

1. Identify whether each model used by ORCHORDS is a GPAI model under Article 3(63) and whether the model crosses the systemic-risk threshold in Article 51(2) (training compute threshold set by the Commission via delegated act, currently 10^25 FLOPs as initial indicator).
2. For GPAI models, demand from the provider: technical documentation (Annex XI equivalent), downstream integration policies, copyright compliance summary, and a public summary of training data.
3. For systemic-risk GPAI, additionally demand model evaluation and adversarial testing, systemic-risk evaluation per state-of-the-art, incident reporting, and cybersecurity protection.
4. When ORCHORDS develops or fine-tunes GPAI, the obligations transfer to ORCHORDS as the new provider.

## Inputs

- Vendor model cards and technical documentation.
- Provider conformity statement and downstream integration policy.
- Training compute logs and dataset summaries.
- Incident reporting channel from the GPAI provider.

## ORCHORDS Profile Table

| ORCHORDS field | ORCHORDS value |
| --- | --- |
| GPAI model register | Source, version, access mode (API/fine-tuned/local), provider |
| Systemic-risk assessment | Compute threshold check, downstream impact analysis |
| Downstream documentation | Annex XI equivalent demanded before first production use |
| Incident reporting SLA | Receive notifications from provider within 15 days for serious incidents |
| Copyright compliance | Provider must summarise training-data compliance with EU copyright law |

## Implementation Notes

- Fine-tuning a GPAI with significant modifications makes ORCHORDS a new
  provider; ORCHORDS must take on the obligations before deployment.
- When GPAI is integrated into a high-risk system, the downstream provider
  carries the high-risk obligations, but must still pass the GPAI provider
  obligations through the supply chain.
- The Commission may designate a model as systemic-risk based on capabilities
  even below the compute threshold (Article 51(2)).
- Penalties for GPAI obligations up to 3 % of worldwide turnover.

## Companion Documents

- EU AI Act Reference Card
- EU AI Act — Annex III Reference Card
- EU AI Act — Article 5 Prohibited Practices Reference Card
- ISO/IEC 42001:2023 Reference Card
- NIST AI 100-1 Reference Card
- NIST AI 600-1 Reference Card
