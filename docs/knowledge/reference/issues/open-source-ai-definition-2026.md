# open-source-ai-definition-2026

**Issue:** A team wants to release an AI model as "open source." They put the model weights on HuggingFace with an Apache 2.0 license. A regulator asks "is this open source?" The team doesn't know the criteria. The team discovers the Open Source AI Definition requires more than the weights.

**Date:** 2026-08-10
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Symptom

The Open Source Initiative (OSI) released the Open Source AI Definition (OSAID) 1.0 in October 2024. As of 2026, the definition is the de facto standard for what counts as "open source AI." Most released "open source" models don't meet the criteria.

## Root cause

The OSAID 1.0 defines 4 freedoms for open source AI: use, study, modify, share. To exercise these freedoms, the user needs access to the model, training data information, training code, and model weights. Releasing weights alone is not enough.

## The 4 OSAID freedoms

The 4 freedoms are the framework for the definition.

1. **Use** the system for any purpose without permission
2. **Study** how the system works — inspect the components
3. **Modify** the system for any purpose — change the components
4. **Share** copies with or without modifications — redistribute

To exercise all 4, the user needs sufficient information about the system. Without it, the system is "open weights" or "open code" but not "open source AI."

## The 5 required components

For an AI system to qualify as open source AI under OSAID 1.0, 5 components are required.

1. **Model weights / parameters** — the trained model, sufficient to run inference
2. **Training data information** — sufficient to recreate a similar system (not necessarily the exact data; the metadata, sources, processing)
3. **Training code** — the code that, given the data and the model architecture, would train a similar model
4. **Model architecture** — the structure of the model
5. **Code for inference / serving** — the code to use the model

The 5 components map to the 4 freedoms. Missing any component limits which freedoms can be exercised.

## The data information rule

The training data requirement is the most-discussed OSAID 1.0 element.

- **Sufficient information** to recreate a similar system
- **Not necessarily the raw data** — metadata, sources, processing details
- **Not "any data whatsoever"** — the data that enables the system is what's required

The 2026 community interpretation: a detailed datasheet (data sources, sizes, preprocessing, filtering, license) is sufficient; the raw training data is not required.

## The 4 freedoms mapped to components

| Freedom | Requires |
|---|---|
| Use | model weights + inference code |
| Study | model weights + architecture + training code + data information |
| Modify | weights + training code + data information (or equivalent data access) |
| Share | any component + license that allows redistribution |

The freedoms build on each other. "Use" alone (weights + inference) is "open weights"; "Study" requires more; "Modify" requires the most.

## The 5 release models and their OSAID 1.0 compliance

| Release | Weights | Data info | Train code | Arch | Inference | OSAID? |
|---|---|---|---|---|---|---|
| Meta Llama 2/3 | yes | minimal | no | yes | yes | no (data + train code missing) |
| BigScience BLOOM | yes | yes | yes | yes | yes | yes (full compliance) |
| Mistral 7B (initial) | yes | no | no | yes | no | no |
| OLMo (Allen AI) | yes | yes | yes | yes | yes | yes (full compliance) |
| OpenAI GPT-4 | no | no | no | no | API only | no |

The 5 release models show the spectrum. Only full open-data + open-train-code + open-weights is OSAID-compliant.

## The 4-step OSAID assessment

For a team's AI release, 4 questions.

1. **Are the model weights released under an OSI-approved license?** If no, the system is not open source.
2. **Is sufficient training data information released?** If no, the "Study" and "Modify" freedoms are limited.
3. **Is training code released?** If no, the "Modify" freedom is limited.
4. **Is inference code released?** If no, the "Use" freedom is practical-limited.

The 4 questions are the 2026 due-diligence baseline.

## The 5 anti-patterns (rebranding "open" AI)

1. **"Open weights" = "open source AI."** False. Open weights is one component; OSAID requires 4 more.
2. **"Open source" with no training data information.** False. The data is the source; without it, you can't exercise the Modify freedom.
3. **"Source available" = "open source."** False. Source available is a license category; not all source-available licenses are OSI-approved.
4. **"We released the model card."** False. The model card is documentation; the 5 components are infrastructure.
5. **"We have a research-only license."** False. The OSAID requires no restriction on use; research-only violates the "Use" freedom.

## The 5 best practices for open source AI releases

1. **Release the 5 components under OSI-approved licenses.** Apache 2.0, MIT, BSD-3, MPL 2.0, AGPL-3.0 for code; CC-BY-4.0, CC-BY-SA-4.0 for data.
2. **Document the data lineage.** The data information is the most-missed component. See `lessons/ai-data-lineage-2026.md`.
3. **Release the training code, not just the model.** The training code is the "recipe"; without it, "Modify" is limited.
4. **Use the OSAID 1.0 checklist.** The OSI publishes a checklist; use it to verify compliance.
5. **Label the release clearly.** "Open weights," "open source AI (OSAID 1.0)," "source available" — the labels matter for downstream choice.

## The 5 business model implications

