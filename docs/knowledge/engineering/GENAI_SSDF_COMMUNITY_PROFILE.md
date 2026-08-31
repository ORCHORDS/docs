# Generative AI SSDF Community Profile

## Purpose

NIST SP 800-218A, published in July 2024, extends the Secure Software Development Framework (SSDF) version 1.1 with AI-specific secure-development practices for generative AI and dual-use foundation models.

It is a Community Profile of the SSDF rather than a replacement for SP 800-218. Engineering programmes should therefore use it to augment the underlying secure-software-development lifecycle where AI model development creates additional risks or assurance needs.

## Engineering use

A reusable GenAI secure-development programme should:

1. map AI model development activities to the existing SSDF practices rather than creating an isolated AI-only security process;
2. identify model-specific assets, dependencies, data, training infrastructure, evaluation systems, and deployment components that require protection;
3. define provenance and integrity controls for models, datasets, code, configuration, and supporting artifacts;
4. assess threats and misuse cases introduced by generative or dual-use model capabilities;
5. integrate security testing and evaluation throughout model development rather than only after model packaging;
6. document model-development assumptions, security-relevant changes, and known limitations; and
7. preserve enough evidence to support repeatable review of how a model and its surrounding software were produced.

## Relationship to the SSDF

SP 800-218A augments SSDF v1.1 with AI-model-specific practices, tasks, recommendations, considerations, notes, and informative references. Teams should keep the core SSDF controls for organizational preparation, software protection, secure production, and vulnerability response, then apply the Community Profile where AI development introduces additional considerations.

## Scope discipline

The profile addresses secure development. It should not be treated as a complete AI governance, model-safety, privacy, legal-compliance, or deployment-risk framework by itself. Those concerns may require additional controls and sources.

## Sources

- NIST SP 800-218A — Secure Software Development Practices for Generative AI and Dual-Use Foundation Models: https://csrc.nist.gov/pubs/sp/800/218/a/final
- NIST SP 800-218 — Secure Software Development Framework (SSDF): https://csrc.nist.gov/pubs/sp/800/218/final

## Scope note

This article summarizes project-neutral engineering use of the NIST Community Profile. It does not claim implementation, conformity, certification, or security of any specific model or software system.