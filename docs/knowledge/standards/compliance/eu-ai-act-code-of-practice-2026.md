# eu-ai-act-code-of-practice-2026

- **Issue**: The EU AI Act's GPAI obligations took effect on 2 August 2025, and the Commission's enforcement actions started 2 August 2026. The General-Purpose AI (GPAI) Code of Practice (published 10 July 2025) is the voluntary path to compliance. If you train or distribute a GPAI model — or fine-tune one above the threshold — you need to know which chapter applies and what the obligations are.
- **Date**: 2026-08-09
- **Repo**: example-org/example-repo
- **Author**: kb-batch-2
- **Status**: Active; complements `documentation/docs/policies/compliance/eu-ai-act.md`.

## Symptom

- You are deploying a fine-tuned LLM in the EU and assume "we're a downstream user, the provider handles compliance." The model was modified; you may now be the provider of a modified GPAI model.
- You are signing the Code without knowing which Chapter applies. Signing the wrong chapter is worse than not signing.
- Your training pipeline doesn't produce the Model Documentation Form data the Transparency chapter requires.
- Your model is above the systemic-risk threshold (10^25 FLOP training compute) and you have not implemented the Safety and Security chapter.

## Root cause

The AI Act has phased obligations. **GPAI model provider obligations took effect 2 August 2025** (Articles 50–55). The Commission's enforcement actions — requests for information, access to models, model recalls — **began 2 August 2026**. For models released before 2 August 2025, the compliance deadline is **2 August 2027**. The Code of Practice is a voluntary tool to bridge the gap between the 2025 obligations and the eventual harmonised European standards.

## The three chapters

| Chapter | Applies to | Voluntary signable by | Key obligations |
|---|---|---|---|
| **Transparency** | All GPAI model providers | All | Model documentation form, downstream information, integrity of documentation (10-year retention) |
| **Copyright** | All GPAI model providers | All | EU copyright law compliance policy; respect `robots.txt`; technical safeguards against reproducing protected content; complaint contact point |
| **Safety and Security** | GPAI with systemic risk (training compute > 10^25 FLOP) | ~5–15 companies worldwide | Safety & Security Framework; risk identification/assessment/mitigation; serious-incident reporting within 2 days for critical infrastructure; record retention 10 years |

The Transparency and Copyright chapters apply to all GPAI providers. Safety and Security applies only to systemic-risk providers (above 10^25 FLOP). xAI signed the Safety and Security chapter but must demonstrate compliance on Transparency and Copyright via alternative means.

## The 12 commitments

- **Transparency chapter**: 1 commitment + 3 measures (documentation, downstream info, integrity)
- **Copyright chapter**: 1 commitment + measures (policy, opt-out mechanisms, safeguards, complaint handling)
- **Safety and Security chapter**: 10 commitments covering risk assessment, mitigation, incident reporting, cybersecurity, safety framework, evaluation triggers, organizational responsibilities

## The 10^25 FLOP threshold

This is the **systemic risk threshold**. Below it, the Safety and Security chapter is not mandatory. Above it, full compliance is required. To put it in perspective: the most advanced frontier models (OpenAI o3, Anthropic Claude 4 Opus, Google Gemini 2.5 Pro) are above this threshold. The current estimate is that 5–15 companies worldwide have models above it.

Fine-tuning a sub-threshold model does not push you over. Training a new model from scratch above the threshold does. The Commission has published guidelines on how the threshold applies to fine-tunes and modifications.

## Critical dates

| Date | Event |
|---|---|
| 1 August 2024 | AI Act entered into force |
| 2 February 2025 | Prohibited AI system provisions in effect |
| **2 August 2025** | **GPAI model provider obligations in effect** (Articles 50–55) |
| 10 July 2025 | Code of Practice final version published |
| **2 August 2026** | **Commission enforcement actions begin** (requests for info, access to models, model recalls) |
| 2 August 2027 | Pre-2025-08-02 models must reach compliance |

New transparency rules also took effect 2 August 2026:
- Chatbots and interactive AI systems must disclose they are AI
- Deepfakes (images, video, audio generated/edited by AI) must be labeled
- AI-generated content must carry machine-readable marks for detection

## The Model Documentation Form

Required by Measure 1.1 of the Transparency chapter. The downloadable DOCX is user-friendly and covers:
- Licensing information
- Technical specifications
- Use cases (intended and known forbidden)
- Datasets (categories, sources, sizes, languages, date ranges)
- Compute and energy usage
- Capabilities and limitations
- Training methodology

Documentation must be **kept current**, reflecting material changes. Must be **stored for at least 10 years** after the model's initial release. Must be available **on request to the AI Office and downstream providers**. Public release is encouraged to promote transparency.

## The Transparency chapter's three measures

1. **Measure 1.1** — draw up and keep up-to-date the model documentation per the Model Documentation Form.
2. **Measure 1.2** — provide relevant information to downstream providers integrating the model, and to the AI Office on request.
3. **Measure 1.3** — ensure the quality, security, and integrity of the documented information.

## The Copyright chapter's requirements

- **Policy to comply with EU copyright law** for all GPAI models placed on the Union market.
- **Respect machine-readable rights signals** like `robots.txt`; avoid sites flagged for copyright infringement.
- **Technical safeguards** to minimize the likelihood of reproducing protected content.
- **Terms of service** must prohibit copyright-infringing uses. For open-source distributions, alert users to the prohibition.
- **Designated contact point** for copyright holders to submit complaints; efficient and fair complaint processes.

## The Safety and Security chapter's commitments (10)

