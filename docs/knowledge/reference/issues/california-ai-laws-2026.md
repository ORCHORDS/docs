# california-ai-laws-2026

**Issue:** A US team deploys an AI system to California users. They hear "California passed an AI law" and assume it's SB 1047. SB 1047 was vetoed. The real law is SB 53, effective January 1, 2026. The team spends 3 months preparing for the wrong statute.

**Date:** 2026-08-10
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Symptom

California has 3 active AI laws as of 2026 (SB 53, AB 2013, SB 942) and 1 famous vetoed bill (SB 1047). The compliance posture for each is different. Picking the wrong one wastes a quarter.

## Root cause

California Governor Gavin Newsom signed SB 53 on September 29, 2025; it took effect January 1, 2026. SB 53 is the Transparency in Frontier Artificial Intelligence Act (TFAIA). It is narrower than the vetoed SB 1047 and targets frontier developers above 10^26 operations, with the heaviest duties on "large frontier developers" above $500M annual revenue.

## The 4 California AI bills (3 active, 1 vetoed)

| Bill | Status | Effective | Who it reaches | First action |
|---|---|---|---|---|
| SB 53 (TFAIA) | law | Jan 1, 2026 | Frontier developers training >10^26 ops; heaviest duties >$500M revenue | confirm threshold; if covered, publish framework + transparency report |
| AB 2013 (Training-Data Transparency) | law | Jan 1, 2026 | Any developer offering gen-AI to Californians | publish high-level training-data disclosure |
| SB 942 (California AI Transparency Act) | law | Aug 2, 2026 (per AB 853) | Covered gen-AI providers producing synthetic media | build provenance/watermark disclosure + detection tooling |
| SB 1047 (Frontier AI Safety Act) | vetoed Sept 29, 2024 | n/a | no one | remove from compliance plan |

Most startups are not directly covered by SB 53. They are more likely covered by AB 2013 (training-data transparency) and SB 942 (watermarking).

## SB 53: the Transparency in Frontier AI Act

The 2026 frontier-AI statute.

- **Scope:** "frontier developers" who train a "frontier model" (foundation model using >10^26 integer or floating-point operations)
- **Heavy obligations:** "large frontier developers" with annual gross revenue >$500M
- **Transparency report:** every new frontier model triggers a published report (intended uses, release date, capabilities, limitations, contact mechanism)
- **Frontier AI framework:** large frontier developers must publish a documented framework for catastrophic risk management
- **Critical safety incident reporting:** 15 days to Cal OES (Office of Emergency Services); 24 hours if imminent risk of death or serious physical injury
- **Whistleblower protection:** employees assessing/managing critical safety incidents are protected
- **Penalty:** civil penalty up to $1,000,000 per violation; enforced by California Attorney General
- **Catastrophic risk threshold:** >50 deaths OR >$1 billion in damage

A 10^26 operations threshold is enormous — on the order of the largest models from best-funded labs. Most startups fall below.

## AB 2013: Training-Data Transparency

A separate California law, also effective January 1, 2026, that reaches much further.

- **Scope:** any developer offering a generative-AI system to Californians
- **Requirement:** publish a high-level training-data disclosure (sources, whether personal info was used, whether copyrighted material was used)
- **Who it reaches:** startups, mid-market, large companies — anyone serving California users with gen-AI

This is the one most startups actually need to comply with.

## SB 942: California AI Transparency Act

The watermarking / provenance law.

- **Scope:** covered generative-AI providers producing synthetic media (images, video, audio)
- **Effective:** August 2, 2026 (per AB 853 amendment that pushed the date)
- **Requirement:** manifest + latent disclosures for AI-generated content; detection API
- **Manifest disclosure:** visible label or metadata indicating AI generation
- **Latent disclosure:** invisible watermark in the content

## The compliance decision tree (2026)

1. **Do you train foundation models with >10^26 ops?** If yes, you may be a "frontier developer" under SB 53. Check revenue: if >$500M, you're a "large frontier developer" with framework obligations.
2. **Do you offer a generative-AI system to California users?** If yes, AB 2013 applies. Publish training-data disclosure.
3. **Do you produce synthetic media (image, video, audio)?** If yes, SB 942 applies (effective Aug 2, 2026). Add manifest + latent disclosures.

Most startups hit 2 and 3. Few hit 1.

## The implementation pattern

For AB 2013 (training-data disclosure):
- Add a `/data-disclosure` page to your product docs
- Document training data sources (with vendor attestations if applicable)
- State whether personal information was used
- State whether copyrighted material was used
- Date the disclosure; update when data sources change

For SB 942 (watermarking):
- Add visible labels to AI-generated content ("AI-generated", "Created with [Product]")
- Embed latent watermarks (C2PA Content Credentials, SynthID-Text for text)
- Provide a detection API for downstream platforms

