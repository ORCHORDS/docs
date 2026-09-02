# ISO 26162:2008 SSDDM Anonymization Vocabulary Template Governance

## Purpose

ISO 26162:2008, "Information technology — Security techniques — Vocabulary used in connection with the de-identification, re-identification, and re-identification risk management of personal data," defines the vocabulary used in the international standard for de-identification (anonymization) of personal data and the management of re-identification risk. The standard supports consistent terminology across anonymization techniques, re-identification risk assessments, and policy discussions. This article governs the application of ISO 26162 vocabulary as a template for an organization's anonymization documentation.

## Scope

The standard applies to any organization processing personal data that uses anonymization techniques. Within this knowledge base, the article covers the terms and definitions in ISO 26162 (anonymization, re-identification, identifiers, quasi-identifiers, direct identifiers, indirect identifiers, attribute disclosure, identity disclosure, membership disclosure, re-identification risk), the application of those terms to the organization's documentation, and the integration of the vocabulary with the organization's privacy controls. It does not cover the substantive anonymization techniques; readers should consult other resources for that.

## Workflow

1. Adopt the ISO 26162 vocabulary for the organization's anonymization documentation: policies, training materials, technical documentation, and internal communications should use the terms the standard defines.
2. Distinguish the key concepts:
   - Direct identifier: a data element that directly identifies an individual (e.g., national ID).
   - Quasi-identifier: a data element that, in combination with others, may identify an individual (e.g., date of birth, postal code).
   - Sensitive attribute: a data element whose value the organization seeks to protect against attribute disclosure.
3. Apply the disclosure risk concepts to the organization's risk assessments:
   - Identity disclosure: identifying an individual.
   - Attribute disclosure: learning a sensitive attribute value about an individual.
   - Membership disclosure: learning that an individual is in the dataset.
4. Document the re-identification risk management approach: the threat model, the assessment method, the controls applied, and the residual risk.
5. Update the documentation on anonymization method change.

## Controls and evidence

Controls include the documented anonymization vocabulary in the organization's policies, the risk assessment using the standard's terms, the documentation of anonymization methods and their limits, and the re-identification risk management records. Evidence of disciplined anonymization practice includes the risk assessment, the documented methods, and the residual-risk acceptance.

## Validation

Validation should confirm the vocabulary is used consistently, risk assessments reference the disclosure risk concepts, anonymization methods are documented, and re-identification risk management is performed. Reviewers should be able to trace from any anonymization practice to its documented rationale.

## Failure correction

Common failure modes: the vocabulary is used loosely (corrective: enforce the ISO 26162 vocabulary in the documentation); quasi-identifiers are not identified or treated as direct identifiers (corrective: distinguish the categories and treat them differently in risk assessment); re-identification risk is ignored because anonymization is treated as a one-time process (corrective: assess re-identification risk on each release and on changes to the underlying data); residual risk is accepted without evidence (corrective: require a documented residual risk acceptance with named approver).

## Limitations

ISO 26162 is a vocabulary standard; it does not prescribe anonymization techniques. The standard does not provide a quantitative model for re-identification risk; the organization selects the model that fits its context. The vocabulary is one element of anonymization practice; legal compliance with data protection laws (GDPR, CCPA, etc.) is governed by those laws and requires additional measures.

## Scope note

This article summarizes project-neutral use of ISO 26162:2008 as a template. It does not assert any specific organization's anonymization conformance or claim any certification outcome.

## Canonical sources

- ISO 26162:2008 — Information technology — Security techniques — Vocabulary used in connection with the de-identification, re-identification, and re-identification risk management of personal data: https://www.iso.org/standard/43462.html