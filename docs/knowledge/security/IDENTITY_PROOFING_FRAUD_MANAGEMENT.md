# Identity-Proofing Fraud Management

## Purpose

NIST SP 800-63A-4 requires credential service providers (CSPs) to operate an identity-proofing fraud-management program rather than treating fraud checks as isolated vendor features. The program spans fraud identification, detection, investigation, reporting, resolution, privacy review, redress, relying-party coordination, agent training, insider-risk controls, and measurement of control effectiveness.

This guidance provides a reusable governance pattern for remote and attended identity-proofing services without assuming any particular fraud vendor or implementation.

## Program requirement

A CSP should document its fraud-management practices in the applicable practice statement and keep them aligned with the identity-proofing processes actually used in production.

A useful program scope includes:

- fraud-risk identification;
- preventive and detective controls;
- investigation procedures;
- escalation and case ownership;
- applicant self-reporting;
- confirmed-fraud handling;
- communication to affected relying parties (RPs);
- correction and redress;
- control testing and monitoring;
- staff and proofing-agent training; and
- insider and collusion risks.

Do not describe a fraud program solely by listing data providers or automated scores. Governance needs to explain what decisions are made from those signals and what happens when they are wrong.

## Privacy risk assessment

SP 800-63A-4 requires privacy-risk assessment before deploying fraud checks and fraud-mitigation technologies that process applicant or subscriber information.

For each material fraud control, document:

- purpose of the check;
- personal data used;
- source of the data;
- retention period;
- access controls;
- third-party processors;
- whether the check creates sensitive inferences;
- false-positive consequences;
- applicant notice or transparency obligations; and
- deletion or correction processes.

A control can reduce fraud while still creating disproportionate privacy or exclusion risk. Those trade-offs need explicit review.

## Applicant self-reporting

Provide a practical mechanism for individuals to report suspected identity-proofing fraud involving their information.

A reusable workflow is:

1. accept the report through a documented support or fraud channel;
2. authenticate the reporter appropriately for the information that will be disclosed or changed;
3. preserve relevant proofing and account evidence;
4. investigate the reported event;
5. contain confirmed abuse;
6. notify affected parties where required;
7. correct records and credentials where appropriate; and
8. explain available redress to the affected individual.

Self-reporting should not require the victim to repeat the compromised proofing path if doing so would be unsafe or ineffective.

## High-risk indicators

NIST requires CSPs to analyze remote identity-proofing channels for high-risk indicators appropriate to the operating environment.

Signals can include, where justified:

- suspicious device characteristics;
- unusual network or geographic patterns;
- repeated failed proofing attempts;
- identity-data reuse across multiple applicants;
- abnormal application velocity;
- known fraud indicators from authoritative or credible sources;
- recent changes in telecommunications or account information;
- inconsistencies between evidence and applicant behavior; and
- transaction or behavioral anomalies relevant to the service.

A single signal should not automatically become a universal fraud rule. Document weighting, thresholds, exceptions, and known limitations.

## Authoritative-source query leakage

Identity proofing often asks an authoritative or credible source whether applicant data matches a record. The interaction must not let an attacker efficiently infer or enumerate protected source data.

Design checks so applicants cannot learn the accuracy of hidden attributes by repeatedly varying guesses and observing overly specific responses.

Useful safeguards include:

- limit the detail returned from source comparisons;
- rate-limit repeated probing;
- detect systematic attribute enumeration;
- avoid revealing which exact field failed when that creates unnecessary leakage; and
- separate applicant-facing error messages from internal diagnostic detail.

Error handling should remain understandable enough for legitimate applicants to use redress or correction channels.

## Death-record checks

SP 800-63A-4 requires CSPs to check authoritative death records during identity proofing where the applicable NIST requirement applies.

A death-record match needs careful handling. Data can be delayed, erroneous, incomplete, or associated with identity theft involving a deceased person.

A practical process should:

1. treat the match as a high-impact fraud/risk signal;
2. verify the source and record context;
3. avoid making unnecessary disclosures about third parties;
4. route disputed matches to redress or manual review; and
5. preserve enough evidence to explain the final decision.

Do not convert a database match into an irreversible automated decision without the review and correction path required by policy.

## Additional risk checks

Depending on risk, NIST identifies or recommends checks that can include areas such as:

- SIM-swap or telecommunications-risk information;
- tenure or account-age information;
- address or residency consistency;
- device fingerprinting;
- transaction analytics; and
- external fraud indicators.

Use only signals appropriate to the service and jurisdiction. Confirm current legal, privacy, fairness, and contractual constraints before adding a new data source.

## Monitoring control performance

Fraud controls need continuing measurement because attacker behavior, data quality, vendors, user populations, and generation technologies change.

