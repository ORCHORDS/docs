# W3C WCAG 2.2 Version Transition Governance

## Purpose

This article describes how an organisation records, governs, and transitions between versions of **Web Content Accessibility Guidelines (WCAG) 2.2**, published as a W3C Recommendation on **12 December 2024** by the W3C Accessibility Guidelines Working Group (AG WG). WCAG 2.2 builds on WCAG 2.0 (2008) and WCAG 2.1 (2018) by adding success criteria, providing guidance, and clarifying conformance. WCAG 2.2 does not deprecate or supersede WCAG 2.0 or WCAG 2.1; content that conforms to WCAG 2.2 also conforms to WCAG 2.0 and WCAG 2.1.

The article is governance guidance. It is not a substitute for the W3C Recommendation, the AG WG publications, or the organisation's accessibility conformance documentation.

## Scope

WCAG 2.2 is a W3C Recommendation that defines how to make web content more accessible to people with disabilities. WCAG 2.2 is backwards-compatible with WCAG 2.0 and WCAG 2.1: a website that conforms to WCAG 2.2 also conforms to the earlier versions. WCAG 2.2 adds nine success criteria to the prior total (now 86 success criteria across levels A, AA, and AAA), grouped into the familiar four principles (perceivable, operable, understandable, robust) and the same POUR-aligned guideline structure.

The W3C Web Accessibility Initiative (WAI) maintains WCAG and the supporting techniques documents, accessibility understanding documents, and conformance evaluation methodology. WCAG does not stand alone: it is typically used alongside the WAI-ARIA specification, the Authoring Tool Accessibility Guidelines (ATAG), the User Agent Accessibility Guidelines (UAAG), and the WAI Mobile Accessibility Mapping.

## Version governance workflow

### 1. Pin the operative WCAG version, level, and date consulted

