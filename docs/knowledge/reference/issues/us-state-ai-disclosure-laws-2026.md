# us-state-ai-disclosure-laws-2026

**Issue:** A team ships a generative-AI product used in California, Texas, Illinois, Colorado, and New York. The team must comply with a patchwork of state-level AI disclosure laws: California CAITA (SB 942 + AB 853) effective August 2, 2026, Texas TRAIGA (HB 149) effective January 1, 2026, Colorado AI Act (SB 24-205) effective June 30, 2026, Illinois HB 3773, and Nevada NRS 294A on political synthetic media. The team needs the unified 2026 reference for US state AI disclosure obligations.

**Date:** 2026-08-10
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Symptom

US AI regulation in 2026 is a 50-state patchwork. There is no federal comprehensive AI law. The disclosure-obligation state laws hit the same GenAI providers at different dates with different scopes. California leads on watermarking/provenance; Texas leads on broad governance; Colorado leads on high-risk impact assessments. Compliance is per-state, not per-product.

## Root cause

The 2026 wave of state AI laws followed three state-legislature patterns: (1) California content-transparency stack (AB 2013 training data, SB 53 frontier safety, SB 942 watermarking, AB 853 CAITA), (2) Texas-style omnibus governance (TRAIGA), and (3) Colorado-style high-risk-focused law (SB 24-205). They overlap but use different definitions, different enforcement bodies, and different penalty structures.

## The 7 effective 2026 state AI disclosure laws

| Effective | State | Law | Scope | Penalty |
|---|---|---|---|---|
| 2025-01-01 | CA | AB 2905 AI calling | Auto-dialer AI voice | $500/violation |
| 2025-01-01 | CA | AB 2355 political ads | AI in political ads | $5,000/violation |
| 2026-01-01 | CA | SB 53 (TFAIA) | Frontier >10^26 ops | $1M/violation |
| 2026-01-01 | CA | AB 2013 | GenAI training data transparency | AG enforcement |
| 2026-01-01 | CA | SB 243 | Companion chatbot minors | $1,000/violation private |
| 2026-01-01 | CA | AB 489 | Healthcare AI patient comm | Existing enforcement |
| 2026-01-01 | TX | HB 149 (TRAIGA) | Statewide AI governance | $10K-$200K, no private right |
| 2026-01-01 | IL | HB 3773 | Employment AI | IHRA private action |
| 2026-01-01 | NV | NRS 294A | Political synthetic media | Injunctive |
| 2026-01-01 | MT | MCA Title 30 | AI likeness | Actual damages + profits |
| 2026-05-19 | Federal | TAKE IT DOWN Act | NCII/AI deepfake platform takedown | FTC + criminal |
| 2026-06-30 | CO | SB 24-205 | High-risk AI impact assessments | $20,000/violation |
| 2026-08-02 | CA | SB 942 / CAITA | GenAI watermarking + detection | $5,000/violation/day |
| 2027-01-01 | CA | SB 942 platform | Large platform provenance labeling | $5,000/violation/day |
| 2027-01-01 | CA | CCPA ADMT regs | Automated decision-making | $7,500/violation |
| 2028-01-01 | CA | CAITA capture device | Camera/device latent disclosure | $5,000/violation |

## The 5 California CAITA core obligations

California AI Transparency Act (SB 942 + AB 853 amendments) covers GenAI services with >1M monthly visitors, publicly accessible in California, excluding non-user-generated video games, TV, streaming, movies, interactive experiences.

1. **Manifest disclosure option.** Provider must offer users a way to include a manifest disclosure in any AI-generated image, video, or audio content. The disclosure must clearly identify the content as AI-generated, be permanent or extraordinarily difficult to remove, to the extent technically feasible.
2. **Latent disclosure in all outputs.** Provider must embed a latent disclosure in every AI-generated image, video, and audio output. The disclosure must uniquely identify the content, name the GenAI system and version, and provide the creation/alteration date. Must be durable, consistent with industry standards (C2PA reference), compatible with the provider's detection tool.
3. **Free public AI detection tool.** Provider must make available at no cost, publicly accessible, a tool that determines whether specified content was created or altered by the provider's GenAI system, supports content upload, URL submission, and API. Must output any system provenance data detected.
4. **Licensee clause.** When a provider licenses a GenAI system, contractually require the licensee to maintain latent disclosure. If the provider learns the licensee disabled latent disclosure, revoke the license within 96 hours.
5. **No private right of action.** Enforcement is by California AG and other state actors, civil penalties $5,000 per violation, each day a discrete violation, plus injunctive relief and attorney fees.

## The 5 CAITA staggered effective dates

1. **August 2, 2026.** Provider obligations (manifest, latent, detection tool) operative.
2. **January 1, 2027.** Hosting-platform prohibition: may not knowingly offer GenAI systems lacking CAITA latent disclosure. Large online platform obligations to detect embedded provenance and surface it via UI.
3. **January 1, 2028.** Capture-device manufacturers (cameras, recorders, mobile phones sold in California) must enable CAITA disclosures in captured content by default.
4. **Per-violation-per-day counting.** Each day of non-compliance = separate violation. Penalties can compound quickly for ongoing violations.
5. **No federal pre-emption.** California and other state laws operate independently; compliance with one does not waive another.

## The 5 Texas TRAIGA (HB 149) mechanics

Effective January 1, 2026. Applies to developers and deployers conducting business in Texas.