1. **Safety and Security Framework** before model release — evaluation triggers, risk categories, mitigation strategies, forecasting methods, organizational responsibilities.
2. **Risk identification, assessment, and mitigation** throughout the model lifecycle.
3. **Safety measures** integrated throughout the lifecycle: filtering, continuous monitoring, refusal training, phased access controls, downstream tool safeguards, secure deployment environments.
4. **Security controls** to prevent unauthorized access or misuse: strong digital and physical protections.
5. **Serious-incident reporting** — within **2 days for incidents affecting critical infrastructure**. Reports updated regularly, kept for at least 5 years.
6. **Record retention** of safety and risk-management activities for at least **10 years**.
7. **Public summaries** of safety frameworks and model reports when needed to reduce risks, unless the model meets "similarly safe or safer" criteria.
8. **Risk governance framework** — pre-market assessments, ongoing monitoring, continuous oversight.
9. **State-of-the-art model evaluations** before deployment and on material change.
10. **Cybersecurity protection** proportionate to the risks.

## Who can sign

- **All providers** of GPAI models can sign the Transparency and Copyright chapters.
- **Systemic-risk providers** (above 10^25 FLOP) should sign the Safety and Security chapter.
- xAI signed the Safety and Security chapter but must demonstrate compliance on Transparency and Copyright via alternative means.
- Signatory process: complete the Signatory Form, send to `EU-AIOFFICE-CODE-SIGNATURES@ec.europa.eu`.
- The Signatory Taskforce, chaired by the AI Office, facilitates coherent application of the Code.

## Why sign the Code

> "The Commission and the AI Board have confirmed that the code is an adequate voluntary tool for providers of GPAI models to demonstrate compliance with the AI Act. Following the endorsement, AI model providers who voluntarily sign it can show they comply with the AI Act by adhering to the code. This will reduce their administrative burden and give them more legal certainty and trust than if they proved compliance through other methods."

In other words: signing the Code is the path of least resistance. Not signing means proving compliance by other means — likely more burdensome and time-consuming.

## What this means for downstream deployers

If you are **deploying** a GPAI model (not training one), you are typically the **downstream provider of an AI system** (a different category). You are not subject to the GPAI provider obligations directly. However:

- The Transparency chapter requires GPAI providers to give you (downstream) information about capabilities and limitations. **Use that information** in your own risk classification and documentation.
- If you **fine-tune** a sub-threshold model enough to materially change its behavior, the Commission may re-classify you as a GPAI provider. Read the Commission's guidelines.
- You are still subject to the **AI Act's general obligations** (transparency, data quality, human oversight, etc.) if your AI system is high-risk.

## Verification

- **Signatory list** — check that the providers you depend on have signed the Code (and which chapters).
- **Model Documentation Form** — request it from your upstream provider for any GPAI model in production.
- **Downstream information** — verify you received and have on file the capabilities/limitations summary.
- **Risk classification** — re-evaluate your AI system under the AI Act's high-risk categories (Annex III) and the systemic-risk threshold for fine-tunes.
- **Logging** — every interaction with a GPAI model should be logged with the model identifier, version, and a snapshot of the request and response. This is your audit trail.
- **Incident response** — a serious-incident reporting process must be in place, with a 2-day SLA for critical infrastructure incidents.

## Gotchas

- **Signing the wrong chapter is worse than not signing.** Be honest about which applies.
- **The 10^25 FLOP threshold is a training-compute threshold.** Inference compute doesn't count.
- **Fine-tuning can re-classify you as a GPAI provider.** Read the Commission's guidelines.
- **Documentation retention is 10 years** for Transparency, 10 years for safety records, 5 years for incident reports. Plan your storage.
- **Open-source models are exempt from some Article 53 obligations** (the (1)(a) and (b) parts), but copyright compliance still applies.
- **The Commission's enforcement actions started 2 August 2026** — not "sometime soon." Requests for information, model access, and recalls are live.
- **Downstream users are not off the hook.** High-risk AI system obligations still apply.
- **"Reasonable" is not a defense.** The Code is voluntary but specific. Vague commitments are not enough.
- **The Safety and Security chapter is for systemic-risk providers only.** Don't sign it if it doesn't apply; don't fail to sign it if it does.
- **Pre-2025-08-02 models have until 2027-08-02** to comply. Newer models must already comply.

## Related

- `documentation/docs/policies/compliance/eu-ai-act.md` — the broader Act
- `documentation/docs/policies/compliance/iso-42001-ai-management-system-2026.md` — the certifiable management system
- `documentation/docs/policies/compliance/nist-ai-rmf-software-compliance.md` — the US framework
- `documentation/docs/policies/security/ai-agent-security.md` — the technical controls
- `documentation/docs/policies/lessons/scope-discipline.md` — keep compliance concerns out of unrelated PRs

## Source URLs (verified 2026-08-09)

- "The General-Purpose AI Code of Practice" (EU Commission) — https://digital-strategy.ec.europa.eu/en/policies/contents-code-gpai
- "An Introduction to the Code of Practice for General-Purpose AI" (artificialintelligenceact.eu) — https://artificialintelligenceact.eu/introduction-to-code-of-practice/
- "EU AI Act: General-Purpose AI Code of Practice · Final Version" — https://code-of-practice.ai/
- "Overview of the Code of Practice" (artificialintelligenceact.eu) — https://artificialintelligenceact.eu/code-of-practice-overview/
- "Commission starts enforcing AI Act rules and new transparency requirements" — https://digital-strategy.ec.europa.eu/en/news/commission-starts-enforcing-ai-act-rules-and-new-transparency-requirements-2-august
- AI Act full text — https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:32024R1689
