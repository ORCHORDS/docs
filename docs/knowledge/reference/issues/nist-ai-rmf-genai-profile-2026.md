# nist-ai-rmf-genai-profile-2026

**Issue:** A US company deploys a generative AI assistant to customers. The team has no AI risk management framework. The board asks "what are our AI risks?"; the team has no structured answer. Voluntary frameworks exist; the team doesn't know which to follow.
**Date:** 2026-08-10
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Symptom

The US has no single binding AI law comparable to the EU AI Act. The de facto national framework is the NIST AI Risk Management Framework (AI RMF 1.0, January 2023) plus its companion profiles. A US team building, deploying, or procuring generative AI is expected to follow AI RMF and the Generative AI Profile (NIST-AI-600-1, July 2024).

## Root cause

NIST AI RMF is voluntary, sector-agnostic, and organized around four iterative functions: GOVERN, MAP, MEASURE, MANAGE. The Generative AI Profile (NIST AI 600-1) maps these functions to 12 risk categories specific to generative AI, pursuant to Executive Order 14110 (October 2023) on Safe, Secure, and Trustworthy Development and Use of AI.

For US federal agencies, AI RMF is mandatory through OMB M-24-10 and M-25-21. For private sector, it's voluntary — but it is the framework regulators reach for when asking "what is your AI risk management process?"

## The four functions

| Function | Purpose | Timing |
|---|---|---|
| **GOVERN** | Establish the organizational culture, roles, policies, and processes that make risk management possible | Before and throughout deployment |
| **MAP** | Identify and categorize the AI system, its context, users, and failure modes | Pre-deployment; revisit at major changes |
| **MEASURE** | Assess, test, and track risk against defined metrics | Pre-deployment and continuously in production |
| **MANAGE** | Prioritize risks, implement responses, monitor, and improve | Ongoing throughout system lifecycle |

A critical note: the functions are iterative, not sequential. GOVERN runs throughout; MEASURE feeds MANAGE; MAP is revisited when the system changes. The Playbook (updated ~2× per year) provides suggested actions for each subcategory.

## The 12 Generative AI Profile risk categories

NIST AI 600-1 maps 12 GAI-specific risk categories to AI RMF subcategories:

1. **CBRN information** — uplift to chemical, biological, radiological, nuclear threats
2. **Confabulation (hallucination)** — false or fabricated outputs
3. **Data privacy** — risks from training data ingestion, memorization, inference outputs
4. **Data provenance** — tracking the origin and history of training data
5. **Harmful bias and homogenization** — bias amplification and output homogenization at scale
6. **Human-AI configuration** — calibration of human oversight to risk level
7. **Information integrity** — disinformation, synthetic media, influence operations
8. **Information security** — prompt injection, data poisoning, model extraction, evasion
9. **Intellectual property** — training data copyright, IP exposure in outputs
10. **Obscene or abusive content** — moderation for sexual, violent, abusive content
11. **Transparency and documentation** — model cards, system cards, disclosure
12. **Value chain and component integration** — third-party model and component risks

## The required artifacts

| Artifact | Satisfies | Typical owner |
|---|---|---|
| AI inventory / system register | GOVERN 1.6, MAP 1.1, MAP 2 | AI Ops / GRC |
| Risk tolerance statement | GOVERN 1.3, MAP 1.5 | Executive / Risk Committee |
| Context documentation | MAP 1.1, MAP 1.3, MAP 1.4 | System owner |
| Impact assessment | MAP 5.1, MANAGE 1.3 | AI Ethics / GRC |
| Model card | MAP 2.2, MEASURE 2.5, MEASURE 2.9 | ML Engineering |
| TEVV test set documentation | MEASURE 2.1, MEASURE 2.5 | ML Engineering / QA |
| Bias / fairness test results | MEASURE 2.11 | Data Science |
| Privacy risk assessment | MEASURE 2.10 | Privacy / Security |
| Residual risk register | MANAGE 1.4 | Risk Manager |
| Incident response plan | MANAGE 4.1, MANAGE 4.3 | Security / Ops |
| Post-deployment monitoring plan | MANAGE 4.1, MEASURE 2.4 | MLOps |
| Third-party AI risk inventory | GOVERN 6, MAP 4 | Procurement / GRC |

A MEASURE plan for an LLM-based system that does not reference NIST AI 600-1 is incomplete.

## The implementation phases

A typical 9-month rollout for a mid-size enterprise:

| Phase | Duration | Activities | FTE load |
|---|---|---|---|
| Foundation (GOVERN) | Weeks 1-6 | Policy drafting, RACI, inventory stand-up | 0.5-1 FTE program lead + legal review |
| Inventory and MAP | Months 2-4 | System-by-system MAP documentation for top 20 highest-risk systems | 0.5 FTE per system × 20 systems |
| Measurement baseline (MEASURE) | Months 3-6 | Bias tests, TEVV documentation, model card templates | 1-2 FTE data science + 0.5 FTE security |
| Production monitoring (MANAGE) | Months 5-9 | Monitoring platform deployment; incident response runbook; drift thresholds | 1 FTE MLOps |
| First review cycle | Month 12 | Internal audit against all subcategories; gap remediation | 0.5 FTE internal audit |

