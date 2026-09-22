# NIST CSF 2.0 RS.CO-02 Data and AI Applicability Profile

## Outcome

**RS.CO-02:** Internal and external stakeholders are notified of incidents

## Data and AI applicability review

Evaluate this outcome against the real architecture rather than assuming that an AI-specific framework replaces ordinary cybersecurity outcomes.

### Review surfaces

- datasets, metadata, lineage, and storage;
- training, tuning, evaluation, and inference systems;
- retrieval and embedding pipelines;
- agents, tools, delegated actions, and automation;
- APIs, identities, secrets, networks, and dependencies supporting the workflow;
- human review, governance, supplier, and operational processes around the system.

## Decision method

1. Identify which review surfaces actually exist.
2. Decide whether the outcome applies to those surfaces.
3. Link applicable requirements to real technical or governance evidence.
4. Record partial applicability and shared responsibility.
5. Record non-applicability with an architecture-based rationale.
6. Revisit after model, data, tool, provider, identity, or deployment changes.

## Source

- NIST Cybersecurity Framework 2.0: https://doi.org/10.6028/NIST.CSWP.29
- NIST OSCAL catalog: https://github.com/usnistgov/oscal-content/blob/main/nist.gov/CSF/v2.0/json/NIST_CSF_v2.0_catalog.json
- Catalog version: 1.2.0
- Catalog published: 2026-05-13

## Boundary

This profile does not force the outcome onto an AI/data system where the relevant surface does not exist, and it does not treat AI-specific controls as a substitute for applicable general cybersecurity outcomes.