Releasing as OSAID 1.0 has 5 business model implications.

1. **Direct monetization is constrained.** No usage restrictions means no per-call license fee.
2. **Differentiation comes from service.** Hosting, fine-tuning, support, integration — services over the open model.
3. **Data is the moat, not the model.** If the model is open, the data and the integration are differentiators.
4. **Community contribution drives improvement.** Open development pulls in external contributions; the company can curate.
5. **Regulatory goodwill.** A OSAID-compliant model is more defensible against regulation than closed models.

The 5 implications explain why some companies release open (Meta, Mistral) and others don't (OpenAI, Anthropic).

## The 3 "open source" adjacent categories

The 3 categories that are NOT OSAID 1.0 but are commonly confused.

1. **"Open weights"** — model weights released; no data, no train code, no inference. Common.
2. **"Source available"** — code released under non-OSI license (e.g., BSL, SSPL, AGPL-waitlist). Different terms.
3. **"Open data"** — training data released; no model. The data is a separate open asset.

The 3 categories are useful; they're not open source AI per OSAID 1.0.

## The 5 license compatibility considerations

The 5 license issues for open source AI releases.

1. **Code licenses** — Apache 2.0 + MIT for code; permissive for downstream mixing
2. **Data licenses** — CC-BY-4.0 or CC0 for data; permissive for downstream use
3. **Model weights** — Apache 2.0 (Llama 2/3), RAIL (BigScience), custom; check each
4. **Documentation** — CC-BY-4.0 for docs; model card under CC
5. **Incompatibility** — some licenses (e.g., AGPL) require derivative works to be open; mixing with permissive licenses is risky

The 5 license considerations need legal review before release.

## The 4-quadrant decision matrix

| Weights | Data + Code | Decision |
|---|---|---|
| yes | yes | OSAID 1.0 compliant open source AI |
| yes | no | open weights; not open source AI |
| no | yes | open data; not open source AI |
| no | no | closed AI; not open source AI |

The 4-quadrant matrix is the assessment tool. Most "open source" AI is in the second quadrant.

## The 5 best-known fully OSAID-compliant releases (2026)

1. **BLOOM** (BigScience) — full release
2. **OLMo** (Allen AI) — full release
3. **StarCoder** (BigCode) — code model, full release
4. **Stable Diffusion** (Stability AI, RAIL license) — image model, with caveats
5. **MPT** (MosaicML) — partial compliance; data information limited

The 5 best-known releases are the references. The list grows slowly because full OSAID compliance is hard.

## The 4-step migration to OSAID compliance

For a team with "open weights" wanting to be OSAID 1.0 compliant:

1. **Document the training data** — even if not releasing the data, publish the data information
2. **Release the training code** — the script + the framework; not necessarily the data prep code
3. **Release the inference code** — the serving code, the eval code
4. **Choose OSI-approved licenses** — for each component

The 4 steps take 1-3 months; the compliance lasts forever.

## Verification

The tell that an AI system is OSAID 1.0 compliant:

- All 5 components (weights, data info, train code, arch, inference) are released
- All components under OSI-approved licenses
- The release is labeled "OSAID 1.0 compliant" or similar
- A datasheet / model card is published with the data lineage
- Training code is reproducible (given the data, the train code can recreate a similar model)

The tell it isn't:

- Only model weights are released
- "Open source" with a research-only or use-case restriction
- No training data information
- No training code
- License is non-OSI (BUSL, SSPL with restrictions, etc.)

## Gotchas

- **"Open weights" is not "open source AI."** The 2024 OSAID 1.0 made the distinction explicit.
- **Research-only licenses violate the "Use" freedom.** The OSAID requires no restriction on use.
- **The data information is the hardest component.** Documenting the data is more work than documenting the model.
- **Licenses matter.** Apache 2.0 weights + research-only code = not open source.
- **The 4 freedoms build on each other.** Most "open" releases satisfy "Use" but not "Modify."

## Related

- `lessons/ai-data-lineage-2026.md` — data lineage is a key component
- `worktree/git-lfs-2026.md` — large file storage for weights
- `worktree/sbom-slsa-2026.md` — supply chain provenance
- `compliance/` — license management

## Source URLs (verified 2026-08-10)

- https://opensource.org/ai — Open Source AI Definition 1.0
- https://opensource.org/blog/the-open-source-ai-definition-v1-0-is-here — OSAID 1.0 release
- https://opensource.org/ai/the-open-source-ai-definition — full definition
- https://www.linuxfoundation.org/blog/blog/the-open-source-ai-definition-a-matter-of-principles — Linux Foundation analysis
- https://huggingface.co/docs/hub/repositories — HuggingFace model card docs
- https://www.mozilla.org/en-US/MPL/2.0/ — MPL 2.0
- https://www.apache.org/licenses/LICENSE-2.0 — Apache 2.0
- https://creativecommons.org/licenses/by/4.0/ — CC-BY-4.0
- https://www.bigscience.house/ — BigScience project
- https://allenai.org/blog/olmo — OLMo release
