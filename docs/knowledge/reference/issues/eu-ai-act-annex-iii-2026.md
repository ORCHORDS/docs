# eu-ai-act-annex-iii-2026

**Issue:** A team deploys an AI system that screens job applications. Six months later, an EU regulator asks which Annex III category the system falls under, what the compliance obligations are, and when the deadline applies. The team has no answer.
**Date:** 2026-08-10
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Symptom

Annex III of the EU AI Act lists 8 categories of high-risk AI use cases. Any AI system in one of these areas inherits the full Article 9-15 obligation set for providers and Article 26 for deployers. A team that has not classified their system against Annex III cannot answer basic compliance questions.

## Root cause

Annex III defines high-risk by use case, not by technical architecture. The same underlying model can be high-risk in one context and not in another. A generic LLM used to draft marketing emails is not high-risk; the same LLM used to screen job applications is high-risk under category 4 (Employment).

The compliance deadline depends on the path. The EU Digital Omnibus (provisional agreement, May 7, 2026) pushed the full compliance deadline for standalone Annex III systems to December 2, 2027, with Annex I product-safety route pushed to August 2, 2028.

## The eight categories

| # | Category | Examples | Article 6(3) derogation? |
|---|---|---|---|
| 1 | Biometrics | Remote biometric identification, biometric categorisation, emotion recognition | Yes (verification is excluded) |
| 2 | Critical infrastructure | AI as safety component in road traffic, water/gas/heating/electricity supply, critical digital infrastructure | Yes (narrow procedural) |
| 3 | Education and vocational training | Admissions/assignment, scoring tests, detecting prohibited exam behaviour | Yes (narrow procedural) |
| 4 | Employment and worker management | CV screening, candidate ranking, task allocation, performance evaluation | Yes (narrow procedural) |
| 5 | Essential private and public services | Credit scoring, insurance pricing, public benefit eligibility, emergency dispatch | Yes (narrow procedural) |
| 6 | Law enforcement | Risk assessment of offending, evidence reliability evaluation, profiling | Yes (narrow procedural) |
| 7 | Migration, asylum, border control | Visa/asylum application assessment, security risk, document verification | Yes (narrow procedural) |
| 8 | Administration of justice and democratic processes | AI assisting a judicial authority, influencing elections/referenda | Yes (narrow procedural) |

## The decision table

| If your AI does this... | Annex III category | High-risk? |
|---|---|---|
| Screens job applications | Employment (4) | Yes |
| Monitors employee productivity | Employment (4) | Yes |
| Scores creditworthiness | Essential services (5) | Yes |
| Prices insurance policies | Essential services (5) | Yes |
| Identifies faces in real-time | Biometric (1) | Usually prohibited (Article 5) |
| Matches faces to a database post-event | Biometric (1) | Yes (law enforcement) |
| Determines access to a university course | Education (3) | Yes |
| Proctors online exams | Education (3) | Yes |
| Recommends courses to learners | Education (3) | No |
| Detects fraud for a private bank | Not listed | No |
| Detects fraud for law enforcement | Law enforcement (6) | Yes |
| Drafts emails using AI | None | No |
| Summarizes legal documents internally | None | No |
| Assists a judge in researching case law | Justice (8) | Yes |
| Optimizes energy usage in a building | None | No |
| Controls a power grid | Critical infrastructure (2) | Yes |

## The Article 6(3) derogation

An Annex III system is **not** high-risk where it "does not pose a significant risk of harm to the health, safety or fundamental rights of natural persons" and meets at least one of four conditions:

1. It performs a **narrow procedural task**.
2. It is intended to **improve the result of a previously completed human activity**.
3. It is intended to **detect decision-making patterns** or deviations from prior patterns, and is not meant to replace or influence the previously completed human assessment without proper human review.
4. It performs a **preparatory task** to an assessment relevant to the use cases in Annex III.

The derogation is narrow. "Detects decision-making patterns" with a human review at the end is excluded; "automatically decides" is not. A team relying on the derogation must document which condition applies and why.

## The two compliance paths

| Route | Original | After Digital Omnibus |
|---|---|---|
| Article 6(2) — Annex III high-risk use cases | 2 August 2026 | **2 December 2027** |
| Article 6(1) — Annex I product-safety (medical devices, machinery, lifts, etc.) | 2 August 2026 | **2 August 2028** |

Standalone high-risk AI systems (most employment, credit, education, biometric AI not embedded in a regulated product) must comply from **2 December 2027**.

High-risk AI embedded in Annex I regulated products (medical devices, machinery, lifts, etc., covered by existing EU harmonization law) must comply from **2 August 2028**.

## The Article 9-15 obligations

For high-risk systems, the provider must:

