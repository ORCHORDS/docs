---
title: "NIST SP 800-218A Secure Software Development for AI Systems (GenAI Profile) Version Guide"
standard: "NIST SP 800-218A (Draft)"
publisher: "National Institute of Standards and Technology (NIST)"
category: "reference"
subcategory: "ai-systems-engineering"
canonical_url: "https://csrc.nist.gov/pubs/sp/800/218/a/final"
status: "approved"
classification: "public"
audience: "AI engineers, ML platform teams, secure software development lifecycle (SDLC) owners"
last-reviewed: "2026-09-05"
review-cycle: "180 days"
next-review: "2027-03-04"
---

# NIST SP 800-218A Secure Software Development for AI Systems (GenAI Profile) Version Guide

## Profile

NIST SP 800-218A is a profile of the Secure Software Development Framework (SSDF), SP 800-218, that describes secure software development practices for AI systems, with a particular focus on generative AI (GenAI). The profile identifies how SSDF practices (PO, PS, PW, RV) apply to data preparation, model training, evaluation, deployment, and ongoing operation of AI systems. The GenAI profile addresses AI-specific threats: data poisoning, prompt injection, sensitive data leakage, model theft, and supply-chain risks from pre-trained models, fine-tuning datasets, and model-serving infrastructure.

The profile is structured as practice enhancements to SSDF v1.1. Each SSDF practice is annotated with AI-specific considerations and additional practice statements that go beyond generic secure software development.

## Identifier

| Field | Value |
| --- | --- |
| Primary document | NIST SP 800-218A (Secure Software Development for AI Systems) |
| Publisher | NIST Computer Security Resource Center (CSRC) |
| Status | Initial public draft; final version in review |
| Companion artifacts | NIST SP 800-218, NIST AI 100-2, NIST AI 600-1, EU AI Act |
| Source URL | https://csrc.nist.gov/pubs/sp/800/218/a/final |

## Current context and source status

NIST SP 800-218A was published as an initial public draft. It is intended as a profile of SP 800-218 v1.1. No successor revision is published as of September 5, 2026, although periodic updates to SP 800-218 itself will affect the base practices.

## Governance pattern

1. Cite SP 800-218A in AI/ML SDLC policies, model cards, and secure-development evidence.
2. Apply SSDF PO practices (Organizational) to AI development environments, including GPU clusters, training-data storage, and model registries.
3. Apply SSDF PS practices (Protect Software) to model artifacts, training data, and the supply chain for pre-trained models.
4. Apply SSDF PW practices (Produce Well-Secured Software) to data-validation pipelines, fine-tuning workflows, and evaluation harnesses.
5. Apply SSDF RV practices (Vulnerability Response) to model-behavior incidents, including jailbreaks and prompt-injection attacks.
6. Bind to NIST AI 100-2 (Adversarial ML Taxonomy) for the threat taxonomy.
7. Bind to NIST AI 600-1 (GenAI Profile) for the generative-AI risk profile.
8. Bind to NIST SP 800-218 for the base SSDF.
9. Bind to NIST SP 800-161 for the supply-chain risk management context.
10. Document deviations with approver, scope, expiration, compensating controls, and review schedule.

## Identifier details

| Family | AI-specific consideration |
| --- | --- |
| PO.1 (Security Requirements) | Define requirements for model behavior, including acceptable and unacceptable outputs, and threat-model the AI system. |
| PO.5 (Implementation Security) | Secure the development environment including GPU access, training-data storage, and code repositories. |
| PS.1 (Protect Code) | Treat model weights as sensitive artifacts; protect with access control and integrity verification. |
| PS.2 (Provide a Mechanism for Verifying Software Release Integrity) | Use signed model artifacts and reproducible training pipelines. |
| PS.3 (Secure Archive) | Archive training data, training code, model weights, and evaluation results for reproducibility and audit. |
| PW.4 (Reuse Existing Software) | Vet pre-trained models and datasets for license, provenance, and security. |
| PW.5 (Code Analysis) | Apply static and dynamic analysis to data pipelines, fine-tuning code, and inference code. |
| PW.7 (Review Human-Generated Code) | Review prompt-engineering code, tool-use definitions, and agent logic. |
| RV.1 (Vulnerability Response) | Treat model-behavior incidents (jailbreaks, prompt injection, hallucinations) as vulnerability reports. |

## Validation and evidence

Compliance evidence includes:

- SDLC policy that explicitly cites SP 800-218A and maps SSDF practices to AI-specific considerations.
- Model cards that document training data, fine-tuning data, evaluation results, and intended use.
- Signed model artifacts with provenance metadata (for example, SLSA Build Level 3 attestation).
- Reproducible training pipelines with recorded environment, code version, and data version.
- Vulnerability-response runbook that addresses model-behavior incidents.
- Threat model that includes data poisoning, model theft, and prompt injection.
- Supply-chain attestation for pre-trained models and datasets.

Evidence that omits the AI-specific considerations or treats AI systems as conventional software does not establish SP 800-218A conformance.

## Companion Documents

- [NIST SSDF SP 800-218](NIST_SSDF_SP_800_218.md)
- [NIST SSDF SP 800-218A GenAI Profile Version Governance](../standards/NIST_SP_800_218A_GENAI_PROFILE_VERSION_GOVERNANCE.md)
- [Supply Chain Levels for Software Artifacts (SLSA)](SUPPLY_CHAIN_LEVELS_SOFTWARE_ARTIFACTS.md)
- [NIST AI 100-2 Adversarial ML Version Guide](NIST_AI_100_2_ADVERSARIAL_ML_VERSION_GUIDE.md)
- [NIST AI 600-1 GenAI Profile Version Guide](NIST_AI_600_1_GENAI_PROFILE_VERSION_GUIDE.md)
- [NIST SP 800-161 C-SCRM](NIST_SP_800_161_C_SCRM.md)
- [CNCF Supply Chain Best Practices](CNCF_SUPPLY_CHAIN_BEST_PRACTICES.md)
