# W3C Recommendation-Track Transition Governance

## Purpose

W3C technical reports can exist at different maturity levels. A reference to “the W3C specification” is therefore incomplete unless it records the document, dated publication, and maturity status used for the decision.

This article provides a public, project-neutral method for separating experimentation from conformance baselines and for governing transitions between Recommendation-track publications.

## Current process context

The W3C Process dated 18 August 2025 identifies the Recommendation-track maturity levels as **Working Draft**, **Candidate Recommendation**, and **W3C Recommendation**. Candidate Recommendations can be published as Drafts or Snapshots.

Advancement is not automatic. Transition requirements, review, implementation experience, and resolution of objections affect progression. A document can also regress, be revised, abandoned, rescinded, obsoleted, superseded, restored, or otherwise retired.

A Working Draft communicates work in progress. It must not be represented as a W3C Recommendation or as proof of conformance to a final standard. An Editor's Draft can be useful for development visibility, but it is not a substitute for a dated W3C technical-report publication when recording an adoption baseline.

## Governance workflow

### 1. Record an exact publication

For every adopted W3C document, record:

- the specification title and level;
- the canonical and dated publication URLs;
- the publication date and maturity status;
- the adoption date, owner, and approved use;
- relevant implementation reports, test suites, errata, and amendments; and
- the preceding baseline and migration rationale.

Preserve the dated URL in evidence. A generic latest-version link can change after an assessment and is not sufficient by itself to reproduce the decision.

### 2. Separate experimentation from a conformance baseline

Working Draft or Editor's Draft features should require an explicit experimental decision. Define affected users, interoperability assumptions, fallback behavior, data or protocol changes, and removal or promotion criteria. Public claims should identify the feature as draft work rather than implying Recommendation status.

Use a Recommendation as the ordinary conformance baseline where one exists, unless the relevant conformity model or procurement requirement says otherwise. Recommendation status alone does not prove that a product conforms.

### 3. Define transition gates

Before moving to a newer maturity level or dated publication:

1. compare normative and behaviorally significant changes;
2. inventory implementations, dependencies, extensions, and test coverage;
3. run interoperability, accessibility, privacy, and security review appropriate to the technology;
4. test migration and fallback paths;
5. update public and internal version claims; and
6. approve known gaps with an owner and review date.

A transition gate should rely on evidence from the publication and implementation ecosystem, not on an assumption that later always means compatible.

### 4. Monitor status changes

Assign an owner to monitor the technical-report page, Working Group publications, errata, amendments, and supersession notices. Reassess the baseline when a publication advances, regresses, is replaced, or is retired. Preserve historical evidence under the status it had when the decision was made.

## Evidence record

A review packet should contain the dated source snapshot, maturity classification, change assessment, implementation or interoperability results, unresolved issues, approved exceptions, communication changes, and final decision. It should distinguish statements copied from the publication from organization-specific interpretations.

## Failure modes

- Calling a Working Draft a standard overstates its maturity.
- Using only an Editor's Draft loses a stable, dated adoption reference.
- Assuming every document progresses linearly ignores regression, abandonment, and supersession.
- Treating Recommendation status as proof of implementation conformance skips testing and evidence.
- Updating a generic link without preserving the prior dated publication makes an audit irreproducible.
- Shipping draft behavior without fallback or removal criteria creates an unmanaged compatibility commitment.

## Sources

- W3C Process, 18 August 2025, Recommendation Track: https://www.w3.org/policies/process/20250818/#rec-track
- W3C Technical Reports and Specifications: https://www.w3.org/TR/

Sources were checked on September 1, 2026.

## Scope note

This article describes publication-status and transition governance. It does not reproduce the W3C Process, declare conformance, or replace the operative Process Document or a specification's normative text.
