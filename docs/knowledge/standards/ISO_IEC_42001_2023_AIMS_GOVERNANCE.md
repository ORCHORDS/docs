---
title: ISO/IEC 42001:2023 AI Management System (AIMS) Governance
owner: Knowledge Engineering
status: approved
classification: public
last-reviewed: 2026-09-05
review-cycle: 180 days
next-review: 2027-03-04
source: ISO/IEC 42001:2023 (first edition, 2023-12-18) — "Information technology — Artificial intelligence — Management system"; https://www.iso.org/standard/81230.html
---

# ISO/IEC 42001:2023 AI Management System (AIMS) Governance

## Scope

This card governs how `orchords-docs` evaluates AI components referenced from KB cards against ISO/IEC 42001:2023 — the first globally recognized AI management system standard. It binds KB expansion that touches model providers, embedding pipelines, or AI-assisted tooling.

## Why this card exists

ISO/IEC 42001 (AIMS) prescribes a Plan-Do-Check-Act cycle for AI governance: policy, impact assessment, lifecycle management, third-party assurance, data quality, transparency, and continual improvement. A KB that cites AI systems without binding to 42001 risk-treatments produces a reference architecture that does not survive an AI-specific audit.

## Document structure (Clauses 4 — 10)

| Clause | Title | Project interpretation |
|---|---|---|
| 4 | Context of the organization | KB is published as a public artifact; "interested parties" = readers, auditors, contributors |
| 5 | Leadership | `ORCHORDS.COM` token owner is top management |
| 6 | Planning | AI impact assessment is mandatory before adopting a new AI system in a reference card |
| 7 | Support | resources, competence, awareness, communication, documented information |
| 8 | Operation | operational planning and control, AI impact assessment, AI system lifecycle, data for AI, third-party assurance |
| 9 | Performance evaluation | monitoring, measurement, analysis, internal audit, management review |
| 10 | Improvement | nonconformity, corrective action, continual improvement |

References: `https://www.iso.org/standard/81230.html`.

## Annex A — Control objectives and controls (subset)

ISO/IEC 42001 Annex A lists AI-specific controls. The KB expansion pipeline binds a subset:

| Control | Title | Project obligation |
|---|---|---|
| A.5.1 | AI policy | reference architecture cards that cite AI must reference the AIMS policy |
| A.5.2 | AI roles and responsibilities | RACI for AI lifecycle stages |
| A.6.1.2 | AI system life cycle | documented in `AI_LIFECYCLE_GOVERNANCE.md` (if present) |
| A.6.2.1 | AI impact assessment | mandatory before adopting a new model in a reference card |
| A.6.2.2 | AI risk treatment | risks mapped to controls A.6.3.x through A.7.x |
| A.6.2.3 | AI system acceptance | PR review + staging evaluation |
| A.6.2.4 | AI system operation and monitoring | observability on every AI reference architecture |
| A.6.2.5 | AI system retirement | decommission plan before adoption |
| A.6.3.1 | Data quality for AI | data lineage, bias testing |
| A.6.3.2 | Data acquisition | lawful basis, provenance, consent |
| A.6.3.3 | Data preparation | pipeline audit logs |
| A.6.4.1 | AI explainability | transparency card per model family |
| A.6.4.2 | AI transparency | disclosure in reference architecture cards |
| A.7.1 | AI third-party assurance | supplier due diligence |
| A.7.2 | AI supplier relationship | DPA + AIMS attestation |
| A.8.1 | AI system responsibility | named accountable owner |
| A.8.2 | AI documentation | KB card frontmatter must include model name, version, vendor |
| A.8.3 | AI knowledge and skill | reader-facing prerequisites |
| A.8.4 | AI toolchain security | supply-chain hardening per SSDF |
| A.9.1 | Bias, fairness, and ethics | bias testing before adoption |
| A.9.2 | AI reliability | reproducibility check |
| A.9.3 | AI safety | safety risk assessment |
| A.9.4 | AI security | security threat model |

References: ISO/IEC 42001:2023 Annex A control titles.

## AI impact assessment (mandatory)

Before adopting a new AI system in a reference card, the project must produce an AI Impact Assessment (AIIA) that covers:

1. Intended purpose and affected stakeholders.
2. Data classes used (PII, sensitive, public).
3. Model class (LLM, embedding, classification, regression, generative).
4. Output constraints (deterministic, bounded stochasticity).
5. Failure modes (hallucination, bias, data leakage, jailbreak).
6. Risk treatment plan (controls A.6.3.x → A.9.x applied).
7. Acceptance criteria (factual accuracy, refusal rate, latency).

The AIIA is filed with the change ticket and referenced from the KB card.

## Transparency obligations

Every reference card that cites an AI system must include:

- The model name, version, and vendor.
- The license terms for the model and the output.
- Any data classes the model is fed in the reference architecture.
- The data classes the model can produce in its output.
- Any non-deterministic behavior and its bounds.
- Any rate limits or quotas imposed by the provider.

## Mandatory pre-flight (before adopting a new AI system in a reference card)

1. AI Impact Assessment is filed.
2. Risk-treatment plan is filed.
3. The provider has a current 42001 attestation or equivalent (e.g., NIST AI RMF profile, EU AI Act Article 9 conformity assessment).
4. The model version is pinned in the reference card.
5. Bias testing is documented with a measurable outcome.
6. Observability is wired into the reference architecture (latency, token usage, refusal rate, factual accuracy).

## Self-attestation cycle

Every 180 days, the project must:

1. Walk every reference card that cites an AI system.
2. Confirm the AI Impact Assessment is current.
3. Confirm the model version is still the pinned version (not drifted).
4. Confirm observability is still wired.
5. Update the next-review date.

## Sources

- ISO/IEC 42001:2023: `https://www.iso.org/standard/81230.html`
- ISO/IEC 42001:2023 Annex A (controls): see ISO/IEC 42001:2023 PDF
- NIST AI Risk Management Framework (AI RMF 1.0): `https://www.nist.gov/itl/ai-risk-management-framework`
- EU AI Act (Regulation (EU) 2024/1689): `https://eur-lex.europa.eu/eli/reg/2024/1689/oj`
