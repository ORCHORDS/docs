# NIST SP 800-53 PL-4 Rules of Behavior Data and AI Applicability Profile

## Control reference

- Control: **PL-4 — Rules of Behavior**
- Family: Planning

## Applicability review for data and AI systems

Evaluate this control against the actual data, model, agent, automation, and supporting-platform architecture. Do not assume AI-specific guidance displaces applicable system security or privacy controls.

## Review surfaces

- datasets, metadata, storage, and lineage;
- model development, evaluation, inference, and serving;
- retrieval, embedding, and vector systems;
- agents, tools, actions, and delegated credentials;
- APIs, identities, secrets, networks, endpoints, and dependencies;
- human review, governance, supplier, and operational processes.

## Decision steps

1. Read the current control and assessment objectives.
2. Determine whether the relevant control surface exists.
3. Resolve organization-defined parameters for the real architecture.
4. Map direct, shared, and inherited responsibility.
5. Link applicable requirements to implementation and operational evidence.
6. Record partial or non-applicability with technical rationale.
7. Revisit after model, data, provider, identity, tool, or deployment changes.

## Source

- NIST SP 800-53 Rev. 5.2.0 OSCAL catalog: https://github.com/usnistgov/oscal-content/blob/main/nist.gov/SP800-53/rev5/json/NIST_SP-800-53_rev5_catalog.json
- Catalog version: 5.2.0
- Catalog last modified: 2026-05-11

## Boundary

This profile does not force the control onto an architecture where it is not applicable and does not treat AI-specific controls as a substitute for applicable general controls.
