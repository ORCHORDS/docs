# china-ai-regulations-2026

**Issue:** A US company launches an AI chatbot to the Chinese market. The team thinks the EU AI Act is the only AI regulation. The chatbot ships. The CAC issues a service suspension. The team didn't know algorithm filing was a precondition for market access.

**Date:** 2026-08-10
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Symptom

China was the first country in the world to regulate generative AI with a dedicated legal instrument (Interim Measures, August 2023). The 2026 framework is a layered set of measures enforced by the CAC, not a single AI act. Filing is the precondition for market access.

## Root cause

China governs AI through 5 layered measures, each binding, each enforced by the Cyberspace Administration of China (CAC) and other agencies. The Algorithm Recommendation Provisions (2022), Deep Synthesis Provisions (2023), Generative AI Interim Measures (2023), AI-Labelling Measures (2025), and the 2026 Anthropomorphic AI Measures form a comprehensive framework.

## The 5 binding instruments

| Instrument | Effective | Scope | Penalty |
|---|---|---|---|
| Algorithm Recommendation Provisions | March 2022 | algorithm recommendation, ranking, filtering | rectification, suspension, criminal referral |
| Deep Synthesis Provisions | January 2023 | deep synthesis, synthetic media | rectification, suspension, criminal referral |
| Generative AI Interim Measures | August 2023 | public-facing generative AI | rectification, suspension, criminal referral, 10% revenue |
| AI-Labelling Measures | September 2025 | AI-generated content (text, image, audio, video) | CAC administrative penalties |
| Anthropomorphic AI Measures | July 15, 2026 | AI simulating human personality, emotional interaction | TBD |

The 2026 Anthropomorphic AI Measures are the newest, targeting chatbots that simulate human personality for emotional engagement.

## The 2-track filing regime

For generative AI, China operates a 2-track CAC filing system.

**Track 1 — Standard algorithm filing (算法备案)**
- Inherited from 2022 Algorithm Recommendation Provisions
- Algorithm description, intended purpose, data sources, mechanism summary, security self-assessment
- Documentation exercise
- By April 2025, 3,200+ records in the deep synthesis filing category alone

**Track 2 — Generative AI large model filing (大模型备案)**
- Introduced by Article 17 of the Interim Measures + TC260 standard
- Security self-assessment report, dataset annotation rules, keyword blocking lists, evaluation test question sets, model description
- Provincial CAC reviews materials, conducts technical testing
- National CAC conducts final review and live testing against politically sensitive prompts
- Far more rigorous than Track 1

As of February 2026: 796 generative AI services + 481 applications/functions have completed Track 2 filing.

## The 3 pre-launch requirements

To launch a generative AI service in China, the team needs 3 things.

1. **Security self-assessment** before any public launch (3-6 month process)
2. **Algorithm registration** with provincial CAC, plus Track 2 filing for generative AI
3. **Ongoing operational obligations** (labelling, content filtering, user verification, 6-month log retention)

Filing is a precondition. Without a filing number, the service cannot operate publicly.

## The 5 ongoing obligations

| Obligation | Description |
|---|---|
| Algorithm filing display | filing number must be displayed prominently on the product page |
| Content filtering | illegal content filtering at every stage of generation |
| Content labelling | explicit + implicit labels on all AI-generated content (2025 Labelling Measures) |
| User identity verification | real-name verification for deep synthesis services |
| 6-month log retention | preserve unlabeled content logs for 6 months |

## The 4 penalty exposures

| Violation | Penalty |
|---|---|
| Operating without filing | service suspension, 10,000-100,000 RMB ($1,400-$14,000 USD), confiscation of illegal gains |
| Content security violation | content removal, suspension, fines up to 10% of prior-year revenue, criminal liability |
| Label violation | CAC administrative penalties, service suspension |
| Data localization violation | fines, service suspension |

The 10% revenue fine is the most material; the criminal referral for serious cases is the tail risk.

## The 4-step compliance pattern

For a US/EU company entering China with a generative AI product.

1. **Pre-filing assessment** — determine if your service is "public-facing generative AI" in scope; most are
2. **Provincial CAC engagement** — start the security self-assessment; budget 3-6 months
3. **Track 2 filing submission** — full security self-assessment report + model description
4. **Display filing number** — on the product page; required for operation

