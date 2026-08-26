# eu-ai-act-article-50-deepfakes-2026

**Issue:** A team ships a generative-AI image or video product in the EU. The product creates photorealistic portraits of real-looking people, AI-edited news clips, and AI-generated text articles on public-interest topics. The team reads EU AI Act Article 50. The team must implement deepfake disclosure, machine-readable marking, and text-publication labeling by August 2, 2026 (Article 50(2) transitional relief extends to December 2, 2026 for systems already on market).

**Date:** 2026-08-10
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Symptom

EU AI Act Article 50 imposes four transparency obligations from August 2, 2026, and the deepfake rule (Article 50(4)) is the most disputed. The Commission's draft guidelines (published 8 May 2026) clarify that the deepfake label is required even without intent to deceive and even when the depicted person is fictional but realistic. Article 50(2) machine-readable marking has a transitional deadline of December 2, 2026 for systems on the market before August 2, 2026.

## Root cause

The EU Code of Practice on Transparency of AI-generated Content (Section 2: Deployers) operationalizes Article 50(4). It defines deepfake as AI-generated/manipulated image, audio, or video content that resembles existing persons, objects, places, entities, or events and would falsely appear authentic. The draft guidelines (May 8, 2026) confirm clearly fantastical content (dragons, flying humans) falls outside, but realistic synthetic depictions of fictitious natural-looking people are in scope.

## The 4 Article 50 obligations

| # | Applies to | Trigger | Disclosure required |
|---|---|---|---|
| 50(1) | Providers | AI system intended to interact directly with people | Users informed they are interacting with AI, at first interaction |
| 50(2) | Providers (incl. GPAI) | System generates synthetic audio/image/video/text | Outputs marked in machine-readable format, detectable as AI-generated |
| 50(3) | Deployers | Emotion recognition or biometric categorisation | Exposed individuals informed |
| 50(4) | Deployers | Deepfakes, AI text on public-interest matters | Content disclosed as AI-generated/manipulated |

All four apply cumulatively. AI agents fall within 50(1) per draft guidelines. Notice must be at first interaction/exposure, clear, distinguishable, and accessibility-compliant.

## The 5 deepfake rule mechanics

The 4 mechanics from the May 8, 2026 draft guidelines.

1. **No-intent-to-deceive rule.** Labeling required even where the deployer had no fraudulent intent. Assessment of whether content "falsely appears authentic" is objective, not subjective.
2. **Fictional-but-realistic is in scope.** A realistic synthetic depiction of a fictitious but natural-looking person constitutes a deepfake under Article 3(60), even where no identifiable rights-holder is implicated.
3. **Fantastical carve-out.** Clearly unrealistic content (dragons, humans flying unaided, elephants driving cars) generally falls outside the deepfake definition.
4. **Artistic carve-out (reduced obligation).** Where deepfake content forms part of an artistic, creative, satirical, fictional, or analogous work, the disclosure is limited to disclosing existence "in an appropriate manner that does not hamper display or enjoyment" (e.g., opening disclaimer for video, audible warning for audio).
5. **Law-enforcement carve-out (full exemption).** Use authorised by law to detect, prevent, investigate, or prosecute criminal offences is exempt from 50(4) entirely.

## The 3 disclosure modalities

The 2026 default stack for deepfake disclosure.

1. **Persistent visual labels.** Burned-in watermark, corner badge, or in-frame text that survives screenshot and re-encoding.
2. **Opening disclaimers for video.** On-screen text or audio overlay at the start of the clip indicating AI origin.
3. **Audible warnings for audio.** Spoken disclosure or beep-tone alert at the start of audio content.

For artistic contexts, the modality may be reduced but disclosure cannot be omitted entirely.

## The 4 Article 50(4) text-publication rules

When AI generates text published to inform the public on matters of public interest.

1. **Trigger is purpose-based.** The publisher's purpose of informing the public is what triggers, not the subject matter itself.
2. **Carve-out requires substantive editorial review.** A cursory sign-off or spell-check is not sufficient. Review must be substantive, by a person with relevant expertise.
3. **Editorial responsibility must be attributable.** A named natural or legal person must hold editorial responsibility, with public contact details and authority to approve/amend/reject.
4. **No private right of action for the carve-out.** The substantive review and editorial responsibility are obligations on the publisher, enforced by national market surveillance authorities (per Member State) and the AI Office (for systems under its supervision).

