---
title: "C2PA Content Credentials Version Guide"
standard: "C2PA Technical Specification (current published version)"
publisher: "Coalition for Content Provenance and Authenticity (C2PA)"
category: "reference"
subcategory: "content-provenance"
canonical_url: "https://c2pa.org/specifications/specifications/2.0/"
status: "approved"
classification: "public"
audience: "Content platform engineers, media integrity researchers, AI-content governance leads"
last-reviewed: "2026-09-05"
review-cycle: "180 days"
next-review: "2027-03-04"
---

# C2PA Content Credentials Version Guide

## Profile

The Coalition for Content Provenance and Authenticity (C2PA) develops the Content Credentials specification, an open technical standard for cryptographically signing media files with provenance metadata (creator, edits, AI-generated components). C2PA builds on the W3C Verifiable Claims and the W3C Provenance Ontology. C2PA Content Credentials address misinformation, deepfakes, and the lack of provenance for digital media. Profiles that govern digital-media integrity, AI-content governance, or content authenticity should cite the current C2PA specification and bind to the EU AI Act, NIST AI 600-1, and MITRE ATLAS.

## Identifier

| Field | Value |
| --- | --- |
| Primary document | C2PA Technical Specification (current published version, e.g. 2.x) |
| Publisher | Coalition for Content Provenance and Authenticity |
| Status | Active specification; periodic minor revisions |
| Companion artifacts | W3C Verifiable Claims, W3C Provenance Ontology, EU AI Act Article 27 (FRIA), NIST AI 600-1, MITRE ATLAS |
| Source URL | https://c2pa.org/specifications/specifications/2.0/ |

## Current context and source status

The C2PA Technical Specification is in the 2.x series as of September 5, 2026. Earlier versions (1.x) are widely deployed. The specification defines the manifest store, the assertion format, the trust model (X.509 certificate chain), and the validation process.

## Governance pattern

1. Cite the current C2PA specification by version in content-credentials policy and content-platform documentation.
2. Apply C2PA Content Credentials to media files at creation, editing, and distribution.
3. Maintain a trust list (X.509 root and intermediate certificates) for content credential issuers.
4. Validate content credentials on consumption; surface validation results to consumers.
5. Document the AI-component assertion (whether the content contains AI-generated or AI-modified components).
6. Document the chain of custody from creation through distribution.
7. Bind to EU AI Act Article 27 (FRIA) for the EU regulatory context on AI-generated content.
8. Bind to NIST AI 600-1 for the GenAI risk profile.
9. Bind to MITRE ATLAS for the adversarial-ML threat context.
10. Bind to UNESCO Recommendation on the Ethics of AI for the broader ethical framework.
11. Document deviations with approver, scope, expiration, compensating controls, and review schedule.

## Identifier details

- **Manifest store**: a structure embedded in the media file that contains assertions and the C2PA signature.
- **Assertion**: a signed statement about the content (for example, `c2pa.actions`, `c2pa.ingredient`, `c2pa.ai_generative_training`).
- **Trust model**: X.509 certificates with a C2PA trust list; validation requires the issuer to be in the trust list at signing time.
- **Validation**: the process of verifying the manifest signature, the issuer trust chain, and the integrity of the referenced content.
- **Soft binding**: hash-based binding to the content bytes; detects modification but not visual manipulations.

## Validation and evidence

Compliance evidence includes:

- Content-credentials policy that cites the current C2PA specification by version.
- Trust-list configuration with X.509 root and intermediate certificates.
- Manifest-store generation tooling integrated into creation, editing, and distribution workflows.
- Validation tooling integrated into consumption workflows.
- Records of validation results (pass, fail, unsupported) for ingested content.
- AI-component assertions recorded for content with AI-generated or AI-modified components.

Evidence that omits the trust-list configuration, the validation tooling, or the AI-component assertions does not establish C2PA conformance.

## Companion Documents

- [EU AI Act Article 27 FRIA Version Guide](EU_AI_ACT_ARTICLE_27_FRIA_VERSION_GUIDE.md)
- [MITRE ATLAS Version Guide](MITRE_ATLAS_VERSION_GUIDE.md)
- [NIST AI 600-1 GenAI Profile Version Guide](NIST_AI_600_1_GENAI_PROFILE_VERSION_GUIDE.md)
- [UNESCO AI Ethics 2021 Version Guide](UNESCO_AI_ETHICS_2021_VERSION_GUIDE.md)