Every reference to WCAG in policy, accessibility statements, audit reports, conformance claims, customer-facing material, or procurement documents should record the exact WCAG version (for example, WCAG 2.2), the conformance level claimed (A, AA, or AAA), and the date the version was consulted. The W3C/TR/ publication URL encodes the publication date (for example, https://www.w3.org/TR/2024/REC-WCAG22-20241212/) and is sufficient to reconstruct the Recommendation date consulted.

A reference that cites "WCAG 2.0" or "WCAG 2.1" remains valid but should be retained alongside the operative WCAG 2.2 reference where the deployment has been assessed against WCAG 2.2.

### 2. Capture the WCAG 2.2 transition explicitly

A transition from WCAG 2.1 to WCAG 2.2 should record:

- the new WCAG 2.2 success criteria (nine new criteria across A and AA);
- the success criteria that have been removed or restructured, if any;
- the success criteria whose guidance has been clarified (for example, focus appearance, dragging movements, target size, focus not obscured, redundant entry, accessible authentication, page break navigation); and
- the disposition of existing accessibility audit results that predate WCAG 2.2.

The transition delta should be retrievable for the duration of any accessibility audit or contractual commitment that pre-dated the WCAG 2.2 Recommendation.

### 3. Update accessibility statements and conformance evidence

An accessibility statement that claims conformance with WCAG 2.2 should be re-issued after the conformance assessment, and the previous accessibility statement should be retained. Customer-facing claims about WCAG conformance should record the operative WCAG version, the conformance level, the assessment date, and the assessor (internal or external).

### 4. Distinguish WCAG conformance from WCAG validation by an external auditor

WCAG does not, on its own, define a certification scheme. WCAG conformance is typically assessed by internal accessibility teams, external accessibility consultants, or conformance evaluation programmes. A claim that a website "conforms to WCAG 2.2 AA" should be accompanied by the assessment methodology, the date of the assessment, the assessor, and the scope of the assessment (page types, content types, user journeys).

Confusion between WCAG conformance and a third-party WCAG certification programme is a frequent claim-related failure mode. Some jurisdictions (for example, EU Member States implementing the Web Accessibility Directive, the UK Equality Act 2010, the ADA Title III in the US, or the EN 301 549 harmonised European standard) require accessibility conformance that is referenced against a specific WCAG version. The operative jurisdiction and its WCAG version reference should be recorded alongside the conformance claim.

### 5. Coordinate with EN 301 549 and sectoral accessibility regulation

EN 301 549 is the European harmonised standard for accessibility requirements for ICT products and services. EN 301 549 incorporates WCAG and other accessibility requirements by reference. The current published EN 301 549 edition incorporates WCAG 2.1 by reference; an updated edition or amendment that incorporates WCAG 2.2 may be published. Governance documentation should record the operative EN 301 549 edition alongside the operative WCAG version.

Sectoral accessibility regulation (for example, the European Accessibility Act, the US Section 508 refresh, the UK PSBAR, or the Canadian ACA) should be tracked independently of WCAG, and governance documentation should record each operative edition.

### 6. Sequence accessibility audits across WCAG versions

Accessibility audit programmes should record the WCAG version consulted for each audit, the audit date, the auditor, the scope, the conformance level assessed, and the findings. Where the WCAG version is updated between audits, the audit programme should be refreshed, and the previous audit results should be retained under the version they were assessed against.

### 7. Preserve historical evidence under the WCAG version it was created for

Internal audit reports, automated scan results, accessibility test reports, and remediation records that were assessed against WCAG 2.0 or WCAG 2.1 should remain labelled with the version under which they were created. Reinterpreting legacy findings against WCAG 2.2 without preserving the original version breaks traceability.

### 8. Monitor amendments, errata, and W3C AG WG output

The W3C Accessibility Guidelines Working Group may publish Candidate Amendments, errata, or new techniques documents that affect interpretation of WCAG 2.2. Governance should subscribe to the AG WG publications feed and the W3C Web Accessibility Initiative publications. A change-log artefact should record the date of each change, the operative WCAG version affected, and the affected success criteria.

## Controls and evidence

Version-transition evidence typically includes:

- a dated version register recording the WCAG version consulted for each artefact;
- a transition delta document listing the new WCAG 2.2 success criteria, the removed or restructured criteria, and the criteria whose guidance has been clarified;
- a re-issued accessibility statement under the operative WCAG version and conformance level;
- accessibility audit reports stored with the WCAG version reference and the conformance level assessed;
- automated scan reports stored with the WCAG version reference and the rule set version consulted;
- conformance methodology documentation (manual testing, automated testing, assistive-technology testing) stored with the version reference;
- training and competency records showing staff were briefed on the WCAG 2.2 success criteria; and
- a change-log capturing W3C AG WG amendments, errata, and techniques documents.

## Validation

Validation that web content continues to meet WCAG 2.2 requirements typically draws on:

- internal audits conducted against the operative WCAG version by auditors trained on the WCAG 2.2 success criteria;
- external accessibility audits conducted by accredited or recognised accessibility consultants;
- automated scans using rule sets that have been updated for WCAG 2.2 (for example, axe-core, WAVE, Accessibility Insights, pa11y);
- assistive-technology testing using current versions of screen readers, screen magnifiers, voice-control software, and other assistive technologies;
- user-testing sessions with people with disabilities, where the user testing protocol records the operative WCAG version;
- W3C WAI techniques and understanding documents consulted during the assessment; and
- where applicable, conformance evaluation programmes (for example, country-level WCAG conformance schemes or voluntary WCAG certification programmes).

## Failure correction

Common transition failures include:

- citing "WCAG" without a version, level, or assessment date in policy or customer-facing material;
- assuming WCAG 2.2 supersedes WCAG 2.1 and discarding WCAG 2.1 audit evidence without preserving it;
- treating WCAG conformance as equivalent to a third-party certification when no certification programme was used;
- conflating WCAG conformance with jurisdiction-specific accessibility regulation;
- failing to update automated scan rule sets and manual test protocols to the operative WCAG version;
- treating accessibility as a one-off project rather than a recurring programme;
- losing historical evidence under the WCAG version it was created for;
- making accessibility claims about content that has not been re-assessed under the operative WCAG version; and
- ignoring W3C AG WG amendments, errata, or techniques documents.

A corrective action should document the WCAG version under which the failure occurred, the operative WCAG version that should have been used, the disposition of historical evidence, and the owner of the re-issued artefact.

## Limitations

WCAG 2.2 is a W3C Recommendation, not a regulation. Conformance with WCAG 2.2 does not equate to compliance with jurisdiction-specific accessibility regulation, with the European Accessibility Act, with the US ADA Title III, with the UK Equality Act 2010, or with sectoral accessibility rules. WCAG 2.2 does not on its own mandate specific technologies, design patterns, or assistive-technology pairings.

WCAG 2.2 does not supersede WCAG 2.1 or WCAG 2.0. WCAG 2.0 and WCAG 2.1 remain in effect, and content that conforms to WCAG 2.2 also conforms to those earlier versions. The governance transition is largely additive (new success criteria, new techniques) rather than a deprecation cycle.

## Canonical sources

- W3C — *Web Content Accessibility Guidelines (WCAG) 2.2*, W3C Recommendation, 12 December 2024: https://www.w3.org/TR/WCAG22/
- W3C — *Web Content Accessibility Guidelines (WCAG) 2.1*, W3C Recommendation: https://www.w3.org/TR/WCAG21/

## Scope note

This article describes version and reference governance for WCAG 2.2. It does not reproduce the WCAG Recommendation, declare conformance, or substitute for the W3C Recommendation, the AG WG publications, or the organisation's accessibility conformance documentation.