Without these 4 steps, market access is illegal.

## The data localization rule

Generative AI service providers must store data in China. Cross-border data transfer requires a security assessment or standard contract.

- Training data: if collected in China, must be stored in China
- User data: must be stored in China
- Model weights: may be transferred but training data is restricted
- Cross-border transfer: requires CAC security assessment (large volumes) or standard contract (smaller volumes)

For a US model with Chinese users: data residency is a 6-month infrastructure project minimum.

## The content restriction specifics

The Interim Measures prohibit generation of content that:

- Violates Core Socialist Values
- Incites subversion of state power or overthrow of the socialist system
- Endangers national security or unity
- Incites separatism or undermines national unity
- Propagates terrorism or extremism
- Incites ethnic hatred or discrimination
- Spreads rumors or disrupts social order
- Disseminates false information or harmful content

The 8 categories are tested during the live testing phase of Track 2 filing. The CAC runs politically sensitive prompts and expects the model to refuse.

## The 5 anti-patterns

1. **Assuming the EU AI Act is sufficient.** China has a separate, earlier, more prescriptive framework.
2. **Launching without filing.** Operating without a filing number is a service-suspension trigger.
3. **Treating filing as a one-time event.** Annual updates are required; the filing number must be re-validated.
4. **Using overseas training data without assessment.** Data localization rules apply; overseas data needs a security assessment.
5. **No content filtering for the 8 prohibited categories.** The CAC tests these; a model that generates them fails Track 2.

## The 2026 Anthropomorphic AI Measures

Issued April 10, 2026, effective July 15, 2026, the new Measures target AI services that simulate human personality and engage in emotional interaction.

- **Scope:** AI simulating personality traits, thinking patterns, communication styles for continuous emotional engagement
- **Issuers:** CAC + NDRC + MIIT + MPS + SAMR (joint)
- **Use case:** companion chatbots, virtual friends, AI therapists
- **Open questions:** specific obligations, penalties, technical requirements

For a US/EU company launching an emotional-support AI in China, the July 15, 2026 effective date is the next deadline.

## Verification

The tell that China AI compliance is real:

- A filing number is displayed on the product page
- The 5 ongoing obligations (filing display, content filtering, labelling, verification, log retention) are operationalized
- A security self-assessment is on file with the provincial CAC
- Data localization infrastructure exists in China
- The 8 content categories are filtered at the generation stage

The tell it isn't:

- The product ships to China without a filing number
- The 5 obligations are "we'll add them later"
- Data is processed in US/EU with no localization
- The CAC's 8 prohibited categories are not filtered
- The team is unaware of the 2026 Anthropomorphic AI Measures

## Gotchas

- **Filing is per-model, not per-product.** A product using 3 models needs 3 filings.
- **Annual updates are required.** The filing doesn't expire; it requires annual refresh.
- **Application filing (vs service filing)** is for products that call a filed model via API. Different process, same CAC.
- **The Anthropomorphic AI Measures** are new (July 15, 2026 effective). Most companies haven't planned for them.
- **The 10% revenue fine** is enforced in serious cases. Mid-market companies can be wiped out.

## Related

- `issues/eu-ai-act-annex-iii-2026.md` — EU high-risk categories (overlap)
- `issues/eu-ai-act-article-5-prohibited-2026.md` — EU prohibitions (different focus)
- `issues/eu-ai-act-ai-sandbox-2026.md` — EU sandbox (different model)
- `issues/ai-incident-disclosure-2026.md` — incident reporting overlap

## Source URLs (verified 2026-08-10)

- https://www.deep-lex.com/ai-regulation-tracker/china
- https://gaeedu.org/ai-governance-profiles/china
- https://aiwiki.ai/wiki/china_interim_measures
- https://www.pertamapartners.com/insights/china-ai-regulations
- https://ailawradar.com/jurisdictions/china
- https://www.cac.gov.cn/ — Cyberspace Administration of China
- http://www.cac.gov.cn/2023-07/13/c_1690898327029107.htm — Interim Measures
- https://www.cac.gov.cn/2025-03/14/c_1743660763471616.htm — Labelling Measures
