# uk-ai-policy-2026

**Issue:** A US AI company launches a chatbot in the UK. The team checks the EU AI Act compliance. The team assumes the UK follows the EU. The team misses the UK AI Bill, the AISI evaluation program, and the Algorithmic Transparency Recording Standard. Different rules apply.

**Date:** 2026-08-10
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Symptom

The UK takes a "pro-innovation, sectoral" approach to AI regulation — different from the EU's horizontal AI Act. The 2026 framework is principles-based via 5 regulators, not a single law.

## Root cause

The UK government published a 2023 white paper "A pro-innovation approach to AI regulation" and has not enacted a horizontal AI Act. Instead, 5 sectoral regulators enforce existing laws + new guidance.

## The 5 regulator + principle model

The UK government assigned 5 existing regulators to apply 5 cross-sectoral principles to AI in their domain.

| Regulator | Domain | Key principles applied |
|---|---|---|
| ICO (Information Commissioner's Office) | data protection, privacy | data protection, transparency, accountability |
| CMA (Competition and Markets Authority) | competition, consumer protection | fairness, contestability, transparency |
| FCA (Financial Conduct Authority) | financial services | consumer protection, model risk management |
| MHRA (Medicines and Healthcare products Regulatory Agency) | medical devices, AI as medical device | safety, efficacy, post-market surveillance |
| Ofcom | online safety, communications | illegal content, child safety |

Each regulator issues AI-specific guidance for its sector. The 5 principles (safety, security, transparency, explainability, contestability) are applied by each regulator within its existing legal mandate.

## The AISI (AI Safety Institute)

The UK established the AI Safety Institute in November 2023 as the world's first government-backed AI safety body. The 2026 functions.

- **Pre-deployment evaluation** of frontier AI models (voluntary)
- **Safety case review** for models from OpenAI, Anthropic, Google DeepMind, Meta
- **Joint evaluations** with US AISI (established November 2023)
- **International coordination** with EU AI Office, Japan AISI, Singapore AI Verify
- **Research publications** on safety evaluation methodologies

AISI is not a regulator; it provides voluntary evaluation. The 5 regulators retain enforcement authority.

## The 2025-2026 UK AI policy developments

| Date | Event |
|---|---|
| August 2024 | AI Bill introduced in Parliament |
| 2024-2025 | AI Bill consultations and revisions |
| 2025 | UK AI Opportunities Action Plan published |
| 2026 | AI Bill (revised) progressing through Parliament; expected to pass 2026-2027 |

The UK AI Bill (as of mid-2026) focuses on:
- Frontier AI safety evaluation (codifying AISI)
- Transparency obligations for general-purpose AI providers
- Anti-discrimination safeguards
- Copyright and training data transparency
- Voluntary vs mandatory safety evaluation

The Bill is narrower than the EU AI Act, focused on frontier models and transparency.

## The Algorithmic Transparency Recording Standard (ATRS)

For public sector AI deployment, the UK government requires transparency records.

- **Scope:** central government, arm's-length bodies, local authorities using algorithmic tools in decision-making
- **Format:** standard template with 5 sections (owner, description, rationale, data, risk)
- **Publication:** published on algotransparency.gov.uk (a public register)
- **Effective:** mandatory for new deployments since 2024

The ATRS is the UK version of public sector AI transparency. It doesn't apply to private sector but signals UK policy direction.

## The UK GDPR + DPA 2018

Data protection in the UK is governed by the UK GDPR (the retained EU GDPR) + Data Protection Act 2018.

- **Lawful basis for AI training** — UK ICO guidance permits "legitimate interest" with DPIA
- **Automated decision-making** — UK GDPR Article 22 applies (similar to EU); right to human review for solely automated decisions
- **Data subject rights** — access, rectification, erasure, portability all apply
- **Cross-border data transfer** — UK-EU Adequacy Decision (in effect since 2021) facilitates EU-UK data flows; UK-US Data Bridge (2023) for US transfers

The UK retains EU-style data protection in practice. The divergence is gradual.

## The 5 anti-patterns

1. **Assuming UK follows EU AI Act.** The UK is sectoral, not horizontal. The framework is different.
2. **No AISI engagement for frontier models.** Voluntary but signals good faith; the 2026 AI Bill may make it mandatory.
3. **Missing ATRS for public sector deployments.** Mandatory for central government since 2024.
4. **No data protection impact assessment (DPIA) for AI training.** UK ICO requires DPIA; "legitimate interest" without DPIA is non-compliant.
5. **No UK data residency planning.** UK adequacy decisions facilitate EU-UK data flow; UK-US Data Bridge helps with US transfers. Plan for cross-border.

## The 4-step UK compliance pattern

For a US/EU AI company launching in the UK.

1. **Regulator mapping** — identify which of the 5 regulators applies (data protection = ICO; consumer-facing = CMA; etc.)
2. **DPIA for training data** — UK ICO requires DPIA for high-risk AI training
3. **ATRS for public sector** — if selling to UK government, prepare ATRS documents
4. **AISI voluntary evaluation** — for frontier models, engage AISI for pre-deployment evaluation

The 4 steps are not redundant. Different regulators, different obligations.

## The 2026 UK AI Bill structure (draft)

| Title | Function | Mandatory? |
|---|---|---|
| AI Safety Institute (statutory) | codify AISI as statutory body | yes |
| Frontier AI safety obligations | pre-deployment evaluation for >10^25 FLOP | yes (for covered models) |
| GPAI provider transparency | publish training data summary, safety measures | yes (for covered providers) |
| Anti-discrimination in AI | ICO + EHRC enforcement on AI-driven discrimination | yes |
| Copyright + AI | TDM exception with opt-out for text-and-data mining | yes (if data is in copyright) |
| AI sandboxes | DSIT / regulator AI regulatory sandboxes | voluntary |

The Bill is sectoral: AISI for frontier, transparency for GPAI, discrimination via ICO, copyright via existing laws. No horizontal risk-classification like the EU AI Act.

## The training data copyright rule

The UK allows text-and-data mining (TDM) under the Copyright, Designs and Patents Act 1988, with a rightsholder opt-out.

- **Commercial TDM** — permitted unless rightsholder has reserved the right
- **Opt-out mechanism** — machine-readable (e.g., robots.txt, TDMRep) or contractual
- **Enforcement** — copyright infringement if opt-out is ignored
- **Effective** — applies since 2014; reinforced by 2024 ICO guidance

The UK is more permissive than the EU (which has Article 4 opt-out) and the US (litigation-driven). For training data, the UK is one of the easier jurisdictions.

## Verification

The tell that UK AI compliance is real:

- The 5 regulators are mapped per product domain
- A DPIA is on file for AI training
- ATRS documents exist for any public sector deployment
- AISI engagement is planned for frontier models
- The 2026 AI Bill is tracked for changes

The tell it isn't:

- "UK is the same as EU" is the assumption
- No DPIA for training
- No ATRS for public sector
- The team has not heard of AISI
- The 5 regulators are not named

## Gotchas

- **The 2026 AI Bill is in flux.** The final scope may differ from the current draft. Track.
- **AISI is voluntary but politically expected.** Refusing AISI evaluation is a reputational risk.
- **UK GDPR ≠ EU GDPR.** Post-Brexit, the UK GDPR has its own guidance, supervisory authority (ICO), and adequacy decisions. Plan for both.
- **Sectoral regulators are catching up.** The FCA's AI guidance is newer than the ICO's. Different industries have different maturity.
- **The UK may diverge further.** Watch for the 2026 AI Bill's final scope; it could pull UK closer to or further from the EU.

## Related

- `issues/eu-ai-act-annex-iii-2026.md` — EU high-risk (overlap with UK sectoral)
- `issues/eu-ai-act-ai-sandbox-2026.md` — EU sandbox vs UK sandbox
- `issues/ai-bill-of-rights-2026.md` — US AI Bill of Rights (different again)
- `issues/ai-procurement-2026.md` — US federal procurement (different jurisdiction)

## Source URLs (verified 2026-08-10)

- https://www.gov.uk/government/publications/ai-regulation-a-pro-innovation-approach
- https://www.aisi.gov.uk/ — UK AI Safety Institute
- https://ico.org.uk/for-organisations/uk-gdpr-guidance-and-resources/artificial-intelligence/ — ICO AI guidance
- https://www.gov.uk/government/collections/algorithmic-transparency-records
- https://bills.parliament.uk/bills/3554 — UK AI Bill (as introduced)
- https://www.gov.uk/government/publications/ai-opportunities-action-plan
- https://www.gov.uk/government/publications/copyright-and-artificial-intelligence — UK copyright + AI
- https://www.gov.uk/government/publications/ai-bill-2024-25-factsheet
