# ISO/IEC 27032:2023 Cybersecurity and Cyberspace Guidance Governance

## Purpose

Govern the application of ISO/IEC 27032:2023 (cybersecurity and privacy protection — guidance for cybersecurity) so that the studio's cybersecurity practice addresses the cyberspace layer where organizational boundaries blur: interactions across information services, stakeholders, and supply chains, coordinating information security, application security, network security, and internet safety into a coherent cybersecurity posture.

## Scope

Applies to the studio's overall cybersecurity posture spanning internal systems and external interactions. Covers the 27032 framework's areas — threat agents, attack vectors, and cybersecurity controls — and its coordination model. Does not replace the ISMS (ISO/IEC 27001 governs that) or sector-specific regimes.

## Workflow

1. Distinguish the layers 27032 coordinates: information security (information protection), application security, network security, and internet safety — cybersecurity is the intersection where they meet cyberspace's cross-boundary interactions.
2. Model threat agents per the framework's classes (state, ideologists, criminals, thrill-seekers, insiders) against the studio's exposure; agent classes differ in intent and capability and therefore in the defenses they warrant.
3. Map attack vectors across the interaction surface: the vectors relevant to the studio's cyberspace presence (web services, third-party integrations, remote access), not only the internal network view.
4. Apply the framework's cybersecurity control areas: attack prevention and detection, incident readiness, and business continuity arrangements that operate across organizational boundaries.
5. Establish the coordination mechanism: 27032's central governance point coordinating the security disciplines — a named function or forum that owns the integrated posture rather than four disciplines each optimizing locally.
6. Extend obligations outward: suppliers and partners in the interaction chain receive protection requirements matching the interactions they carry; cross-boundary services are inside the cybersecurity perimeter the posture must cover.
7. Review the posture against the threat landscape annually: agent activity and vector relevance shift; the model is a living artifact.

## Controls and evidence

- Layer responsibility mapping (infosec, appsec, network, internet safety) with the coordination owner.
- Threat agent model with per-class exposure assessment.
- Attack vector map covering the external interaction surface.
- Supplier protection obligations for cross-boundary interactions.
- Annual posture review records.

## Validation

- Confirm the coordination function exists and has met within the review cadence.
- Sample three external interactions and confirm each carries documented protection obligations.
- Confirm the threat agent model was refreshed within the last review cycle.

## Failure correction

- **Coordination gap (disciplines operating independently)** → convene the coordination mechanism with a charter; the gap is a governance defect, not a staffing accident.
- **Unprotected external interaction discovered** → attach obligations or terminate the interaction; exposure without obligations is accepted risk without decision.
- **Stale threat model** → refresh the model and re-prioritize controls against current agent activity.

## Limitations

- 27032 is guidance without certification; its value is the coordination frame it imposes.
- Cyberspace threats evolve faster than standards cycles; supplement with threat intelligence sources.
- The standard deliberately complements rather than replaces 27001; organizations without an ISMS gain less from its coordination model.

## Scope note

This article is part of the security leaf. Cross-reference: `ISO_IEC_27032_1_2023_CYBERSECURITY_GUIDANCE_GOVERNANCE.md` sibling guidance, `NIST_SSDF_SP_800_218A_TAGGING_GOVERNANCE.md`, and `ENISA_THREAT_LANDSCAPE_ANNUAL_ASSESSMENT_GOVERNANCE.md`.

## Canonical sources

- ISO/IEC 27032:2023 — Cybersecurity and privacy protection — Guidance for cybersecurity: https://www.iso.org/obp/ui/#iso:std:iso-iec:27032:ed-2
- ISO/IEC 27001:2022 — Information security management systems — Requirements: https://www.iso.org/obp/ui/#iso:std:iso-iec:27001:ed-3
- ISO/IEC 27002:2022 — Information security controls: https://www.iso.org/obp/ui/#iso:std:iso-iec:27002:ed-4
- NIST SP 800-53 Rev 5 — Security and Privacy Controls: https://csrc.nist.gov/pubs/sp/800/53/rev-5/final
- ENISA — Threat Landscape: https://www.enisa.europa.eu/topics/cyber-threats/threat-landscape