Track, where useful:

- confirmed fraud detected;
- confirmed fraud missed;
- false-positive rate;
- manual-review overturn rate;
- applicant abandonment after a fraud check;
- exception and redress outcomes;
- signal or model version;
- performance by channel; and
- material differences across relevant user populations.

A declining fraud rate does not automatically prove a control improved. It can also reflect reduced usage, attacker migration, or missing detection.

## Independent testing

NIST recommends independent evaluation of fraud controls.

Independent testing can assess:

- whether controls operate as documented;
- whether known attack patterns are detected;
- whether source data is current enough for its purpose;
- false-positive and false-negative behavior;
- whether manual-review and redress paths work;
- resilience against bypass and replay; and
- whether operators can override controls without appropriate accountability.

Retest after material changes to vendors, models, proofing architecture, evidence types, or risk assumptions.

## Proofing-agent training

Agents involved in identity proofing should understand fraud indicators relevant to the channel and the boundaries of their authority.

Training can include:

- manipulated or forged identity evidence;
- social-engineering indicators;
- coercion and distress signals;
- synthetic and stolen identities;
- forged or injected media;
- unusual applicant behavior;
- escalation criteria; and
- avoiding unsupported conclusions from one ambiguous signal.

Training records and qualification reviews should be kept current.

## Insider and collusion risk

SP 800-63A-4 requires controls for insider collusion where proofing personnel or process participants could facilitate fraudulent enrollment.

Examples of governance controls include:

- separation of duties for high-risk approvals;
- case-assignment controls;
- immutable or protected audit trails;
- supervisor review of defined exceptions;
- anomaly detection for unusual approval patterns;
- restrictions on self-assigned or related-party cases;
- conflict-of-interest disclosure; and
- periodic sampling of proofing decisions.

The exact safeguards should match the scale and threat model of the service.

## Communicating fraud to relying parties

When suspected or confirmed identity-proofing fraud affects an RP's trust decision, NIST requires appropriate communication to the RP.

Trust agreements should define:

- points of contact;
- reportable events;
- urgency and timing expectations;
- minimum information required for action;
- privacy restrictions;
- credential/session containment responsibilities; and
- follow-up and closure procedures.

Share enough information for the RP to protect affected accounts without exposing unrelated applicant data or sensitive fraud-detection internals.

## RP responsibilities

RPs that depend on a CSP's identity proofing have their own governance responsibilities.

A reusable RP review includes:

- designate a fraud point of contact;
- assess privacy and business risk associated with the proofing service;
- define required fraud-management capabilities in the trust agreement;
- periodically review CSP performance and material changes;
- integrate CSP fraud notifications with local account-security processes; and
- maintain a redress path for users affected by downstream decisions.

Federation or outsourcing does not eliminate the RP's responsibility to understand the risk it accepts.

## Failed fraud checks

A failed fraud check should invoke documented actions rather than an unexplained permanent denial.

SP 800-63A-4 requires CSPs to document the practices applied after fraud-control failures and to provide redress. NIST also recommends trusted-referee handling for certain unattended remote failures where that exception process is supported.

A useful decision tree can distinguish:

- confirmed fraud;
- high-confidence risk requiring specialized investigation;
- inconclusive automated result;
- likely data-quality error;
- applicant unable to satisfy a particular control; and
- false positive confirmed through attended or manual review.

Each outcome can require a different containment, exception, or redress path.

## Redress

Redress should let legitimate applicants challenge or correct an identity-proofing outcome without revealing information that would help attackers bypass controls.

Document:

- how applicants request review;
- identity and authorization checks for the review process;
- evidence accepted for correction;
- expected handling stages;
- escalation for sensitive cases;
- correction of subscriber-account records; and
- notification to affected RPs when a prior fraud conclusion changes materially.

## Evidence to retain

Where appropriate, retain:

- fraud-program policy and version;
- risk assessments;
- control inventory;
- vendor/source inventory;
- test and monitoring results;
- proofing-agent training records;
- investigation and disposition records;
- RP notifications;
- exception and redress outcomes; and
- dates of material program review.

Retention should follow privacy, legal, security, and audit requirements rather than assuming fraud data should be stored indefinitely.

## Sources

- NIST SP 800-63A-4 — Identity Proofing and Enrollment: https://pages.nist.gov/800-63-4/sp800-63a.html
- NIST SP 800-63 Revision 4 publication hub: https://pages.nist.gov/800-63-4/

## Scope note

This article summarizes reusable identity-proofing fraud-management governance from NIST SP 800-63A-4. It does not accuse any person of fraud, prescribe a specific fraud vendor, or claim that any ORCHORDS service implements a NIST-conformant fraud-management program.