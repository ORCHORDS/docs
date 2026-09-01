# CMMI Appraisal Evidence File

A CMMI maturity or capability claim is only as useful as the records behind it. This article defines a structured evidence file — a register of appraisal claims and their supporting documents — that an organization maintains for its own appraisals and that a buyer or auditor can use to verify claims made to them. Each register entry captures the essentials: appraised scope, model version, appraisal method class, date, maturity or capability rating, validity period, and any action-plan re-appraisal that remediated findings from a prior attempt.

## Scope

This article covers the structure, population, and maintenance of a CMMI appraisal evidence file: what claims are registered, what documents substantiate each field, how action-plan re-appraisals and expiries are recorded, and how the file is used in bids, audits, and customer verification requests. It covers both first-party files (an organization's own appraisal history) and counterparty files (claims received from suppliers). It does not cover conducting the appraisal itself, preparing practice instantiations, or interpreting maturity levels for supplier selection.

## Workflow or implementation guidance

Open one register entry per appraisal event. An entry is created when an appraisal is scheduled and completed through its lifecycle; it is never edited destructively — corrections are appended so the history of the claim stays auditable.

**Entry fields.** Record: (1) claim identifier and owner; (2) appraised organization name and the organizational unit, sites, and functions in scope; (3) model version and constellation or view (for example, CMMI V2.0 with specific view); (4) appraisal method and class (benchmark-class versus lower-rigor classes); (5) start and end dates of the appraisal; (6) maturity level or capability level profile awarded; (7) lead appraiser identity and team size; (8) sponsor; (9) validity start and expiry dates per the applicable CMMI Institute policy; (10) published result identifier or disclosure statement reference; (11) findings summary and any weaknesses identified; (12) action-plan re-appraisal linkage where applicable; and (13) file status (current, expiring, expired, superseded).

**Action-plan re-appraisals.** Where an appraisal fails to achieve the target level or identifies weaknesses requiring remediation, organizations may execute a documented action plan and undergo a targeted re-appraisal. Register the re-appraisal as a child entry of the original: reference the parent entry, list the weaknesses addressed, the corrective actions taken with completion dates, the re-appraisal date and scope, and the resulting rating. The chain must read coherently — a current rating that exists only because of a re-appraisal should be traceable to the original attempt without leaving the file.

**Counterparty claims.** When a supplier submits a CMMI claim, create an entry of the counterparty type: capture the claim as made, the verification source checked (published appraisal record), the verification date, and the verdict (verified, partially verified, unverifiable). Do not let an unverified counterparty claim sit in the same state as a verified one; the register's purpose is to make the difference visible at a glance.

**Expiry monitoring.** Set review reminders at twelve, six, and three months before each entry's expiry. For entries load-bearing in active bids or contracts, the three-month reminder should trigger either a re-appraisal decision or a communication plan for customers who rely on the rating.

**Use in bids.** When a bid cites a maturity level, cite the register entry identifier rather than restating the claim freehand. This forces the bid text to inherit the register's scope and dates and prevents the common drift where marketing prose widens an appraised scope.

## Controls

The register is access-controlled with change history enabled. Every current entry must link to a source document (appraisal disclosure statement, published result, or sponsor confirmation) stored in the same file structure. Claims without sources cannot hold "verified" status. Bid and contract templates that reference CMMI ratings pull the rating, scope, and validity window from the register, not from memory. An annual reconciliation confirms each entry's status and archives expired entries with a clear "expired" banner rather than deletion.

## Validation evidence

The file contains, per entry: the appraisal disclosure or summary result, scope description, model version evidence, lead appraiser details, the published result reference and verification capture, expiry computation with the policy basis, action-plan documents and re-appraisal records where applicable, and the reconciliation log. Validation testing samples entries and reconstructs each claim end to end — from the rating stated in a recent bid back through the register to the source document — confirming dates, scope, and version match at every step.

## Failure modes and correction

- **Stale entry presented as current.** An expired appraisal still cited in bids. Correction: mark expired, sweep bids and templates for citations, and communicate corrected status to affected customers.
- **Scope creep in citations.** Bid text claims an entity-wide rating for a single-unit appraisal. Correction: correct the citation to the register scope and re-issue; add template language locking citations to entry identifiers.
- **Broken re-appraisal chain.** The current rating's parent entry is missing. Correction: reconstruct from sponsor records and appraiser correspondence; if unrecoverable, downgrade the entry to partially verified.
- **Unverified counterparty claims pooled with verified ones.** Correction: add the verdict field to the register view used in procurement scoring and re-score.
- **Wrong expiry computed.** Expiry tracked from the wrong event date. Correction: recompute from the policy-basis document and adjust reminders.

## Limitations

The register documents and organizes claims; it does not make the underlying appraisal more or less valid, and a complete file can still contain a genuinely weak rating. CMMI Institute policies on validity periods, appraisal classes, and result publication change between model generations, so expiry rules in the file must be re-checked against current official guidance rather than copied forward. Counterparty verification depends on what suppliers and publishers make available.

## Canonical sources

- ISACA / CMMI Institute, *Appraisals — performance results and published records*: https://cmmiinstitute.com/appraisals
- ISACA / CMMI Institute, *CMMI: capability maturity model integration overview*: https://cmmiinstitute.com/cmmi
