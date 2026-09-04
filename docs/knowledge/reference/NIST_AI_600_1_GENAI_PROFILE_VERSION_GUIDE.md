---
title: "NIST AI 600-1 Generative AI Profile Version Guide"
standard: "NIST AI 600-1"
publisher: "U.S. National Institute of Standards and Technology (NIST)"
category: "reference"
subcategory: "ai-risk-management"
canonical_url: "https://www.nist.gov/itl/ai-risk-management-framework/generative-ai-profile"
status: "approved"
classification: "public"
audience: "Generative AI developers, deployers, risk officers, auditors"
last-reviewed: "2026-09-04"
review-cycle: "180 days"
next-review: "2027-03-03"
---

# NIST AI 600-1 Generative AI Profile Version Guide

## Profile

NIST AI 600-1 (July 26, 2024) is the Generative AI Profile for the AI Risk Management Framework. It enumerates the unique risks of generative AI (GAI) systems — confabulation, data leaking, information integrity, dangerous, biased, or harmful information, content provenance, intellectual property, privacy, and harmful bias — and provides 200+ actions aligned with AI RMF Core functions (GOVERN, MAP, MEASURE, MANAGE) to mitigate them.

The profile is intended for use alongside AI RMF 1.0; it does not replace it. The actions are organized by risk category and tagged with their primary AI RMF Core function. Implementers should select actions proportionate to the GAI system's context, capabilities, and intended use.

## Identifier

| Field | Value |
| --- | --- |
| Document number | NIST AI 600-1 |
| Title | Artificial Intelligence Risk Management Framework: Generative Artificial Intelligence Profile |
| Publication date | 2024-07-26 |
| Companion | NIST AI 100-1 (AI RMF 1.0) |
| Adversarial ML companion | NIST AI 100-2 (2024-01-04) |

## Unique GAI Risks Covered

| Risk | Mitigation (representative actions) |
| --- | --- |
| Confabulation | Retrieval grounding, citation enforcement, output filtering, uncertainty calibration, evaluation against truthfulness benchmarks. |
| Data leaking | Training-data scrubbing, membership inference testing, output screening, prompt-injection hardening, retention enforcement. |
| Information integrity | Provenance (C2PA Content Credentials, watermarking), authenticity verification, downstream filtering. |
| Dangerous, biased, or harmful information | Domain restriction, safety classifiers, abuse testing, red teaming, refuse-list maintenance. |
| Content provenance and IP | Ingest licensing controls, attribution tracking, output hashing, opt-out honoring for web/music/news sources. |
| Privacy | Data minimization, consent management, training data review, differential privacy, deletion mechanisms. |
| Harmful bias and representational harm | Bias measurement, dataset curation, benchmark testing across demographic groups, mitigation interventions. |
| Hazardous chemical, biological, radiological, or nuclear (CBRN) information | Filtering of dual-use content, restricted deployment of dual-use APIs, refusal patterns, access controls. |

## ORCHORDS Profile

| Field | ORCHORDS convention |
| --- | --- |
| Companion pairing | Pair with NIST AI 100-1 for AI RMF Core functions; pair with NIST AI 100-2 for adversarial-threat actions. |
| Risk record | Each GAI risk category listed in this profile MUST be logged in the AI system record with applicable NIST AI 600-1 actions selected. |
| Provenance | Adopt C2PA Content Credentials for GAI-synthesized media produced by or through ORCHORDS-managed systems. |
| Confabulation | Require retrieval-grounded generation with citations where the application makes factual claims. |
| CBRN filters | Apply filters, restrictions, and access controls on any GAI system whose capabilities could materially assist CBRN misuse. |
| Measurement | Maintain a documented measurement plan covering confabulation rate, bias benchmarks, and red-team findings. |
| Lifecycle gating | Do not promote GAI models to production until confabulation, bias, and safety thresholds are met and risk acceptance is recorded. |

## Implementation Notes

- The 200+ actions are an enumeration; do not treat them as a checklist. Choose actions based on the system's deployment context and user impact.
- Confabulation mitigation alone (e.g., retrieval) does not satisfy harmful-information mitigation; safety classifiers or domain restriction are independent controls.
- Provenance markers should be applied at the platform layer where feasible rather than relying on downstream detectors.
- Pair the profile with sector overlays (health, finance, education) and regulators' guidance when applicable.

## Companion Documents

- [NIST AI 100-1 AI RMF 1.0 Version Guide](NIST_AI_100_1_AI_RMF_1_0_VERSION_GUIDE.md)
- [NIST AI 100-2 Adversarial Machine Learning Taxonomy](NIST_AI_100_2_ADVERSARIAL_ML_VERSION_GUIDE.md)
- [C2PA Content Credentials Version Guide](C2PA_CONTENT_CREDENTIALS_VERSION_GUIDE.md)
- [OECD AI Principles Version Guide](OECD_AI_PRINCIPLES_2024_VERSION_GUIDE.md)
- [EU AI Act Version Guide](EU_AI_ACT_2024_1689_VERSION_GUIDE.md)
