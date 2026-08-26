# us-state-ai-laws-2026-colorado-texas-california

- **Issue**: With no comprehensive US federal AI law, state AI laws came into
  force through 2025-2026. Teams that mapped US *privacy* laws (CCPA etc.)
  still get blindsided by AI-specific statutes: Colorado's comprehensive AI
  Act, Texas TRAIGA, and California's SB 942 / AB 2013 transparency pair.
  These regulate developers AND deployers of AI, with duties that overlap
  but do not match the EU AI Act.
- **Date**: 2026-08-13
- **Repo**: example-org/example-repo
- **Author**: kb-batch-3-compliance
- **Status**: Active; complements
  `us-state-privacy-laws-2026-multi-state-compliance.md` (privacy only).

## The four laws that matter

| Law | Effective | Who it hits | Core duty |
|---|---|---|---|
| **Colorado AI Act (SB 24-205)** | 30 Jun 2026 (delayed from Feb) | Developers + deployers of "high-risk AI" | Reasonable care against algorithmic discrimination; notices; impact assessments; adverse-decision explanations |
| **Texas TRAIGA (HB 149)** | 1 Jan 2026 | Anyone deploying "intentionally harmful / deceptive" AI in TX | No AI developed/deployed with intent to harm (alarm, harassment, extortion, financial injury); civil penalties up to $100k/violation, $250k if injury/death |
| **California SB 942 (AI Transparency Act)** | 1 Jan 2026 | Generative AI providers with >1M monthly users | Free AI-detection tool + provenance disclosures (latent + visible) for synthetic content |
| **California AB 2013 (Training Data Transparency)** | 1 Jan 2026 | Developers of generative AI made available in CA | Public documentation of training datasets before release |

## Symptom

- An HR SaaS ships résumé ranking to Colorado customers in Q1 2026 assuming
  "Texas rules apply, we're based in Austin." Colorado duties attach to use
  affecting Colorado residents — the effective date passed while the roadmap
  pointed at the EU AI Act only.
- A generative-AI product crosses 1M monthly users mid-2026 and nobody
  notices that SB 942's detection-tool and watermarking duties switched on
  with the metric, not with a launch date.
- A vendor ships a model trained on scraped datasets with no public
  documentation — instant AB 2013 exposure the moment a California user can
  access it.
- An "edgy" consumer agent is marketed as able to pressure people into
  paying invoices; under TRAIGA intent-to-harass design is a felony-adjacent
  violation with AG-only enforcement and no small-claims mercy.

## Gotchas

- **"High-risk" under Colorado ≠ Annex III under the EU.** Overlapping but
  distinct lists (education enrollment, employment, financial/lending,
  housing, insurance, healthcare, legal services). Map per-jurisdiction.
- **Colorado has NO private right of action** — AG (and DAs) enforce,
  $20k per violation; but plaintiffs' lawyers reach the same facts via
  state anti-discrimination statutes, so the shield is thinner than it looks.
- **Deployer duties are affirmative**: conspicuous notice to consumers that
  they're interacting with AI (before or during), explanation of the
  principal reasons for adverse decisions, a human-appeal channel, annual
  impact assessments, and published deployment policy. "The vendor handles
  it" fails — Colorado assigns duties to both sides.
- **Texas TRAIGA is conduct-based, not risk-tier based.** You can't
  classify your way out: if the product is *designed* to intimidate or
  deceive, penalties attach. Marketing copy and design docs are evidence.
- **SB 942 thresholds are user-count based** — instrument monthly active
  user counts so compliance triggers fire automatically. The detection tool
  must accept content and return provenance assessment, keyed to latent
  disclosures (C2PA-style manifests are the practical answer).
- **AB 2013 requires pre-release publication**, covering data sources,
  whether datasets include copyrighted/personal/synthetic data, and the
  extent of curation/filtering. Models "released before 2026" are exempt —
  but materially updated releases are treated as new.
- **Watch the also-rans**: Illinois HB 3773 (employment AI + bias audits),
  Utah (disclosure on request; mental-health chatbot restrictions), NYC
  LL 144 (hiring tools). Multi-state maps rot fast; re-check quarterly.
- **California's CPPA rulemaking** on automated decision-making and risk
  assessments keeps moving under CCPA — an AI feature can be compliant with
  SB 942 and still violate CPPA ADMT rules. See the privacy file for that
  layer.

## Practical example — 50-state AI feature gate

```text
BEFORE enabling an AI feature in a US state:
  1. CLASSIFY the feature
     consequential decision? -> Colorado track (notice, assessments,
       explanation, appeal) + Illinois/NYC if employment
     generative media?        -> SB 942 track (detection tool,
       provenance manifests) once >1M MAU
     new/updated model?       -> AB 2013 training-data doc page
     persuasive/pressure UX?  -> TRAIGA review: kill or redesign
  2. EVIDENCE
     - algorithmic discrimination testing (Colorado: "reasonable care")
     - impact assessment template, stored 3y, dated
     - published AI-use notice + deployment policy URL
     - MAU dashboard with alert at 800k (lead time for SB 942 build)
     - training-data documentation published pre-release
  3. CALENDAR
     - 30 Jun 2026: Colorado effective
     - quarterly: re-scan enacted-but-pending state AI bills
```

Cross-reference `eu-ai-act-annex-iii-high-risk-systems-2026.md` — one impact
assessment can often satisfy Colorado + EU if drafted to cover both schemas
explicitly.
