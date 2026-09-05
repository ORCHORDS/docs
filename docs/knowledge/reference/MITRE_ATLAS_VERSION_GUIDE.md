---
title: "MITRE ATLAS Adversarial Threat Landscape for AI Systems"
owner: "Reference Documentation"
status: "approved"
classification: "public"
last-reviewed: "2026-09-05"
review-cycle: "180 days"
next-review: "2027-03-04"
source: "MITRE ATLAS (current published version); https://atlas.mitre.org/"
---

# MITRE ATLAS Adversarial Threat Landscape for AI Systems

## Scope

Reference card for MITRE ATLAS, *Adversarial Threat Landscape for AI Systems*. ATLAS complements MITRE ATT&CK with AI/ML-specific adversary tactics, techniques, and case studies. Profiles that govern AI/ML systems should reference ATLAS and bind it to NIST AI 100-2 (Adversarial Machine Learning), NIST AI 600-1 (GenAI Profile), ISO/IEC 23894 (AI Risk Management), and the OWASP ML Top 10.

## Identifier table

| Field | Value |
| --- | --- |
| Primary document | MITRE ATLAS (current published version) |
| Status | Continuously maintained by MITRE |
| Companion artifacts | NIST AI 100-2 (Adversarial ML), NIST AI 600-1 (GenAI Profile), NIST AI RMF, ISO/IEC 23894, OWASP ML Top 10 |
| Source URL | https://atlas.mitre.org/ |

## Plan

1. Reference MITRE ATLAS by version whenever a profile governs AI/ML threat modelling.
2. Use ATLAS tactics and techniques as the basis for the AI/ML threat model: reconnaissance, resource development, initial access, ML model access, execution, persistence, defense evasion, discovery, collection, ML attack staging, exfiltration, impact.
3. Map AI/ML attack techniques to the AI/ML system lifecycle: data collection, model training, model deployment, inference, model update.
4. Bind ATLAS to NIST AI 100-2 for adversarial-ML-specific attack taxonomy and mitigations.
5. Bind to NIST AI 600-1 for the GenAI-specific threat overlay.
6. Use OWASP ML Top 10 as the community-recognized top risk catalogue.
7. Document deviations with the approver, scope, expiration, compensating controls, and review schedule.

## Inputs

- MITRE ATLAS tactics, techniques, and case studies.
- NIST AI 100-2 (Adversarial Machine Learning), NIST AI 600-1 (GenAI Profile).
- ISO/IEC 23894:2023 AI Risk Management.
- Internal AI/ML system inventory and threat model.

## ORCHORDS Profile

ORCHORDS treats MITRE ATLAS as the canonical reference for AI/ML adversary tactics and techniques. Profiles that reference AI/ML threat modelling should cite ATLAS, identify the techniques in scope, and bind to NIST AI 100-2, NIST AI 600-1, and ISO/IEC 23894.

A profile that references "AI security" without binding to a recognized AI/ML adversary taxonomy is non-conformant.

## Implementation Notes

- ATLAS techniques are organized by AI/ML lifecycle stage; map each technique to the lifecycle stages where it applies.
- ATLAS case studies provide real-world examples of AI/ML attacks; use them as input to red-team exercises.
- NIST AI 100-2 provides the attack taxonomy and the mitigations; align ATLAS techniques with NIST AI 100-2 mitigations.
- OWASP ML Top 10 provides a community-recognized top risk catalogue; use it as a sanity check for the threat model.
- AI/ML threat modelling should be updated as new ATLAS techniques and case studies are published.

## Companion Documents

- [NIST AI 100-2 Adversarial ML Version Guide](NIST_AI_100_2_ADVERSARIAL_ML_VERSION_GUIDE.md)
- [NIST AI 600-1 GenAI Profile Version Guide](NIST_AI_600_1_GENAI_PROFILE_VERSION_GUIDE.md)
- [ISO/IEC 23894:2023 AI Risk Version Guide](ISO_IEC_23894_2023_AI_RISK_VERSION_GUIDE.md)
- [EU AI Act Article 27 FRIA Version Guide](EU_AI_ACT_ARTICLE_27_FRIA_VERSION_GUIDE.md)
- [C2PA Content Credentials Version Guide](C2PA_CONTENT_CREDENTIALS_VERSION_GUIDE.md)
