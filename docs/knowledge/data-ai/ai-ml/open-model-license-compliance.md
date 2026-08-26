# open-model-license-compliance

**Issue:** Self-hosting open-weight models has become the default cost lever, but "open weights" is a marketing term, not a license. The Llama Community License, Gemma Terms of Use, Apache-2.0, and MIT impose wildly different obligations, and the OSI's February 2025 analysis concluded the Llama license fails the Open Source Definition outright. Engineering teams routinely ship products on models whose licenses restrict commercial use, impose acceptable-use policies that propagate to downstream products, or carry named-entity and geographic clauses that create real legal exposure. License compliance for models is a dependency-management problem and belongs in the pipeline, not in a lawyer's inbox after launch.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Why "open weight" is not "open source"

1. **Open weights means you get the weights.** Not the data, not the training code, and often not unrestricted usage rights. The license grant is whatever the accompanying terms say it is — frequently a custom contract dressed in open-source aesthetics.

2. **OSI rejected the Llama license.** The February 2025 OSI analysis found the Llama Community License fails the Open Source Definition on multiple grounds, including "freedom 0" (unrestricted use), via its naming requirement, acceptable-use policy, and MAU cap. Calling such models "open source" in your own marketing imports that inaccuracy into your compliance posture.

3. **Custom terms can change under you.** Vendor custom licenses (Llama, Gemma terms) are unilateral contracts revisable by the vendor across releases — a model family's license has historically shifted between versions. Pin and review the license per checkpoint, not per family.

4. **"Commercial use allowed" is a floor, not the whole analysis.** A license can permit commercial use while prohibiting certain industries, imposing branding obligations, or restricting outputs. Read the whole document; the headline grant is the least interesting part.

## The major license families

1. **Apache-2.0 / MIT — permissive, boring, safe default.** Qwen (most checkpoints), Mistral (most), Phi, OLMo, and similar ship under classic permissive licenses: commercial use, modification, redistribution, with notice/patent terms. These carry the least review overhead and are the default choice when capability is comparable.

2. **Llama Community License — conditional.** Requires compliance with an acceptable-use policy, includes the 700M-MAU clause (entities exceeding 700 million monthly active users need a special license from Meta), attribution/naming requirements, and restrictions that flow into derivative models. Fine for most startups; a real review item for platforms, aggregators, and anyone reselling model access.

3. **Gemma Terms of Use — policy-encumbered.** Google's custom terms attach usage prohibitions and redistribution conditions beyond permissive norms (newer releases have trended toward more Apache-2.0-style terms — verify per release). Distillations from Gemma outputs have their own conditions, which matters if you train on model outputs.

4. **Research-only and non-commercial licenses.** Some checkpoints (certain fine-tunes, community models, some datasets) are research/non-commercial only. A single such model pulled into a Docker image by an enthusiastic teammate is a shipped violation. These must be blocked at ingestion, not discovered at audit.

5. **Output ownership and distillation terms.** Most permissive licenses grant you outputs; custom licenses sometimes constrain training competitors' models on outputs. If your product trains on model outputs (distillation pipelines, synthetic data), verify the license permits it for that specific checkpoint.

## Compliance review checklist

1. **Record license per artifact.** Every model artifact in the registry (weights, quantization, LoRA adapters) carries: license name, version, URL, hash of the license file at pull time, and reviewer. A model registry without license metadata is unauditable.

2. **Check the MAU and entity clauses against your reality.** The 700M-MAU threshold sounds absurd until your model powers a feature inside a giant platform's product. For B2B embedding of model serving, contractually clarify who counts as the "user."

3. **Map acceptable-use obligations to product controls.** If the license's AUP prohibits certain content generation, your deployment needs the corresponding input/output filtering (see ai-output-filtering, ai-safety-guardrails-implementation) — the AUP is enforceable against you, not just the model.

4. **Verify geographic restrictions.** Several model licenses (and their hosting terms) carry export-control or named-country clauses. Multi-region serving (US + EU + APAC nodes) can silently violate a geographic restriction the US-based team never read.

5. **Review derivative obligations.** Naming/attribution requirements for derivatives (Llama-style) mean your fine-tuned or merged checkpoint may itself need renaming and license carry-forward — this directly affects model-merging and LoRA pipelines that mix checkpoints.

6. **Track dataset licenses too.** The model may be Apache-2.0 while your fine-tuning dataset is CC-BY-NC. Compliance follows the whole dependency closure, same as code.

## Governance in the pipeline

1. **Gate model pulls on license allowlists.** CI and the model-pull tooling refuse artifacts whose license is not on the approved list; new licenses route to review, mirroring how `pnpm audit` gates dependencies. Curated references (e.g., the open-weight-models lists tracking commercially exploitable, no-geo-restriction models) seed the allowlist.

2. **SBOM-style model manifests.** Emit a manifest of every model in each release artifact: checkpoint hash, license, origin, and fine-tune lineage. When a license changes or a violation surfaces, the manifest tells you exactly which shipped products are exposed.

3. **Re-review on version bumps.** Model upgrades (Llama 3.x to 4.x, Gemma generations) are license events, not just eval events — add a license-diff step next to the eval regression gate in the upgrade checklist.

4. **Escalate custom licenses to counsel with a summary, not the raw text.** Engineering's job is detection and inventory; the handoff to legal should include the specific clauses (MAU, AUP, geography, distillation) and how the product actually uses the model, so review is fast and targeted.