- **Article 9 — Risk management system:** Establish a risk management system run as a continuous iterative process across the lifecycle.
- **Article 10 — Data and data governance:** Training/validation/test data must be relevant, representative, free of errors to the extent possible, and appropriate to the intended purpose. Bias must be examined and mitigated.
- **Article 11 — Technical documentation:** Annex IV technical file before market placement. The file documents the system's purpose, design choices, data, performance, and risk management.
- **Article 12 — Record-keeping:** Automatic logging of events sufficient to ensure traceability.
- **Article 13 — Transparency:** Information to deployers on capabilities, limitations, and the meaning of outputs.
- **Article 14 — Human oversight:** Effective human oversight measures built into the system.
- **Article 15 — Accuracy, robustness, cybersecurity:** Appropriate levels declared and demonstrated.

The deployer (Article 26) must use the system per instructions, monitor, and keep human oversight records.

## The penalties

| Violation | Maximum fine |
|---|---|
| Prohibited practices (Article 5) | €35M or 7% of worldwide annual turnover |
| Other obligations (Articles 9-15, 26) | €15M or 3% of worldwide annual turnover |
| Incorrect/incomplete information to authorities | €7.5M or 1% of worldwide annual turnover |
| SMEs: the lower of the two amounts |  |

The penalty is whichever is higher: a fixed amount or a percentage of worldwide turnover. For a global enterprise at €1B turnover, that's €30M for an Article 9-15 violation.

## The conformity assessment

Before market placement, the provider must complete a conformity assessment. The route depends on the system:

- **Internal control (Annex VI):** Most high-risk systems with no biometric identification, no critical infrastructure, and no fundamental rights implications.
- **Notified body (Annex VII):** Biometric identification, critical infrastructure, education/employment scoring, essential services scoring, law enforcement profiling, migration/border profiling, justice profiling.

A notified body is a third-party accredited by an EU Member State. The provider submits the technical documentation; the notified body reviews and certifies. The CE mark is then affixed.

## The post-market monitoring

After market placement, the provider must:

- Establish a post-market monitoring system proportionate to the nature of the system
- Report serious incidents to the market surveillance authorities of the Member States where the incident occurred
- Cooperate with authorities on corrective actions
- Update the technical documentation and risk management throughout the lifecycle

For deployers: keep logs of the system's operation for at least 6 months (or longer if the sectoral law requires).

## The annual review clause

Article 7(1) allows the Commission to add new use cases to Annex III or modify existing ones if the AI systems pose a risk equivalent to or greater than those already listed. Article 112(1) requires annual review of Annex III and the prohibited practices in Article 5 until the end of the delegation period in Article 97. The next Commission assessment is due in 2026.

A team that has classified its AI as "not high-risk" today must reassess every year as the list evolves.

## Verification

The tell that Annex III classification is working:

- Every AI system in the organization has a documented classification against Annex III, signed by legal and product
- High-risk systems have a conformity assessment, an Annex IV technical file, a CE mark, and a post-market monitoring plan
- The deployer logs are kept for at least 6 months
- The classification is reviewed annually against the updated Annex III list
- A team member can name the Annex III category for any AI system in the organization

The tell it isn't:

- A team "thinks" their AI is high-risk but cannot name the category
- A CV-screening tool is in production without a conformity assessment
- The deployer does not log human oversight actions
- The classification has not been reviewed since 2024

## Gotchas

- **Annex III is use-case, not architecture.** A general-purpose LLM is high-risk in employment screening, not high-risk in marketing copy.
- **Article 6(3) derogation is narrow.** "Detects patterns with human review" is excluded; "automatically decides" is not.
- **The compliance deadline depends on the path.** December 2, 2027 for standalone Annex III; August 2, 2028 for Annex I product-safety.
- **Notified body is required for biometric identification, critical infrastructure, and several other categories.** Most teams need internal control, not third-party.
- **The penalty is the higher of the two amounts.** €15M or 3% of worldwide turnover — whichever is more.
- **The Annex III list is reviewed annually.** A "not high-risk" classification today may be high-risk in 2027.

## Related

- `compliance/eu-ai-act-code-of-practice-2026.md` — full Act structure
- `issues/nist-ai-rmf-genai-profile-2026.md` — US-side voluntary framework
- `issues/iso-iec-42001-aims-2026.md` — management system standard
- `lessons/ai-bias-fairness-2026.md` — Article 10 bias obligations

## Source URLs (verified 2026-08-10)

- https://artificialintelligenceact.eu/annex/3/
- https://www.aipolicydesk.com/blog/eu-ai-act-annex-iii-high-risk-ai-systems-2026
- https://www.europarl.europa.eu/RegData/docs_autres_institutions/commission_europeenne/com/2026/0234/COM_COM(2026)0234_EN.pdf
- https://www.deepinspect.ai/blog/eu-ai-act-annex-iii
- https://www.closeit.co/eu-ai-act/article-6-high-risk-classification/
