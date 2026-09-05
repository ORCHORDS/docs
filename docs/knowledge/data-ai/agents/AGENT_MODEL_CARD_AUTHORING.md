---
title: Agent Model Card Authoring
owner: ORCHORDS AI Governance
status: active
classification: internal
last-reviewed: 2026-09-05
review-cycle: semiannual
next-review: 2027-03-05
source: NIST AI 600-1 Generative AI Profile §2.6 (Documentation & Transparency); ISO/IEC 42001:2023 Annex A.6 (Documentation of AI System); Mitchell et al. (2019) "Model Cards for Model Reporting"; EU AI Act 2024/1689 Art. 53 (Provider Obligations for GPAI)
---

## Scope

Defines the minimum content of an ORCHORDS-grade model card that accompanies every agent release. A model card records intended use, training data lineage, evaluation results, known failure modes, and accountability metadata so downstream operators can make an informed deployment decision. Applies to both upstream base models and ORCHORDS-tuned variants.

## Plan

1. Identify the model lineage: base model identifier, fine-tuning dataset(s), alignment procedure, and the SHA of the deployed weights.
2. State intended and explicitly excluded use cases. Refusal modes must enumerate categories the model is contractually restricted from assisting with.
3. Document training and evaluation data sources, including licence, provenance country, and personal-data class (if any). Reference the data sheet for each dataset.
4. Report metrics across the standard eval suite: capability, robustness, bias, factuality, and safety. Disaggregate by language and demographic where data permits.
5. Catalogue known failure modes, including observed jailbreak vectors, hallucination patterns, and tool-use errors.
6. Record accountability: model owner, evaluation lead, date of last refresh, next scheduled review.

## Inputs

- Training and evaluation pipeline manifests.
- Eval results from `AGENT_HALLUCINATION_DETECTION_CITATION_FAITHFULNESS` and `AGENT_ADVERSARIAL_ROBUSTNESS_PROBE`.
- Data lineage records from `data-ai/data-lineage/*` if the model was fine-tuned.
- Legal review of intended-use and exclusion statements.

## ORCHORDS Profile

| Dimension | Target |
|-----------|--------|
| Sections | ≥ 9 (model details, intended use, training data, eval, metrics, ethical considerations, caveats, recommendations, version) |
| Eval results | disaggregated across ≥ 3 axes (capability, robustness, safety) |
| Freshness | refreshed within 90 days of release |
| Accessibility | available before deployment at `/models/{card}.md` |
| Integrity | SHA-256 of weights referenced in card matches deployed artefact |

## Implementation Notes

- Embed the data sheets for any third-party dataset as a numbered appendix; do not duplicate within the card.
- When a card is updated, increment a minor version and record the change log in a leading section; never overwrite history silently.
- Use machine-readable front-matter (this file is a template) so tools like `model-card-validator` can parse without re-implementing extraction.
- If the model is GPAI subject to EU AI Act Art. 53, also produce an Annex IV "summary of training data" template.

## Companion Documents

- `AGENT_EVAL_LEAKAGE_PREVENTION.md` — separations preventing eval data from polluting training.
- `AGENT_BIAS_FAIRNESS_PROBING.md` — disaggregated metrics source.
- `ISO_IEC_42001_AI_MANAGEMENT_SYSTEM_GOVERNANCE.md` (standards) — governance envelope.
