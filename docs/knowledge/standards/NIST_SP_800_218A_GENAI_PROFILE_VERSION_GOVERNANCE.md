---
title: "NIST SP 800-218A Secure Software Development for AI Systems (GenAI Profile) Version Governance"
owner: "Application Security"
status: "active"
classification: "public"
last-reviewed: "2026-08-22"
review-cycle: "annual"
next-review: "2027-08-22"
source: "NIST SP 800-218A; SP 800-218 v1.1; NIST AI 100-2; NIST AI 600-1; SP 800-161; SLSA"
---

# NIST SP 800-218A Secure Software Development for AI Systems (GenAI Profile) Version Governance

## Purpose

NIST SP 800-218A is the AI-specific profile of the Secure Software Development Framework (SSDF), SP 800-218 v1.1. SP 800-218A addresses the secure development of AI systems, with a particular focus on generative AI, including data preparation, model training, evaluation, deployment, and ongoing operation. Profiles that govern AI/ML development lifecycles should reference SP 800-218A and bind to SP 800-218 v1.1 (base SSDF), NIST AI 100-2 (adversarial-ML taxonomy), NIST AI 600-1 (GenAI profile), NIST SP 800-161 (supply-chain risk management), and the SLSA framework.

## Current context and source status

SP 800-218A was published as an initial public draft; the final version is in review as of September 5, 2026. SP 800-218A inherits the SSDF practice families (PO, PS, PW, RV) and adds AI-specific considerations to each. The profile is intended to be referenced in conjunction with SP 800-218 v1.1, not as a replacement.

## Governance pattern

1. Cite SP 800-218A in AI/ML SDLC policies, model cards, and secure-development evidence.
2. Map each SSDF practice to AI-specific considerations using the SP 800-218A profile.
3. Apply PO (Organizational) practices to AI development environments, including GPU clusters, training-data storage, and model registries.
4. Apply PS (Protect Software) practices to model artifacts, training data, and the pre-trained-model supply chain.
5. Apply PW (Produce Well-Secured Software) practices to data-validation pipelines, fine-tuning workflows, and evaluation harnesses.
6. Apply RV (Vulnerability Response) practices to model-behavior incidents (jailbreaks, prompt injection, hallucinations).
7. Bind to NIST AI 100-2 for the adversarial-ML threat taxonomy.
8. Bind to NIST AI 600-1 for the GenAI risk profile.
9. Bind to NIST SP 800-218 for the base SSDF.
10. Bind to NIST SP 800-161 for the supply-chain risk management context.
11. Bind to SLSA for the build-integrity context.
12. Document deviations with approver, scope, expiration, compensating controls, and review schedule.

## Identifier details

| Family | AI-specific consideration (SP 800-218A) |
| --- | --- |
| PO.1 | Define model-behavior requirements, including acceptable and unacceptable outputs. |
| PO.5 | Secure GPU clusters, training-data storage, and model registries. |
| PS.1 | Treat model weights as sensitive artifacts; protect with access control and integrity verification. |
| PS.2 | Use signed model artifacts and reproducible training pipelines. |
| PS.3 | Archive training data, training code, model weights, and evaluation results for reproducibility. |
| PW.4 | Vet pre-trained models and datasets for license, provenance, and security. |
| PW.5 | Apply static and dynamic analysis to data pipelines, fine-tuning code, and inference code. |
| PW.7 | Review prompt-engineering code, tool-use definitions, and agent logic. |
| RV.1 | Treat model-behavior incidents as vulnerability reports. |

## Validation and evidence

Compliance evidence includes:

- AI/ML SDLC policy that cites SP 800-218A and maps SSDF practices to AI-specific considerations.
- Model cards that document training data, fine-tuning data, evaluation results, and intended use.
- Signed model artifacts with provenance metadata (for example, SLSA Build Level 3).
- Reproducible training pipelines with recorded environment, code version, and data version.
- Vulnerability-response runbook that addresses model-behavior incidents.
- Threat model that includes data poisoning, model theft, and prompt injection.
- Supply-chain attestation for pre-trained models and datasets.

Evidence that omits the AI-specific considerations or treats AI systems as conventional software does not establish SP 800-218A conformance.

## Companion Documents

- [NIST SSDF SP 800-218 Version Guide](../reference/NIST_SSDF_SP_800_218.md)
- [NIST SP 800-218A GenAI Profile Version Guide](../reference/NIST_SP_800_218A_GENAI_PROFILE_VERSION_GUIDE.md)
- [Supply Chain Levels for Software Artifacts (SLSA)](../reference/SUPPLY_CHAIN_LEVELS_SOFTWARE_ARTIFACTS.md)
- [NIST AI 100-2 Adversarial ML Version Guide](../reference/NIST_AI_100_2_ADVERSARIAL_ML_VERSION_GUIDE.md)
- [NIST AI 600-1 GenAI Profile Version Guide](../reference/NIST_AI_600_1_GENAI_PROFILE_VERSION_GUIDE.md)
- [NIST SP 800-161 C-SCRM](../reference/NIST_SP_800_161_C_SCRM.md)
- [CNCF Supply Chain Best Practices](../reference/CNCF_SUPPLY_CHAIN_BEST_PRACTICES.md)
