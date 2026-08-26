# eu-ai-act-gpai-2026

**Issue:** A team deploys a general-purpose AI (GPAI) model via API. The team checks the EU AI Act for "high-risk" obligations. The team doesn't realize the GPAI obligations apply separately and are due August 2025.

**Date:** 2026-08-10
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Symptom

The EU AI Act has 3 layers of obligations: prohibited (Article 5), high-risk (Annex III), and GPAI (Articles 51-55). GPAI obligations apply to any general-purpose AI provider, not just high-risk. The deadlines are phased through 2025-2027.

## Root cause

GPAI obligations are Article 51 (transparency) and Article 53 (training data summary). Article 55 adds obligations for "systemic risk" GPAI. The dates differ: Article 51 was effective August 2, 2025; Article 55 is August 2, 2027.

## The 5 GPAI obligations (Article 51)

For any general-purpose AI model provider, Article 51 requires 5 things.

1. **Technical documentation** — model architecture, training process, capabilities, limitations
2. **Downstream provider documentation** — information to help downstream providers comply
3. **Copyright compliance policy** — comply with EU copyright law, including opt-out (Article 4(3) of the Copyright Directive)
4. **Public training data summary** — a "sufficiently detailed" public summary of training data
5. **Cooperation with authorities** — provide documentation on request

The 5 obligations apply to all GPAI providers, including those offering models via API.

## The 4 systemic-risk obligations (Article 55)

For GPAI models with "systemic risk" (defined as >10^25 FLOP training compute), Article 55 adds 4 things.

1. **State-of-the-art evaluations** — model evaluation, including adversarial testing
2. **Systemic risk assessment** — assess and document risks at the Union level
3. **Serious incident reporting** — report to AI Office within 15 days
4. **Cybersecurity protection** — protect model weights, infrastructure, training pipeline

The 4 obligations apply on top of Article 51, with stronger documentation and reporting.

## The 5 effective dates

| Date | Effective | Applies to |
|---|---|---|
| August 2, 2025 | GPAI Article 51, 53 | new GPAI models placed on the market |
| August 2, 2026 | Prohibited (Article 5), AI literacy | all AI providers |
| August 2, 2027 | High-risk (Annex III), Article 55 | systemic risk GPAI |

The 2026 production default: comply with Article 51 + 53 now; Article 55 by August 2027.

## The 3 categories of GPAI

| Category | Training compute | Obligations |
|---|---|---|
| GPAI (general) | any | Article 51 (transparency) + 53 (training data summary) |
| GPAI with systemic risk | >10^25 FLOP | Article 51 + 53 + 55 (state-of-the-art eval, risk assessment, incident reporting, cybersecurity) |
| GPAI released before Aug 2, 2025 | grandfathered | obligations if substantially modified after that date |

The 3 categories determine the obligation set.

## The training data summary (Article 53)

Article 53 requires a "sufficiently detailed" summary of training data, made publicly available.

- **What to include:** data sources, data types, data volumes, curation methods, known limitations
- **Format:** the AI Office provides a template; the summary is public
- **Updated when:** the data changes substantially
- **The template:** "Template for the public summary of training data" issued by the AI Office

The 2026 default: publish the summary before the model is placed on the market.

## The 3 copyright compliance requirements

Article 53(1)(c) requires 3 things for copyright compliance.

1. **Comply with EU copyright law** — including the TDM (text-and-data mining) opt-out
2. **Implement a copyright policy** — document the policy, the opt-out mechanism, the complaint process
3. **Provide opt-out mechanism** — for TDM rights holders who do not want their content used

The 3 requirements are operational, not theoretical. The opt-out mechanism must be technically implementable (e.g., robots.txt for web scraping, or a structured API for dataset requests).

## The 5-step compliance pattern

1. **Determine if you're a GPAI provider.** If you train and place a general-purpose model on the market, yes.
2. **Calculate training compute.** Below 10^25 FLOP → Article 51 only. Above → + Article 55.
3. **Prepare technical documentation.** Model architecture, training, capabilities, limitations.
4. **Prepare downstream documentation.** For downstream developers integrating the model.
5. **Publish the training data summary.** Use the AI Office template.

The 5 steps are the 2026 baseline.

## The 4 article 55 obligations in detail

For systemic-risk GPAI (>=10^25 FLOP):

1. **State-of-the-art evaluations** — run before market placement; document the eval methodology, the results, the limitations
2. **Systemic risk assessment and mitigation** — assess risks to the Union; document the assessment
3. **Serious incident reporting** — report incidents to the AI Office within 15 days; the report includes: incident date, description, mitigation, recurrence prevention
4. **Cybersecurity protection** — protect model weights (e.g., access control, signing, sandboxing), training infrastructure, and the training pipeline

The 4 obligations align with frontier-model safety practices (Anthropic Responsible Scaling Policy, OpenAI Preparedness Framework, Google DeepMind Frontier Safety Framework).

## The 5 best practices

1. **Use the AI Office templates.** The training data summary template, the technical documentation template, the systemic risk assessment template. The templates are public; the AI Office accepts submissions in the template format.
2. **Document continuously.** The documentation is not assembled at audit; it's generated as the model is trained.
3. **Automate the 15-day incident report.** A serious incident detected in monitoring → automated report generation → AI Office submission.
4. **For open-weight models, document the public release process.** Article 53 covers the model card; the release process is part of "downstream documentation."
5. **Sign model weights.** Cosign / Sigstore signing is the 2026 baseline; see `worktree/sbom-slsa-2026.md`.

