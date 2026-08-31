# Identity Proofing Exception Handling

## Purpose

Identity-proofing systems fail for reasons that are not fraud: applicants may lack conventional evidence, identity attributes may have changed, a validation provider can be unavailable, a device may not support remote capture, or an applicant may need accessibility or language assistance.

NIST SP 800-63A Revision 4 requires credential service providers to document operational processes for errors and exceptions and encourages options such as trusted referees and applicant references for applicants who cannot complete standard proofing paths.

Support operations should therefore provide a controlled exception route without turning exceptions into lower-assurance shortcuts.

## Types of exception

Classify the reason the standard process could not complete. Useful categories include:

- **evidence exception** — required evidence is unavailable or cannot reasonably be obtained;
- **attribute mismatch** — evidence is legitimate but names, addresses, or other attributes differ;
- **technical failure** — a validation source, capture system, network, or dependent service fails;
- **capture failure** — the applicant cannot produce acceptable image, video, or biometric capture;
- **accessibility barrier** — the standard workflow is not usable with the applicant's capabilities or assistive technology;
- **device/access limitation** — the applicant lacks compatible technology or connectivity;
- **identity-theft impact** — normal records or attributes are unreliable because of prior fraud; or
- **other documented exception** — a scenario covered by the provider's approved practice statement.

Do not label every failed proofing attempt as suspicious simply because automation could not complete it.

## Document the exception policy

NIST requires operational processes for error and exception handling to be documented. A policy should define:

- which identity assurance levels support each exception mechanism;
- who may approve use of an exception;
- what evidence or corroboration remains required;
- trusted-referee and applicant-reference eligibility;
- permitted process assistance;
- records to retain;
- escalation for fraud indicators; and
- when no compliant exception path is available.

Frontline staff should not invent proofing methods during a difficult case.

## Trusted referees

NIST describes trusted referees as a mechanism to help applicants who cannot satisfy the normal proofing process for applicable assurance levels. Examples can include people without required identity evidence, persons with disabilities, older people, people experiencing homelessness, people with limited technology or credit history, identity-theft victims, people affected by disasters, and children.

Where trusted referees are used, NIST requires a structured program including public availability information, written policy, training and certification, session records, and risk-based decision-making.

A trusted referee is not simply a support representative who decides to waive requirements. The role should be formally designated and trained.

## Trusted-referee training

NIST identifies training areas that include:

- identity-document identification and validation;
- indicators of damaged, altered, fabricated, or forged evidence;
- facial-image comparison;
- social-engineering indicators such as distress, confusion, or coercion; and
- periodic review of the referee's ability to perform required visual checks.

Organizations should track training status and prevent unqualified staff from acting as trusted referees.

## Applicant references

NIST also defines an applicant reference: a person who can vouch for the applicant's identity, attributes, or contextual conditions. An applicant reference supports the proofing claim but does not act on the applicant's behalf.

When this mechanism is supported, define:

- who can serve as a reference;
- what they may attest to;
- how the reference is identified or authenticated;
- how conflicts or collusion risks are handled; and
- how the attestation is documented.

Do not treat a personal acquaintance as authoritative merely because they are confident.

## Process assistants

A process assistant can provide translation, transcription, accessibility, or similar support while the applicant completes proofing. NIST distinguishes assistance from proofing decision-making.

Support workflows should preserve that boundary: an assistant can help the applicant interact with the process but should not substitute their own identity evidence, make risk decisions, or receive credentials on the applicant's behalf unless another authorized legal relationship applies.

## Technical failure workflow

When proofing fails because a dependent service or capture technology is unavailable:

1. identify whether the failure is local or systemic;
2. avoid repeated attempts that create unnecessary lockouts or duplicate records;
3. preserve the pending application state where allowed;
4. give the applicant a clear retry or alternate-method path;
5. avoid downgrading assurance automatically; and
6. record the incident if the dependency repeatedly blocks proofing.

Service unavailability is not evidence that the applicant failed identity verification.

## Attribute mismatches

Legitimate people can have mismatched attributes because of name changes, address changes, transliteration, data-entry errors, cultural naming patterns, or stale source records.

An exception path should explain which mismatches can be resolved through additional evidence or authorized corroboration and which require correction at the source.

Avoid encouraging staff to edit authoritative evidence merely to make fields match.

## Accessibility

Exception handling is part of an accessible proofing design. Applicants should have a way to learn that alternatives exist and how to request them without publicly disclosing sensitive personal circumstances.

Where possible, provide multiple evidence, validation, verification, and proofing options before the applicant reaches a dead end.

An accommodation should preserve the required proofing objective rather than simply removing a control.

## Fraud indicators during exceptions

Exception processes can attract social engineering because they appear to offer flexibility. Escalate when the case includes:

- contradictory evidence;
- repeated attempts with changing identities;
- pressure to skip required documentation;
- forged-media indicators;
- coercion or scripted answers;
- a reference who appears to control the applicant; or
- suspicious linkage to prior fraudulent applications.

Do not disclose detailed fraud-detection rules to the applicant.

## Session records

For a trusted-referee session, NIST requires records including the reason the referee was used, identity of the referee, evidence presented, processes completed, and the referee's decision and rationale for a negative decision.

More generally, an exception record can include:

- exception category;
- approved mechanism;
- staff or referee involved;
- evidence classes used;
- significant risk signals;
- decision and rationale; and
- follow-up or remediation required.

Store sensitive evidence only in systems approved for identity-proofing data.

## Quality and fairness review

Periodically review exception data for:

- groups disproportionately failing the standard flow;
- recurring device or source failures;
- trusted-referee usage and outcomes;
- unexplained differences between reviewers;
- fraud rates associated with exception methods;
- accessibility barriers; and
- applicants repeatedly cycling through unresolved exceptions.

Use the results to improve the main proofing process as well as the exception path.

## Sources

- NIST — SP 800-63A Revision 4, Digital Identity Guidelines: Identity Proofing and Enrollment: https://pages.nist.gov/800-63-4/sp800-63a.html
- NIST — Identity Proofing Requirements, Exception and Error Handling: https://pages.nist.gov/800-63-4/sp800-63a/ial-general/
- NIST CSRC — SP 800-63A-4 final publication: https://csrc.nist.gov/pubs/sp/800/63/A/4/final

## Scope note

This article describes project-neutral support governance for identity-proofing exceptions. It does not claim a particular service meets a NIST IAL and does not authorize undocumented reductions in assurance requirements.