## The 5 implementation steps

1. Map all AI systems and identify those in scope of Article 50 (interactive, generative, biometric, deepfake-capable, public-interest text).
2. For each, design the disclosure modality: 50(1) inline chat message, 50(2) C2PA-style provenance + SynthID-Text/C2PA watermark, 50(3) pre-exposure notice, 50(4) deepfake label.
3. Build the machine-readable marking pipeline (C2PA manifests, watermarks) into the inference path. Article 50(2) effective August 2, 2026; transitional relief for pre-August-2 systems to December 2, 2026.
4. Update editorial workflows: AI-generated text published on public-interest matters must go through a named-editor substantive review with logged accountability.
5. Monitor the Code of Practice and Commission guidelines (final expected June 2026); align with the EU standardised label (in development).

## The 5 anti-patterns

1. **Burying the AI label in fine print.** Article 50(5) requires clear and distinguishable notice at first interaction, not buried in terms-of-service.
2. **Treating C2PA as optional.** The Code of Practice treats C2PA as the reference machine-readable format; non-C2PA approaches must demonstrate equivalent adequacy.
3. **Skipping disclosure for "obviously synthetic" content.** "Obviously AI" is not a legal exemption; the obligation is to disclose regardless of obviousness.
4. **Relying on cursory human sign-off for the 50(4) carve-out.** Spell-check, grammar correction, or single-clicker approval fails the substantive-review test.
5. **Treating deepfake as a creator-only obligation.** Deployers (often publishers, platforms, marketing teams) are liable, not just the model provider.

## Verification

The tell that Article 50(4) compliance is real:

- Every deepfake-capable output has a persistent, machine-readable, human-visible AI-origin label
- AI text on public-interest matters is either labeled or has a logged substantive-editor review with named accountability
- Pre-August-2 systems have a December 2, 2026 transition plan documented
- The team can name which Article 50 paragraph applies to each output type
- The Code of Practice is referenced in the AI governance policy

The tell it isn't:

- "We just add a watermark at upload"
- No editorial review trail for public-interest text
- No machine-readable provenance; only human-visible labels
- The team treats C2PA as "for images only" or "forensic only"
- "We'll figure it out when the Commission finalises the label"

## Gotchas

- **Article 50(2) is for providers including GPAI.** If you fine-tune or otherwise produce a generative system, the marking obligation is yours, not the upstream foundation model's.
- **The 50(4) text rule has no content-type limit.** It applies to news, blog posts, op-eds, social media posts informing the public; the trigger is the publisher's purpose.
- **Member State national authorities enforce 50(1), 50(3), 50(4).** The AI Office enforces 50(2) for systems under its supervision. Penalties are Member-State-defined; many align with the AI Act's general 15M EUR or 3% global turnover cap.
- **Deepfake in audio counts.** Voice cloning of a real-sounding person (even fictional but realistic) is in scope under 50(4).
- **The artistic carve-out is not a full exemption.** Disclosure is required, just "in an appropriate manner that does not hamper display or enjoyment" (e.g., opening credits, not burned-in label).

## Related

- `issues/eu-ai-act-article-50-2026.md` - the umbrella Article 50 entry
- `issues/eu-ai-act-ai-sandbox-2026.md` - regulatory sandbox for Article 50 experimentation
- `issues/ai-system-cards-2026.md` - system cards required under Article 13
- `issues/eu-ai-act-gpai-2026.md` - GPAI obligations overlapping 50(2)
- `lessons/ai-watermarking-2026.md` - SynthID-Text, C2PA, and detection methods

## Source URLs (verified 2026-08-10)

- https://digital-strategy.ec.europa.eu/en/policies/code-practice-ai-generated-content
- https://artificialintelligenceact.eu/article/50/
- https://artificialintelligenceact.eu/transparency-rules-article-50/
- https://digital-strategy.ec.europa.eu/en/policies/guidelines-ai-transparency-obligations
- https://www.gtlaw.com/-/media/files/insights/alerts/2026/06/gt-alert_deepfakes-chatbots-ai-generated-text-eu-commission-details-transparency-obligations-under-the-ai-act.pdf
