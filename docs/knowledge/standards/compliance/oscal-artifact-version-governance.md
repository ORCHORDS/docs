# OSCAL Artifact Version Governance

**Issue:** Control catalogs, baselines, system implementation, assessment results, and machine-executable policy artifacts are produced in multiple representations by multiple teams, with no consistent way to identify the exact artifact and model version used.

**Date:** 2026-09-01
**Author:** ORCHORDS
**Status:** documented

## Standards context

OSCAL is a NIST-led initiative to standardize and automate control-based security, privacy, risk, and compliance information. NIST presents it as an active program developed with industry, with the project site last updated June 2, 2026. The framework supports control catalogs, control baselines, system control implementation, monitoring and assessment results, and machine-executable policy representations in XML, JSON, and YAML.

OSCAL is a model and a representation, not a single product version. A claim of "OSCAL" support should record the exact model artifact, schema or version reference, serialization, and validation tooling used.

## Artifact register

Maintain an OSCAL artifact register with:

- artifact family: catalog, profile, component definition, system security plan, assessment plan, assessment results, plan of action and milestones, or machine-executable policy;
- model artifact, version reference, or schema URL;
- serialization: XML, JSON, or YAML;
- tooling: generator, validator, converter, and any custom scripts;
- authority source, baseline reference, and parent profile or catalog;
- author, approver, publication and effective date;
- applicable systems, control scope, and review cycle; and
- mapping to internal evidence, control narratives, and external frameworks.

Use stable identifiers so an artifact, its parent and child references, and downstream generated evidence can be reproduced.

## Version pinning and migration

OSCAL model artifacts evolve. Record the exact model artifact reference, schema URL, or namespace used to author each OSCAL document and the matching version used by every consumer. A generic "OSCAL" link does not reproduce the decision.

Treat a model upgrade as a controlled migration:

1. inventory affected artifacts and consumers;
2. identify changed requirements, structural rules, and serialization semantics;
3. validate that every generator, validator, and converter supports the new version;
4. test round-trip conversion for the chosen serialization;
5. reconcile back-references in profiles and components;
6. update evidence pipelines, dashboards, and external consumers; and
7. retain the prior artifacts long enough to support change review.

Do not let tooling default upgrades silently change the effective version.

## Serialization governance

XML, JSON, and YAML representations of the same model can have different tooling, validation, signing, and storage characteristics. Use the serialization supported by each consumer pipeline and document the decision.

Validation should confirm structure, cross-references, identifier uniqueness, required fields, and consistency with the chosen profile. Round-trip conversion to another serialization is useful as a sanity test but is not a substitute for content review.

## Evidence integration

Link OSCAL artifacts to the operational evidence that supports each statement. A control narrative in a system security plan should reference logs, configurations, tickets, code commits, or assessment results by a stable identifier. A machine-executable policy should reference the source documents that authorize or require it.

Avoid storing sensitive data inside OSCAL artifacts beyond the minimum needed for the assessment purpose. Maintain a separate evidence store for confidential content and reference it from OSCAL documents by controlled location.

## Change and review

Changes to catalogs, profiles, component definitions, or system plans should follow normal document control. A change should identify the previous and proposed versions, affected controls and systems, evidence impact, approval, and effective date. Preserve historical artifacts so that earlier compliance periods remain reviewable.

When an external framework or baseline changes, record the upstream reference and the OSCAL representation used to apply it. Re-mapping a framework without recording the source can produce a self-consistent but externally unmoored artifact set.

## Verification

- Validate each artifact with a tool pinned to the recorded model version and serialization.
- Confirm that catalog, profile, component, plan, and result artifacts reconcile to expected identifiers and references.
- Test a model upgrade in a non-production environment before consuming downstream evidence.
- Re-derive a sample evidence link from OSCAL back to the source record.
- Detect duplicate or orphan identifiers across OSCAL artifacts and consumers.
- Compare current artifact versions to the registered version after every pipeline change.

## Failure modes

- Treating OSCAL artifacts as plain documents loses the structure and validation guarantees the model provides.
- Calling any XML or JSON file OSCAL without recording the model version overstates the framework.
- Assuming a generator supports the latest model can silently break validation.
- Embedding sensitive data inside OSCAL files instead of using a separate evidence store increases exposure.
- Converting between serializations without round-trip checks hides structural drift.
- Re-mapping external frameworks without recording sources creates internally consistent but unverifiable catalogs.
- Mixing model versions in one pipeline produces evidence that consumers cannot reconcile.

## Official sources

- [NIST OSCAL project overview](https://pages.nist.gov/OSCAL/)
- [NIST OSCAL concepts, layers, and artifacts](https://pages.nist.gov/OSCAL/concepts/layer/)

Source status was checked on September 1, 2026.

## Scope note

This article governs artifact versioning and evidence integration. It does not certify conformance, replace OSCAL model documentation, or substitute for validation, control mapping, or assessor judgment.
