# ai-bill-of-materials-2026

**Issue:** A team ships a model built on PyTorch, fine-tuned on a custom dataset, served with vLLM. A vulnerability is disclosed in one of the upstream packages. The team can't easily identify which of their 40 deployed models are affected. The team needs an AI Bill of Materials (AI-BOM) standard.

**Date:** 2026-08-10
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Symptom

CycloneDX 1.6 (released July 2024) added AI-BOM as a formal component type. SPDX 3.0 (released 2024) added AI package support. The 2026 default for ML supply chain is to generate both an SBOM (software) and an AI-BOM (model, dataset, training code, fine-tuning data, evaluation results) per release.

## Root cause

Traditional SBOM captures software dependencies but not model weights, datasets, training recipes, or fine-tuning lineage. AI systems need a separate component manifest to support vulnerability response, license compliance, and regulatory reporting (EU AI Act Article 13 transparency).

## The 6 AI-BOM component types (CycloneDX 1.6+)

1. **model.** The trained model with weights, architecture, framework, version.
2. **dataset.** Training, validation, test, evaluation datasets with source/license/size/PIBI status.
3. **data.** Individual data items (when sample-level transparency required).
4. **machine-learning-model.** (CycloneDX 1.6 renamed to `model`; legacy form still supported).
5. **ml-model** (legacy type, deprecated).
6. **ml-dataset** (legacy type, deprecated).

## The 7 CycloneDX 1.6 AI-BOM fields

1. **name, version, group.** Standard component fields.
2. **`type: model` or `type: dataset`.** New in 1.6.
3. **`purl` or `swid` tag.** Standard identifier.
4. **`hashes` (SHA-256 minimum).** Model weights hash, dataset content hash.
5. **`licenses`.** Model license (Apache 2.0, Llama Community, RAIL), dataset license.
6. **`externalReferences`.** Hugging Face model URL, dataset DOI, code repo.
7. **`properties` (custom).** Training framework, base model, training data summary, evaluation metrics.

## The 4-step AI-BOM generation pattern

1. **Inventory.** What model(s) does this release ship? What datasets trained it? What code trained it?
2. **Identify upstream.** Base model, dataset sources, fine-tuning data, evaluation suites.
3. **Generate CycloneDX 1.6 AI-BOM** using `cdxgen` (with `--type ai`), `syft`, or `spdx-sbom-generator` with AI extensions.
4. **Sign and attest.** Sigstore cosign, in-toto attestations, attach to release artifact.

## The 5 regulatory drivers

1. **EU AI Act Article 13.** Transparency and provision of information to deployers.
2. **EU AI Act Article 53.** GPAI training data summary (sufficiently detailed).
3. **US Executive Order 14110 (Oct 2023, rescinded Jan 2025).** Required sharing of safety test results with DHS; some requirements inherited by CAISI/USAi.
4. **NIST AI 600-1 GenAI Profile.** MS-2.6-002: assess existence of harmful bias, IP infringement, data privacy in training data.
5. **California AB 2013.** Training data transparency for generative AI developers (effective Jan 1, 2026).

## The 5 best practices

1. **Generate AI-BOM on every release**, not on demand.
2. **Include both raw model and quantized/converted variants** in the manifest.
3. **Hash model weights, not just the file name.** Hash drift catches re-uploads.
4. **Track lineage from base model → fine-tuned model → deployment** with model cards cross-referenced.
5. **Sign AI-BOM with Sigstore cosign** for non-repudiation.

## The 5 anti-patterns

1. **No model hashing.** Identical-name models can have different weights.
2. **Manual AI-BOM.** Errors inevitable; automate.
3. **SBOM only, no AI-BOM.** Misses model, dataset, fine-tuning lineage.
4. **AI-BOM not signed.** No way to detect tampering.
5. **AI-BOM not stored with the model.** Use a registry (Hugging Face, MLflow, OCI artifact) that ties them together.

## Verification

The tell that AI-BOM is set up right:

- AI-BOM generated for every release, stored with the model
- Both CycloneDX 1.6 (model + dataset) and SPDX 3.0 (AI package) supported
- Hashes computed for model weights, dataset content, training code
- Licenses declared for all components
- AI-BOM signed and verified in CI
- Vulnerability response can map CVE → affected models in <1 hour

The tell it isn't:

- "Our model is at huggingface.co/our-org/our-model" with no manifest
- AI-BOM generated once and never updated
- Different weights under the same model name
- No way to answer "which models are affected by CVE-2026-XXXX?"

## Gotchas

- **CycloneDX 1.6 vs SPDX 3.0** both support AI components. Most tooling supports CycloneDX; SPDX 3.0 adoption is still early.
- **Model registry (Hugging Face, MLflow) doesn't enforce AI-BOM.** The publisher must add it.
- **Fine-tuning lineage** is hard. Track base model, training data, hyperparameters, seed, hardware. Most teams underdocument this.
- **Evaluation results** are often out of date by the time AI-BOM is generated. Tie eval runs to model versions.
- **Quantization changes weights hash.** A GPTQ or AWQ quantized model has different SHA-256 than the FP16 original. Document separately.

## Related

- `worktree/sbom-slsa-2026.md` - SBOM and SLSA patterns
- `worktree/sbom-licenses-2026.md` - license compliance
- `worktree/signed-commits-2026.md` - commit signing
- `lessons/ai-supply-chain-attacks-2026.md` - attack patterns

## Source URLs (verified 2026-08-10)

- https://cyclonedx.org/specification/overview/
- https://github.com/CycloneDX/cyclonedx-python-lib
- https://github.com/cdxgen/cdxgen
- https://spdx.github.io/spdx-spec/v3.0/
- https://www.in-toto.io/
- https://github.com/sigstore/cosign
