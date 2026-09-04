---
title: "NIST AI 100-1 AI Risk Management Framework 1.0 Version Guide"
standard: "NIST AI 100-1"
publisher: "U.S. National Institute of Standards and Technology (NIST)"
category: "reference"
subcategory: "ai-risk-management"
canonical_url: "https://www.nist.gov/itl/ai-risk-management-framework"
status: "approved"
classification: "public"
audience: "AI developers, deployers, risk officers, auditors, policy makers"
last-reviewed: "2026-09-04"
review-cycle: "180 days"
next-review: "2027-03-03"
---

# NIST AI 100-1 AI Risk Management Framework (AI RMF) 1.0 Version Guide

## Profile

NIST AI 100-1 (January 26, 2023) is the foundational AI Risk Management Framework developed by the NIST AI Risk Management Framework Working Group. It defines the vocabulary, characteristics, and core functions (GOVERN, MAP, MEASURE, MANAGE) for managing AI system risks across the AI lifecycle. AI RMF 1.0 is voluntary, sector-agnostic, and intended to be used by organizations designing, developing, deploying, evaluating, or acquiring AI systems.

AI RMF 1.0 is structured to pair with the AI RMF Playbook (NIST AI 100-2 reference set, *not* the adversary-ml profile that also carries that publication number) and with subsequent profiles such as the Generative AI Profile (NIST AI 600-1, July 2024) for GAI-specific risk categories. The Core is a set of outcomes — not a checklist; organizations are expected to implement actions, assessments, and mitigations proportionate to the AI system context and the trustworthiness characteristics (valid and reliable, safe, secure and resilient, accountable and transparent, explainable and interpretable, privacy-enhanced, fair with harmful bias managed).

## Identifier

| Field | Value |
| --- | --- |
| Document number | NIST AI 100-1 |
| Title | Artificial Intelligence Risk Management Framework (AI RMF) 1.0 |
| Publication date | 2023-01-26 |
| Status | Final (1.0) |
| Companion | AI RMF Playbook (AI 100-2 supplementary reference, July 2023 and 2024 updates) |
| Generative AI companion | NIST AI 600-1 (2024-07-26) |
| Adversarial ML companion | NIST AI 100-2 (2024-01-04) |

## Scope

AI RMF 1.0 applies to all AI systems and their components, including models, data, infrastructure, processes, and the human and organizational practices surrounding them, regardless of deployment stage or sector.

## Core Functions

| Function | Intent |
| --- | --- |
| GOVERN | Establish the policies, processes, procedures, and practices across the organization that govern AI risk management. |
| MAP | Establish the context to frame risks related to the development or deployment of AI systems. |
| MEASURE | Employ quantitative, qualitative, or mixed-method tools, techniques, and methodologies to analyze, assess, benchmark, and monitor AI risk and related impacts. |
| MANAGE | Allocate risk resources to mapped and measured risks on a regular basis and as defined by the GOVERN function. |

## Trustworthiness Characteristics

The framework uses seven characteristics: valid and reliable; safe; secure and resilient; accountable and transparent; explainable and interpretable; privacy-enhanced; fair with harmful bias managed. These are not checkboxes; they are outcomes to be balanced against the deployment context.

## ORCHORDS Profile

| Field | ORCHORDS convention |
| --- | --- |
| Adoption basis | Voluntary adoption recorded at the system inventory entry, with mapped GOVERNING policies. |
| Function ordering | GOVERN precedes MAP, MEASURE, MANAGE. |
| Profile pairing | Pair AI RMF Core with NIST AI 600-1 for any generative AI system; pair with NIST AI 100-2 for adversarial-threat assessment. |
| Risk register | AI risks MUST be recorded in the consolidated risk register with reference to AI RMF function and characteristic. |
| Impact assessment | Use ISO/IEC 42005 AIMS impact assessment as the documentation vehicle when available; cross-reference fields are required. |
| Lifecycle coverage | Map, Measure, and Manage activities MUST continue through decommissioning, not just at launch. |

## Implementation Notes

- GOVERN applies across the lifecycle, not just at design; do not implement MAP/MEASURE/MANAGE without a functioning GOVERN.
- MEASURE results without established metrics and acceptable thresholds are non-conformant; use explicit, documented measurement plans.
- MANAGE decisions and risk acceptance MUST be traceable to authorized risk owners; assign risk owners before launch.
- Pair with sector overlays (e.g., EEOC, FDA, NHTSA guidance) when the AI system is regulated by sector authorities; record the overlay mapping.

## Companion Documents

- [NIST AI 600-1 Generative AI Profile](NIST_AI_600_1_GENAI_PROFILE_VERSION_GUIDE.md)
- [NIST AI 100-2 Adversarial Machine Learning Taxonomy](NIST_AI_100_2_ADVERSARIAL_ML_VERSION_GUIDE.md)
- [ISO/IEC 42001:2023 AIMS Version Guide](ISO_IEC_42001_2023_AIMS_VERSION_GUIDE.md)
- [ISO/IEC 42005 AI Impact Assessment Version Guide](ISO_IEC_42005_AI_IMPACT_ASSESSMENT_VERSION_GUIDE.md)
- [OECD AI Principles Version Guide](OECD_AI_PRINCIPLES_2024_VERSION_GUIDE.md)
- [EU AI Act Version Guide](EU_AI_ACT_2024_1689_VERSION_GUIDE.md)
