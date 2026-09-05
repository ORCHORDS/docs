---
title: "ISO/IEC 23894:2023 AI Risk Management Version Guide"
standard: "ISO/IEC 23894:2023"
publisher: "International Organization for Standardization (ISO) and International Electrotechnical Commission (IEC)"
category: "reference"
subcategory: "ai-risk-management"
canonical_url: "https://www.iso.org/standard/87209.html"
status: "approved"
classification: "public"
audience: "AI risk managers, AI developers, deployers, auditors"
last-reviewed: "2026-09-04"
review-cycle: "180 days"
next-review: "2027-03-03"
---

# ISO/IEC 23894:2023 AI Risk Management Version Guide

## Profile

ISO/IEC 23894:2023 provides guidance on managing AI-related risks for organizations of all sizes and sectors. It defines the principles, processes, and a framework for AI risk management that can be integrated with ISO 31000 (general risk management) and that complements the controls of ISO/IEC 42001 (AIMS). The standard addresses AI-specific challenges: the statistical nature of model behavior, the impact of training data quality, the opacity of some model families, the dynamic nature of model behavior in deployment, and the difficulty of anticipating emergent properties.

The standard is process-oriented: it does not mandate specific controls, but defines six risk-management steps (context establishment, risk identification, risk analysis, risk evaluation, risk treatment, monitoring and review) and aligns them with AI system lifecycle stages.

## Identifier

| Field | Value |
| --- | --- |
| Standard | ISO/IEC 23894:2023 |
| Title | Information technology — Artificial intelligence — Guidance on risk management |
| Publication date | 2023 (1st edition) |
| Companion | ISO/IEC 42001 (AIMS), ISO/IEC 42005 (AI impact assessment), ISO 31000 (general risk management) |
| Cross-reference | NIST AI 100-1 (AI RMF Core functions align with 23894 lifecycle stages) |

## Risk Management Process

| Step | Activity |
| --- | --- |
| Context establishment | Define the AI system, its purpose, the deployment context, interested parties, and risk criteria. |
| Risk identification | Identify AI risks across development and operational use; cover data, model, system, process, and external environments. |
| Risk analysis | Assess likelihood and consequence; consider AI-specific factors (data drift, adversarial robustness, opacity). |
| Risk evaluation | Compare analyzed risks against risk criteria; produce a prioritized list. |
| Risk treatment | Select and implement controls (avoid, mitigate, transfer, accept); document treatment plans. |
| Monitoring and review | Continuously monitor risk indicators; review the framework's effectiveness; iterate. |

## Lifecycle Integration

| AI lifecycle stage | Key risk activities |
| --- | --- |
| Concept and design | Establish risk context, identify stakeholders, draft risk criteria. |
| Data collection and preparation | Identify data-quality, provenance, privacy, and bias risks; evaluate dataset risks. |
| Model development | Identify modeling risk (overfitting, opacity, robustness); analyze trade-offs. |
| Verification and validation | Analyze model risk on evaluation data; document performance gaps. |
| Deployment | Identify deployment and integration risks; set monitoring thresholds. |
| Operation and monitoring | Detect performance drift, adversarial activity, misuse; review risks. |
| End of life | Identify retirement, decommissioning, and data disposition risks. |

## ORCHORDS Profile

| Field | ORCHORDS convention |
| --- | --- |
| Adoption | Cite this standard as the methodology basis for AIMS Clause 6 and Clause 8 risk assessments. |
| Context statement | Required for each AI system; record context in the AI system record. |
| Risk criteria | Maintain a documented risk criteria table for each AI system; align with organizational risk appetite. |
| Treatment | Treatment plans recorded with explicit owners, completion dates, and acceptance rationale. |
| Monitoring | Use the standard's monitoring indicators as a baseline; augment with AI RMF Core function metrics. |
| Reporting | Produce summary risk reports aligned with the standard's process language to support internal audits and ISO/IEC 42001 management reviews. |

## Implementation Notes

- AI risk management under this standard is a continuous process; do not treat it as a one-time launch-gate activity.
- AI-specific risk factors (data drift, opacity, adversarial robustness) should be added to risk criteria, not forced into generic categories.
- The standard pairs naturally with ISO/IEC 42001; AIMS provides the management system wrapper, 23894 provides the methodology.
- Coordinate with privacy risk management under ISO/IEC 27701 for AI systems that process personal data.

## Companion Documents

- [ISO/IEC 42001:2023 AIMS Version Guide](ISO_IEC_42001_2023_AIMS_VERSION_GUIDE.md)
- [ISO/IEC 42005 AI Impact Assessment Version Guide](ISO_IEC_42005_AI_IMPACT_ASSESSMENT_VERSION_GUIDE.md)
- [NIST AI 100-1 AI RMF 1.0 Version Guide](NIST_AI_100_1_AI_RMF_1_0_VERSION_GUIDE.md)
- [ISO 31000:2018 Risk Management Version Guide](ISO_31000_2018_RISK_MANAGEMENT_VERSION_GUIDE.md)
