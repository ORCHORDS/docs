---
title: "EU AI Act — Regulation 2024/1689 Version Guide"
standard: "Regulation (EU) 2024/1689"
publisher: "European Union"
category: "reference"
subcategory: "ai-regulation"
canonical_url: "https://eur-lex.europa.eu/eli/reg/2024/1689/oj"
status: "approved"
classification: "public"
audience: "Legal, AI governance leads, AI deployers in EU markets, product leads"
last-reviewed: "2026-09-04"
review-cycle: "180 days"
next-review: "2027-03-03"
---

# EU AI Act — Regulation (EU) 2024/1689 Version Guide

## Profile

Regulation (EU) 2024/1689 (the "EU AI Act") entered into force August 1, 2024, with phased applicability through August 2, 2027. It establishes a horizontal, risk-based regulatory framework for AI systems placed on the EU market or used in the EU, regardless of the provider's location. It is the first binding horizontal AI regulation.

The regulation imposes obligations on providers, deployers, importers, distributors, and authorized representatives, with extra-territorial scope for outputs used in the EU. It defines a four-tier risk pyramid (unacceptable-risk prohibited practices, high-risk obligations, limited-risk transparency obligations, minimal-risk voluntary codes of conduct), plus specific rules for general-purpose AI (GPAI) models and systemic-risk GPAI models.

## Identifier

| Field | Value |
| --- | --- |
| Citation | Regulation (EU) 2024/1689 |
| OJ reference | OJ L of 12 July 2024 |
| Entry into force | 2024-08-01 |
| General applicability | 2026-08-02 (24 months after entry into force) |
| GPAI obligations | 2025-08-02 (12 months after entry into force) |
| Prohibited practices | 2025-02-02 (6 months after entry into force) |
| Companion | GDPR (Regulation 2016/679), Digital Services Act, EU AI Liability Directive (proposal) |

## Risk Pyramid

| Tier | Treatment |
| --- | --- |
| Unacceptable risk | Prohibited AI practices (Article 5): social scoring, manipulative techniques exploiting vulnerabilities, biometric categorization for sensitive categories, untargeted scraping for facial recognition databases, real-time remote biometric identification in public spaces for law enforcement (with exceptions). |
| High risk | Annex III categories (biometrics, critical infrastructure, education, employment, essential services, law enforcement, migration, justice, democratic processes); compliance obligations in Articles 8–17 include risk management, data governance, technical documentation, record-keeping, transparency, human oversight, accuracy/robustness/cybersecurity, conformity assessment, CE marking, registration. |
| Limited risk | Transparency obligations (Article 50): inform users when interacting with AI, when exposed to emotion recognition or biometric categorization, when synthetic content is generated. |
| Minimal risk | Voluntary codes of conduct; no legal obligation. |

## GPAI and Systemic-Risk GPAI

| Tier | Obligations |
| --- | --- |
| GPAI model (10^25 FLOPs training compute threshold via Commission delegated act) | Provide documentation, comply with copyright law, summary of training data. |
| Systemic-risk GPAI (most capable models) | Above + model evaluations, adversarial testing, systemic risk assessment, incident reporting. |

## Penalties

| Violation | Maximum administrative fine |
| --- | --- |
| Prohibited practices (Article 5) | EUR 35,000,000 or 7% of worldwide annual turnover, whichever is higher |
| Other obligations (provider/deployer) | EUR 15,000,000 or 3% |
| Supplying incorrect information | EUR 7,500,000 or 1% |

## ORCHORDS Profile

| Field | ORCHORDS convention |
| --- | --- |
| Adoption | ORCHORDS-managed AI systems placed on the EU market or used in the EU MUST conform to this Regulation. |
| Classification | Classify every AI system against the four-tier pyramid; record the classification and rationale. |
| High-risk pathway | Implement Annex IV technical documentation, Article 9 risk management, Article 14 human oversight. |
| Conformity assessment | Apply the appropriate conformity assessment pathway (internal or with notified body) before placing on market or putting into service. |
| EU database | Register high-risk AI systems in the EU database before deployment. |
| Transparency | Disclose AI interaction (Article 50) for affected systems; mark synthetic content where required. |
| GPAI | Treat GPAI model integration as a Tier 2 / Tier 3 responsibility for downstream deployers. |
| Logging | Maintain logs that satisfy Article 12 record-keeping obligations for high-risk AI systems. |
| Notification | Notify serious incidents and report to market surveillance authorities per Article 73. |
| Litigation | Treat violations as matters engaging Legal; cooperate with investigations; document regulatory inquiries. |

## Implementation Notes

- Map overlapping and divergent requirements against the NIST AI 100-1 (AI RMF 1.0), AI 600-1, and ISO/IEC 42001 controls.
- Maintain an Annex IV technical file as a working document throughout the lifecycle; do not generate it only at conformity assessment.
- Apply the prohibited-practices list (Article 5) at concept and design stage; reject designs before development.
- GPAI obligations apply to providers, but also affect deployers who fine-tune or substantially modify GPAI models.
- Sector overlays (medical devices, machinery, toys, vehicles) integrate with this Regulation via EU sectoral law.

## Companion Documents

- [GDPR Article 33 Breach Notification](GDPR_ARTICLE_33_BREACH_NOTIFICATION.md)
- [NIST AI 100-1 AI RMF 1.0 Version Guide](NIST_AI_100_1_AI_RMF_1_0_VERSION_GUIDE.md)
- [NIST AI 600-1 Generative AI Profile](NIST_AI_600_1_GENAI_PROFILE_VERSION_GUIDE.md)
- [ISO/IEC 42001:2023 AIMS Version Guide](ISO_IEC_42001_2023_AIMS_VERSION_GUIDE.md)