The 12-month cycle from kickoff to first internal audit is the typical timeline for a mid-size enterprise. Smaller teams can compress to 6-9 months by limiting scope to the highest-risk systems.

## The what-your-organization-must-do pattern

NIST AI 600-1 implies concrete obligations:

- Map all generative AI systems to the 12 risk categories; assign a responsible owner (AI risk lead or product owner) per category; document gaps against suggested actions
- Update the enterprise AI governance policy to address GAI risks explicitly (hallucination thresholds, CBRN safeguards, content moderation standards); present to board/risk committee within 90 days
- Establish a confabulation and output quality monitoring programme with defined measurement cadences (at minimum quarterly), documented acceptable error thresholds, and a disclosure protocol for material confabulation incidents
- Require all third-party generative AI vendors to supply model cards, system cards, and training data provenance documentation as a contractual condition; assign third-party risk management to review
- Conduct training data and output IP review for any fine-tuned or deployed model; engage legal; implement output filtering or attribution controls where infringement risk is identified
- Align internal GAI security controls with the profile's information security requirements; task cybersecurity to test for prompt injection, data poisoning, model extraction on a defined schedule (at minimum annually or after significant model updates)

## The voluntary vs. mandatory distinction

For private-sector organizations, NIST AI RMF and AI 600-1 are voluntary. There is no penalty for non-compliance with the framework itself.

For US federal agencies, AI RMF is mandatory through OMB guidance. The OMB M-24-10 memo (March 2024) required federal agencies to inventory AI use cases, designate Chief AI Officers, and apply AI RMF practices. The OMB M-25-21 memo (2025) further specified minimum risk management practices.

For contractors selling AI to the federal government, AI RMF compliance is de facto mandatory through procurement requirements. RFPs increasingly require AI RMF or AI 600-1 compliance as a contract condition.

## The relationship to other frameworks

NIST AI RMF cross-maps to:

- **ISO/IEC 42001 (AIMS)** — both are management system approaches; ISO 42001 is certifiable; AI RMF is voluntary
- **EU AI Act** — AI RMF's GOVERN/MAP/MEASURE/MANAGE structure is broadly compatible with the AI Act's risk management lifecycle (Article 9)
- **OWASP AI Security & Privacy Guide** — provides technical implementation for the information security risk category
- **MITRE ATLAS** — adversary tactics for AI systems; complements the information security category

A team that has implemented AI RMF has done 60-70% of the work needed for ISO 42001 certification and a similar fraction of the EU AI Act's high-risk obligations.

## Verification

The tell that NIST AI RMF implementation is working:

- A documented AI inventory with system owners, risk categories, and risk tolerance
- A model card for every production AI system, reviewed at least quarterly
- An incident response plan tested against a GAI-specific scenario (prompt injection, model extraction, confabulation incident)
- Bias and privacy tests run on a defined cadence with documented thresholds
- A residual risk register signed by the executive owner
- Third-party AI vendors contractually required to provide model cards and data provenance

The tell it isn't:

- "We follow AI RMF" with no AI inventory
- A model in production with no model card
- An incident triggers ad-hoc response because there's no runbook
- Bias testing has not been run since the model was deployed

## Gotchas

- **AI RMF is voluntary for private sector, mandatory for federal agencies and contractors.** The same framework applies to both, but the enforcement is different.
- **AI 600-1 is required for any LLM-based system.** A MEASURE plan that doesn't reference it is incomplete.
- **The 12 risk categories map to specific artifacts.** Without the artifacts, the framework is performative.
- **The 9-month rollout is for mid-size enterprises.** Smaller teams can compress; larger teams should plan 12-18 months.
- **AI RMF is iterative, not sequential.** GOVERN runs throughout; MEASURE feeds MANAGE.
- **Cross-mapping to ISO 42001 and EU AI Act is high.** A team that has implemented AI RMF has 60-70% of the work done for both.

## Related

- `compliance/eu-ai-act-code-of-practice-2026.md` — the EU binding counterpart
- `issues/iso-iec-42001-aims-2026.md` — the certifiable counterpart
- `issues/eu-ai-act-annex-iii-2026.md` — the high-risk classification that triggers the AI Act

## Source URLs (verified 2026-08-10)

- https://www.nist.gov/itl/ai-risk-management-framework
- https://aisecurityandsafety.org/en/frameworks/nist-ai-600-1/
- https://nvlpubs.nist.gov/nistpubs/ai/NIST.AI.600-1.pdf
- https://aigovernance.com/policy/nist-ai-600-1-generative-ai-profile
- https://aicompliancevendors.com/guides/nist-ai-rmf-implementation-guide
