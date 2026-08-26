# ai-bias-fairness-standards-2026

**Issue:** A team ships an AI system used in employment, lending, healthcare, or education. The team reads about NIST AI bias standards, EU AI Act bias provisions, and US state laws (Colorado SB 24-205, NYC Local Law 144, Illinois Human Rights Act AI amendments). The team needs a unified 2026 reference for AI bias and fairness standards.

**Date:** 2026-08-10
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Symptom

AI bias standards in 2026 are a stack: NIST SP 1270 (March 2022, foundational taxonomy), NIST AI 600-1 (GenAI Profile, July 2024), NIST AI 800-3 (statistical evaluation, February 2026), EU AI Act bias provisions, Colorado SB 24-205 algorithmic discrimination, NYC Local Law 144 (AEDT for hiring). Compliance requires layered alignment.

## Root cause

The 2026 default is NIST AI RMF as the framework, NIST SP 1270 + 600-1 as the bias-specific guidance, with jurisdictional overlays (EU AI Act for EU, Colorado for CO, NYC AEDT for hiring). There is no single global standard; teams layer.

## The 5 NIST bias documents

1. **NIST SP 1270 (March 2022).** "Towards a Standard for Identifying and Managing Bias in AI." Three categories: systemic, statistical, human. Three challenge areas: datasets, TEVV, human factors.
2. **NIST AI 600-1 (July 2024).** GenAI Profile. 12 GAI risk categories, 200+ action IDs. Bias-specific: MS-2.11, MS-3.3, MG-2.2-004.
3. **NIST AI 800-3 (February 2026).** Statistical models for AI evaluation. Distinguishes benchmark accuracy from generalized accuracy. Uses generalized linear mixed models.
4. **NIST AI RMF 1.0 (January 2023).** Govern-Map-Measure-Manage. The umbrella framework that 600-1 extends.
5. **NIST AI RMF Generative AI Profile (July 2024).** Companion to 600-1 for cross-referencing.

## The 4 jurisdictional overlays

1. **EU AI Act.** Article 10 (data governance), Article 14 (human oversight), Article 27 (FRIA for high-risk), Recital 27 (fundamental rights). Bias-specific obligations for high-risk AI.
2. **Colorado AI Act (SB 24-205, effective June 30, 2026).** "Algorithmic discrimination" definition; high-risk AI impact assessments; consumer rights to disclosure and appeal; $20,000 per violation.
3. **NYC Local Law 144 (AEDT, effective July 5, 2023).** Bias audits for automated employment decision tools; annual third-party audit; public summary; $500 first violation, $1,500 subsequent.
4. **Illinois Human Rights Act AI amendments (HB 3773, January 1, 2026).** AI use in employment as a "covered decision"; IHRA remedies (private right of action); 30-day notice required.

## The 5 evaluation requirements (cross-jurisdiction)

1. **Bias measurement on representative data.** NIST SP 1270 §3 (datasets), NIST AI 600-1 MS-2.11.
2. **Demographic disparity testing** with statistical confidence (NIST AI 800-3).
3. **Documented impact assessment** for high-risk AI (EU AI Act Article 27, Colorado SB 24-205, NYC AEDT).
4. **Annual third-party audit** for AEDT (NYC) and similar jurisdictions.
5. **Public disclosure of bias audit results** (NYC AEDT, EU AI Act for high-risk systems).

## The 5 implementation steps

1. **Map your AI use case** to risk tier (minimal, limited, high-risk, GPAI systemic).
2. **Identify applicable jurisdictions** (EU presence, CO, NYC, IL, etc.).
3. **Adopt NIST AI RMF** as the framework baseline.
4. **Layer NIST SP 1270 + 600-1** for bias-specific guidance.
5. **Add jurisdictional audits** (NYC AEDT bias audit, Colorado algorithmic discrimination assessment).

## The 5 anti-patterns

1. **Single fairness metric reporting.** Different metrics give different rankings. Report at least 2.
2. **Skipping intersectional analysis.** Single-axis (gender only) misses compound disadvantage.
3. **Using benchmark accuracy as production accuracy.** NIST AI 800-3 distinguishes them; use generalized accuracy.
4. **Audit once and stop.** Bias drifts; continuous monitoring required.
5. **Treating fairness as a final-stage check.** Build it into the data collection, model training, and deployment pipeline.

## The 5 best practices

1. Document benchmark assumptions and training/test contamination.
2. Use NIST Dioptra or similar empirical trustworthy evaluation.
3. Sub-sample production traffic for manual annotation in deployment.
4. Test mitigations on held-out groups.
5. Engage with potentially impacted communities for participatory evaluation.

## Verification

The tell that bias standards compliance is real:

- NIST AI RMF adopted as framework baseline
- At least 2 fairness metrics reported per evaluation
- Held-out evaluation with confidence intervals
- Documented impact assessment for high-risk systems
- Annual third-party audit (if applicable to jurisdiction)
- Continuous monitoring with disparate impact alerts
- Engagement with impacted communities documented

The tell it isn't:

- "We use AI responsibly" without framework
- Single-metric fairness reporting
- Static bias evaluation done once
- "Diverse team reviewed it" without structured measurement
- No jurisdictional overlay for in-scope regions

## Gotchas

- **NIST SP 1270's three bias categories** are conceptual, not directly measurable. Translate to specific metrics per category.
- **NIST AI 800-3** requires >30 samples per group for confidence intervals. Smaller subgroups need Bayesian or bootstrap methods.
- **Mitigations can shift bias.** Gender bias mitigation that introduces age bias is a regression.
- **EU AI Act Article 27 FRIA** is for high-risk deployers, not developers. Different obligations.
- **Colorado "algorithmic discrimination"** is defined as "unlawful differential treatment or impact that disfavors persons based on actual or perceived protected class." Broader than EEOC disparate impact.

## Related

- `issues/nist-ai-rmf-genai-profile-2026.md` - NIST AI 600-1 governance
- `issues/eu-ai-act-article-5-prohibited-2026.md` - EU AI Act prohibited practices
- `lessons/ai-bias-fairness-evaluation-2026.md` - evaluation mechanics
- `issues/california-ai-laws-2026.md` - California parallel rules

## Source URLs (verified 2026-08-10)

- https://nvlpubs.nist.gov/nistpubs/SpecialPublications/NIST.SP.1270.pdf
- https://nvlpubs.nist.gov/nistpubs/ai/NIST.AI.600-1.pdf
- https://nvlpubs.nist.gov/nistpubs/ai/NIST.AI.800-3.pdf
- https://www.nist.gov/itl/ai-risk-management-framework
- https://artificialintelligenceact.eu/
- https://leg.colorado.gov/bills/sb24-205
- https://www.nyc.gov/site/dca/about/automated-employment-decision-tools.page
