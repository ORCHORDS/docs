---
title: "NIST AI 100-2 Adversarial Machine Learning Taxonomy Version Guide"
standard: "NIST AI 100-2"
publisher: "U.S. National Institute of Standards and Technology (NIST)"
category: "reference"
subcategory: "ai-adversarial-ml"
canonical_url: "https://www.nist.gov/itl/ai-risk-management-framework/adversarial-ml-profile"
status: "approved"
classification: "public"
audience: "AI/ML security engineers, ML platform owners, red team leads"
last-reviewed: "2026-09-04"
review-cycle: "180 days"
next-review: "2027-03-03"
---

# NIST AI 100-2 Adversarial Machine Learning Taxonomy Version Guide

## Profile

NIST AI 100-2 (January 4, 2024) is the Adversarial Machine Learning (AML) taxonomy and terms glossary developed within the AI RMF program. It establishes a shared vocabulary for adversarial attacks against predictive AI (including generative AI), for evasion, poisoning, and privacy attacks, and for the corresponding defenses. This document is the authoritative glossary; mitigation actions are addressed in companion guidance (NIST SP 800-218A for generative AI; AI RMF Generative AI Profile NIST AI 600-1).

## Identifier

| Field | Value |
| --- | --- |
| Document number | NIST AI 100-2 |
| Title | Adversarial Machine Learning: A Taxonomy and Terminology of Attacks and Mitigations |
| Publication date | 2024-01-04 |
| Companion | NIST AI 100-1 (AI RMF 1.0) |
| Generative AI companion | NIST AI 600-1 (Generative AI Profile) |
| Secure development companion | NIST SP 800-218A (Generative AI Profile for SSDF) |

## Threat Taxonomy

| Class | Goal | Examples |
| --- | --- | --- |
| Evasion | Cause the model to misclassify at inference. | Adversarial examples, gradient-based perturbations, universal perturbations. |
| Poisoning | Compromise model integrity at training. | Backdoor triggers, label flipping, clean-label poisoning, pre-training data poisoning. |
| Privacy | Extract information about the model or its data. | Membership inference, model inversion, attribute inference, reconstruction. |
| Abuse | Repurpose the model for unintended use. | Domain shift exploitation, repurposing via fine-tuning, jailbreaks. |
| Confidentiality / model extraction | Steal model parameters or behavior. | Model stealing, distillation-based extraction, side-channel leakage. |
| Reprogramming | Force the model to perform a different task. | Trojan reprogramming. |

## Attack Stage and Knowledge

| Dimension | Options |
| --- | --- |
| Stage | At training (poisoning); at inference (evasion, abuse, extraction, privacy). |
| Attacker knowledge | White-box (full model access), black-box (output only), gray-box (partial). |
| Attacker goal | Targeted (specific class), untargeted (any wrong class), confidence reduction. |
| Attack modality | Image, text, audio, tabular, multi-modal. |
| Attack surface | Training data, model weights, inputs, prompts, outputs, the model's external interface. |

## ORCHORDS Profile

| Field | ORCHORDS convention |
| --- | --- |
| Adoption | Apply the taxonomy as the authoritative vocabulary in red-team reports and threat models for AI systems. |
| Pairing | Pair with NIST AI 600-1 for generative AI attack categories; pair with NIST SP 800-218A for SSDF controls. |
| Threat model entries | Tag threats by NIST AI 100-2 class, stage, attacker knowledge, and modality. |
| Red-team scope | Red-team objectives SHOULD cover evasion, poisoning, privacy, abuse, extraction, and reprogramming in scope setting. |
| Incident mapping | AML incidents MUST be classified by taxonomy class before severity scoring; record the mapping in the incident record. |
| Metric recording | Record attack success rate, perturbation budget, and model accuracy delta at evaluation; do not record only pass/fail. |

## Implementation Notes

- Do not collapse "prompt injection" and "jailbreak" into a single category; prompt injection is an evasion-class attack against the system, while jailbreaks are a subset of abuse against the policy.
- Privacy attacks (membership inference, model inversion) require separate threat modeling and metrics, distinct from adversarial accuracy.
- Defenses are not generic; choose defenses by stage (training-time vs inference-time), attacker knowledge, and modality.
- Pair AML defenses with the application's risk register, governed by NIST AI 100-1 (AI RMF 1.0).

## Companion Documents

- [NIST AI 100-1 AI RMF 1.0 Version Guide](NIST_AI_100_1_AI_RMF_1_0_VERSION_GUIDE.md)
- [NIST AI 600-1 Generative AI Profile Version Guide](NIST_AI_600_1_GENAI_PROFILE_VERSION_GUIDE.md)
- [MITRE ATLAS — Adversarial Threat Landscape for AI Systems](MITRE_ATLAS_VERSION_GUIDE.md)
- [NIST SP 800-218A GenAI Profile](NIST_SP_800_218A_GENAI_PROFILE_VERSION_GUIDE.md)