1. **5 prohibited restricted purposes.** Self-harm encouragement, unlawful discrimination, constitutional rights infringement, CSAM generation, and other enumerated harmful uses.
2. **NIST AI RMF as affirmative defense.** Compliance with NIST AI RMF provides a curable-violation defense.
3. **Two-tier penalty structure.** $10,000-$12,000 for curable violations (if not cured), $80,000-$200,000 for uncurable, plus $2,000-$40,000 per day continuing.
4. **No private right of action.** State enforcement only.
5. **Statewide scope.** Applies to any AI system used in Texas, regardless of where the developer is located.

## The 4 Colorado AI Act (SB 24-205) mechanics

Effective June 30, 2026. Originally February 1, 2026, delayed by SB 25B-004 (signed August 28, 2025). First US comprehensive statute targeting high-risk AI.

1. **High-risk AI definition.** Aligns with NIST AI RMF and EU AI Act concepts; consumer-facing consequential decisions in employment, education, financial services, healthcare, housing, insurance, legal services, government services.
2. **Reasonable care to prevent algorithmic discrimination.** Both developers and deployers must exercise reasonable care.
3. **Impact assessments.** Required for high-risk AI systems, with consumer rights to disclosure and appeal.
4. **$20,000 per violation.** Per-incident civil penalty.

## The 5 cross-state compliance patterns

1. **One-size-fits-none architecture.** The same GenAI feature may need different labels, watermarks, and disclosure copy per state. A 50-state deployment requires per-state configuration.
2. **No federal pre-emption to leverage.** Federal TAKE IT DOWN Act (May 19, 2026) is narrow (NCII/AI deepfake platform takedown) and does not pre-empt state law.
3. **California is the bellwether.** Other states' laws often follow California's enforcement posture. Investing in CA compliance often covers other states' parallel rules.
4. **Colorado is the high-risk benchmark.** If you serve Coloradans with consequential-decision AI (employment, housing, education), assume you need a full impact assessment.
5. **Texas is the omnibus check.** Even if you're not in Texas, the NIST RMF affirmative defense is a low-cost compliance posture that travels well.

## The 5 anti-patterns

1. **Treating SB 942 (CAITA) as opt-in.** The manifest disclosure is an option for users; the latent disclosure is mandatory for the provider. Don't conflate them.
2. **Single-jurisdiction privacy policy.** A "CCPA-compliant" policy does not cover Colorado, Texas, or Nevada AI laws. Each requires its own disclosures.
3. **Ignoring latent disclosure durability.** A removable watermark is not a CAITA-compliant latent disclosure. C2PA manifest with cryptographic binding is the 2026 reference.
4. **Treating "AI-generated" label as obvious from content.** The law requires explicit disclosure regardless of obviousness. Spectators may not know.
5. **Skipping impact assessment for "internal" AI.** Colorado SB 24-205 covers deployers, not just developers. Your internal hiring tool still needs an impact assessment if Coloradans are screened.

## Verification

The tell that US state AI disclosure compliance is real:

- C2PA manifest + SynthID-Text watermark on every GenAI image, audio, video output
- Manifest disclosure toggle visible to users in the GenAI UI
- Free public detection tool reachable from product homepage
- Training data summary published per AB 2013 (California) with sources, counts, copyright status, timeframes
- Per-state impact assessments for Colorado-served consequential decisions
- Texas TRAIGA NIST AI RMF alignment documented as affirmative-defense basis
- Editorial review trail for any AI-generated political ad or public-interest text
- 96-hour license-revocation SLA in license contracts

The tell it isn't:

- "We add a small AI badge in the corner"
- Watermarks that are trivially strippable by re-encoding
- Detection tool gated behind login or paywall
- "We don't operate in California" but serving users with CA IP addresses
- Single impact assessment reused for all states

## Gotchas

- **CA >1M monthly visitor threshold.** CAITA applies to GenAI services with >1M monthly visitors, publicly accessible in California. Mid-size products may be exempt until they cross the threshold.
- **Text content exemption.** CAITA does not apply to AI-generated textual content. AB 2013 (training data transparency) is the parallel text obligation.
- **Effective date differences.** Texas (Jan 1, 2026), Colorado (Jun 30, 2026), California CAITA (Aug 2, 2026). Build the compliance date matrix.
- **No private right of action in CA, TX, CO.** Enforcement is by state actors. Illinois HB 3773 (employment) has a private right of action via IHRA remedies.
- **TAKE IT DOWN Act federal pre-emption narrow.** Federal law covers NCII/AI deepfake platform takedown (48 hours), criminal penalties, FTC enforcement. Does not pre-empt state disclosure laws.
- **NV political advertising applies to candidates.** NRS 294A covers AI in political advertising; not just deepfakes, any substantially AI-generated or altered content.

## Related

- `issues/california-ai-laws-2026.md` - California deep dive (SB 53, AB 2013, SB 942, AB 853)
- `issues/us-federal-ai-procurement-2026.md` - federal-level AI procurement rules
- `issues/uk-ai-policy-2026.md` - UK 5-regulator model
- `issues/canada-ai-policy-2026.md` - Canada Bill C-36 PPCDA
- `issues/eu-ai-act-article-50-2026.md` - EU Article 50 transparency (parallel regime)

## Source URLs (verified 2026-08-10)

- https://www.morganlewis.com/pubs/2026/08/new-california-ai-disclosure-rules-become-operative
- https://ai-law-center.orrick.com/us-ai-law-tracker-see-all-states/
- https://www.bakerbotts.com/thought-leadership/publications/2026/january/us-ai-law-update
- https://natlawreview.com/article/client-alert-new-ai-laws-will-prompt-changes-how-companies-do-business
- https://www.ailawsbystate.com/tools/ai-disclosure-tracker