## The 5 anti-patterns

1. **"We're an API provider, not a GPAI provider."** The provider of the model is the GPAI provider, regardless of distribution.
2. **"Our model is below 10^25 FLOP, so no systemic risk."** Article 51 + 53 still apply; just not Article 55.
3. **"The training data is proprietary; we can't publish the summary."** The summary is a description, not the data. Publish what data, where from, what volumes; protect the actual data.
4. **"We trained the model in the US; EU AI Act doesn't apply."** The AI Act applies to models placed on the EU market, regardless of where trained.
5. **"Article 55 doesn't apply until 2027; we have time."** Article 51 + 53 are effective since August 2025; no time to wait.

## The 5 cost realities

- **Technical documentation:** 1-2 months of effort for a small team
- **Downstream documentation:** 2-4 weeks
- **Training data summary:** 4-8 weeks (requires data inventory)
- **Systemic risk assessment (Article 55):** 3-6 months (requires risk modeling, evaluation, mitigation)
- **Incident reporting infrastructure:** 1-2 months (process + automation)

The 5 cost areas add up to 6-12 months of work. Plan backward from August 2, 2025 (Article 51) and August 2, 2027 (Article 55).

## The 2026 production stack

For a GPAI provider, the 2026 production stack is:

- **Documentation platform** — a structured template (Notion, Confluence, or custom)
- **Training data inventory** — OpenLineage + MLflow (see `lessons/ai-data-lineage-2026.md`)
- **Incident reporting process** — a runbook for serious incidents; automated where possible
- **Cybersecurity for weights** — model weight signing (cosign), access control, training infrastructure security
- **Public summary** — published on the provider's website

The 5 components are the 2026 baseline.

## The 3 GPAI model release checklist

For each new GPAI model release, 3 things.

1. **Pre-release** — technical documentation complete, training data summary published, downstream documentation available
2. **At-release** — model card published, capabilities/limitations documented, contact for authorities
3. **Post-release** — monitoring for serious incidents, eval against state-of-the-art benchmarks, periodic documentation updates

The 3-step checklist is the per-release discipline.

## The 3 comparison points vs US / UK / China

| Dimension | EU AI Act (Article 51-55) | US (SB 53) | UK (sectoral) | China (CAC) |
|---|---|---|---|---|
| GPAI scope | yes (all GPAI) | frontier (>10^26 ops) | no GPAI-specific | yes (generative AI) |
| Compute threshold | 10^25 FLOP | 10^26 ops | n/a | n/a |
| Training data summary | yes (Article 53) | yes (AB 2013 / SB 53) | voluntary (AISI) | yes (filing) |
| Incident reporting | 15 days (Article 55) | 15 days (SB 53) | n/a | 24h-72h (sectoral) |
| Penalty | 3% global revenue | $1M per violation | n/a | 10% revenue |

The 5 jurisdictions differ; the EU is the most comprehensive. Plan for the strictest.

## Verification

The tell that GPAI compliance is real:

- The GPAI provider status is determined; if yes, Article 51 applies
- Technical documentation is generated continuously, not assembled at audit
- Training data summary is published using the AI Office template
- For >=10^25 FLOP models, Article 55 obligations are on the roadmap
- Serious incident reporting is automated
- Model weights are signed and protected

The tell it isn't:

- "We're an API; we don't have GPAI obligations" (wrong)
- "The training data is proprietary; no summary" (wrong; summary is description, not data)
- No technical documentation
- No incident reporting process
- No weight signing

## Gotchas

- **"GPAI" includes embedding models and image generation models.** It's not just LLMs.
- **The 10^25 FLOP threshold is per training run.** A 10^25 + 10^25 = 2x10^25 model is above; multiple smaller runs don't matter if combined.
- **Open-weight models still have GPAI obligations.** The provider of the open-weight model is the GPAI provider.
- **Fine-tuning a base model is GPAI only if you place the fine-tuned model on the market.** Internal use is not market placement.
- **The "downstream documentation" obligation is forward-looking.** Document the model's intended uses, known limitations, and integration guidance; downstream developers rely on this.

## Related

- `issues/eu-ai-act-annex-iii-2026.md` — high-risk (Annex III)
- `issues/eu-ai-act-article-5-prohibited-2026.md` — prohibited (Article 5)
- `issues/ai-system-cards-2026.md` — model card template
- `lessons/ai-data-lineage-2026.md` — training data lineage

## Source URLs (verified 2026-08-10)

- https://artificialintelligenceact.eu/the-act/ — EU AI Act full text
- https://artificialintelligenceact.eu/article/51/ — Article 51 GPAI
- https://artificialintelligenceact.eu/article/53/ — Article 53 training data
- https://artificialintelligenceact.eu/article/55/ — Article 55 systemic risk
- https://digital-strategy.ec.europa.eu/en/policies/ai-act — Commission AI Act page
- https://ai-act-service-desk.ec.europa.eu/ — AI Act Service Desk
- https://eur-lex.europa.eu/legal-content/ENG/TXT/?uri=CELEX:32024R1689 — full regulation
- https://oecd.ai/en/wonk/the-eu-ai-act-and-general-purpose-ai — OECD analysis
- https://www.aiactblog.nl/ — AI Act blog