For SB 53 (frontier framework):
- Document catastrophic risk management approach
- Reference international standards (ISO/IEC 42001, NIST AI RMF)
- Publish critical safety incident reporting process
- Set up whistleblower protection policy

## The 4 penalty exposures

| Bill | Penalty | Enforcer |
|---|---|---|
| SB 53 | up to $1M per violation | California Attorney General |
| AB 2013 | civil penalty (specific amount TBD) | California Attorney General |
| SB 942 | civil penalty (specific amount TBD) | California Attorney General |
| SB 1047 | n/a (vetoed) | n/a |

The $1M SB 53 cap is the most concrete. AB 2013 and SB 942 penalties are being clarified through AG regulations.

## The 5 anti-patterns

1. **Building compliance for SB 1047.** It was vetoed. No obligations. Remove from your compliance plan.
2. **Ignoring AB 2013 because "we're small."** It applies to any gen-AI system offered to Californians, regardless of size.
3. **Treating SB 53 as the only California AI law.** It's one of three. The other two reach further.
4. **Single-state compliance.** California's the highest-profile; New York, Colorado, Illinois, Texas have similar laws. Adopt a federal-grade compliance posture.
5. **No documented training-data lineage.** AB 2013 requires it. If you can't produce the lineage, you can't comply.

## The 5 best practices

1. **State AG coordination.** California's AG coordinates with other state AGs on AI enforcement. A multi-state compliance posture is more efficient than per-state work.
2. **ISO/IEC 42001 alignment.** California's framework obligations reference recognized standards. ISO/IEC 42001 (AIMS) is the de facto choice. See `issues/iso-iec-42001-aims-2026.md`.
3. **Documentation discipline.** The 3 laws require published disclosures, frameworks, and policies. Document continuously; don't assemble at audit time.
4. **Critical incident playbook.** Even if SB 53 doesn't apply (you don't train frontier models), the 24h/15d pattern is good practice. Have an incident response playbook.
5. **Third-party verification.** "Third-party evaluator involvement" is mentioned in SB 53 transparency reports. Get a third-party safety audit annually.

## Verification

The tell that California AI compliance is real:

- A training-data disclosure is published (AB 2013)
- A watermarking / provenance system is in place (SB 942, by Aug 2, 2026)
- For frontier developers: a published frontier AI framework + transparency report (SB 53)
- A critical safety incident reporting process exists
- The compliance plan explicitly notes "SB 1047 does not apply"

The tell it isn't:

- The team is preparing for SB 1047 in 2026
- No training-data disclosure page exists
- AI-generated images are unlabeled
- The compliance plan says "we'll figure it out"

## Gotchas

- **Effective dates are different.** SB 53 and AB 2013 are Jan 1, 2026; SB 942 is Aug 2, 2026. Don't lump them.
- **"Frontier developer" is a 10^26 ops threshold.** Most companies are not. Confirm the math.
- **"Large frontier developer" is $500M annual revenue.** This is the threshold for the heaviest obligations. Smaller frontier developers have lighter requirements.
- **AB 2013's exact disclosure format** is being finalized by the California AG. Watch for guidance.
- **The penalty structure is per-violation, not per-year.** Multiple violations can stack to >$1M.

## Related

- `issues/iso-iec-42001-aims-2026.md` — AIMS standard for SB 53 frameworks
- `issues/nist-ai-rmf-genai-profile-2026.md` — NIST RMF for SB 53 framework content
- `issues/eu-ai-act-annex-iii-2026.md` — EU high-risk category overlap
- `issues/ai-bill-of-rights-2026.md` — federal US AI policy

## Source URLs (verified 2026-08-10)

- https://leginfo.legislature.ca.gov/faces/billTextClient.xhtml?bill_id=202520260SB53
- https://www.goodwinlaw.com/en/insights/publications/2025/11/alerts-technology-aiml-california-moves-to-regulate-frontier-ai-with-a-focus-on-catastrophic-risk
- https://www.jonesday.com/en/insights/2025/10/california-enacts-sb-53-setting-new-standards-for-frontier-ai-safety-disclosures
- https://astraea.law/insights/california-frontier-ai-law-sb-53
- https://www.mofo.com/resources/insights/251001-california-enacts-ai-safety-transparency-regulation-tfaia-sb-53
- https://apcp.assembly.ca.gov/system/files/2025-09/sb-53-wiener-apcp-analysis-9.11.pdf
- https://leginfo.legislature.ca.gov/faces/billTextClient.xhtml?bill_id=202320240SB1047 — SB 1047 (vetoed)
- https://oag.ca.gov/ — California Attorney General (enforcement)
