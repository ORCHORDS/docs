# AI in Hiring — Employment Regulation and AEDT Compliance

**Date:** 2026-08-16
**Author:** the platform team
**Status:** published

## Symptom

Your organization uses AI tools — resume screeners, video interview
analyzers, chatbot pre-screeners, or scoring algorithms — in hiring or
promotion decisions. You have no bias audit, no candidate notification
process, and no documentation of how the AI tool affects employment
outcomes. Regulators at city, state, and EU level are actively enforcing
AI employment laws with escalating penalties.

## Context

Automated Employment Decision Tools (AEDTs) are computational processes
derived from machine learning, statistical modeling, or AI that produce
scores, classifications, or recommendations used to substantially assist
or replace discretionary decision-making in employment. By 2026, a
patchwork of city, state, federal, and international regulations governs
their use, with no unified US federal law.

## Regulatory landscape (August 2026)

### NYC Local Law 144 (in effect since July 2023)

The pioneering AEDT regulation. Requirements:

- **Annual independent bias audit** — must be conducted by an independent
  auditor before using an AEDT, and annually thereafter. The audit
  examines disparate impact across race/ethnicity and sex categories.
- **Public posting** — audit summary and AEDT usage notice must be posted
  on the employer's website.
- **Candidate notification** — candidates and employees must be notified
  at least 10 business days before an AEDT is used in their evaluation.
- **Alternative process** — employers must offer an alternative selection
  process if requested by the candidate.

### US state laws (emerging patchwork)

States are adopting varying approaches:

| Approach | States | Key requirement |
|---|---|---|
| Bias audit model | NYC (city), Colorado (proposed) | Independent audit + public disclosure |
| Disclosure + human review | Illinois (AIPA), Maryland | Notify candidates + human oversight option |
| Privacy-focused | California (CPRA), Virginia | Right to opt out of automated profiling |
| Comprehensive AI governance | Connecticut, Vermont | Impact assessments + transparency reports |

### EU AI Act (high-risk classification)

The EU AI Act classifies AI systems used in "employment, workers management
and access to self-employment" as **high-risk** (Annex III, point 4).
Requirements include:

- Conformity assessment before deployment.
- Risk management system throughout the AI lifecycle.
- Data governance requirements for training datasets.
- Technical documentation and logging.
- Human oversight measures.
- Accuracy, robustness, and cybersecurity requirements.
- Registration in the EU AI database.

Obligations apply from August 2026 for high-risk systems.

## Bias audit methodology

A compliant bias audit must:

1. **Analyze selection rates** — calculate the selection rate for each
   demographic category (race/ethnicity, sex, and intersectional groups).
2. **Compute impact ratios** — compare selection rates using the 4/5ths
   (80%) rule as a benchmark. A selection rate for a protected group below
   80% of the highest-rate group indicates potential adverse impact.
3. **Use historical or test data** — audits may use historical employment
   data or test data if historical data is insufficient.
4. **Independent auditor** — the auditor must have no financial interest
   in the AEDT vendor beyond the audit engagement.

## Anti-patterns

- **Vendor reliance without audit** — purchasing an AI hiring tool and
  assuming the vendor's claims of "bias-free" are sufficient. The employer
  bears the legal obligation, not the vendor.
- **One-time audit** — audits must be annual (NYC) or periodic. A launch-
  time audit without ongoing monitoring fails compliance.
- **Using AI to replace human judgment entirely** — most regulations
  require human oversight. Fully automated reject decisions without human
  review create maximum legal exposure.
- **Ignoring intersectional analysis** — auditing only for sex or only for
  race misses intersectional disparate impact (e.g., adverse impact on
  Black women specifically).

## Gotchas

- **Definition of "substantially assist"** — NYC defines AEDTs broadly to
  include tools that "substantially assist" decisions, not just fully
  automated ones. A scoring tool that a recruiter can override may still
  be an AEDT if it meaningfully influences outcomes.
- **Vendor contracts** — ensure vendor contracts require cooperation with
  bias audits, access to model documentation, and indemnification for
  regulatory violations.
- **Multi-jurisdiction compliance** — a company hiring across NYC,
  Illinois, and the EU must comply with all applicable regimes
  simultaneously. Map each tool to each jurisdiction's requirements.
- **Disparate impact vs. disparate treatment** — bias audits measure
  disparate impact (statistical outcomes). Even passing an audit does not
  protect against disparate treatment claims (intentional discrimination).

## Verification

- Bias audits are conducted annually by an independent auditor.
- Audit summaries are publicly posted on the company website.
- Candidate notification is sent 10+ business days before AEDT use.
- Alternative selection processes are documented and available.
- EU AI Act conformity assessment is completed for EU deployments.
- Vendor contracts include audit cooperation and indemnification clauses.
- Human oversight is documented for all AI-assisted hiring decisions.

## Related

- `documentation/categories/compliance/eu-ai-act-article-5-prohibited-practices.md`
- `documentation/categories/issues/ai-watermarking-provenance-c2pa-2026.md`
- `documentation/categories/compliance/gdpr-data-subject-rights.md`

## Source URLs (verified 2026-08-16)

- NYC AEDT Law (Local Law 144) — https://www.nyc.gov/site/dca/about/automated-employment-decision-tools.page
- Akerman 2026 compliance guide — https://www.akerman.com/en/perspectives/hrdef-ai-in-hiring-emerging-legal-developments-and-compliance-guidance-for-2026.html
- UC Law Review — https://uclawreview.org/2026/03/10/current-regulations-on-ai-in-employment-decisions/
- EU AI Act Annex III — https://artificialintelligenceact.eu/annex/3/
