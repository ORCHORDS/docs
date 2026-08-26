# NIST SP 800-171Ar3 assessment evidence traceability

**Issue:** Evidence folders organized by screenshots instead of assessment objectives make it impossible to show which determination was tested, whether evidence is current, and why a result is satisfied.

**Date:** 2026-08-17
**Author:** ORCHORDS
**Status:** documented

## Decision

Structure CUI assessment evidence around final NIST SP 800-171A Revision 3 determination statements and the exact SP 800-171r3 baseline/ODPs in scope.

## Evidence record

For each determination capture requirement and objective ID, system/component, assessment method, object examined, people interviewed, mechanism tested, ODP value, time window, evidence URI/digest, collector, result, anomaly, and reviewer.

## Workflow

1. Freeze scope, final revision, tailoring, and ODP catalog.
2. Generate an objective matrix from authoritative machine-readable NIST data where practical.
3. Plan examination, interview, and test activities based on risk and assessment scope.
4. Collect primary evidence with timestamps and provenance; redact unnecessary CUI and secrets.
5. Record `satisfied` only when the determination is met; use `other than satisfied` for anomalies or insufficient information.
6. Link remediation and retest evidence without overwriting original findings.
7. Apply retention, access, and secure-destruction requirements to the package.

## Verification

Reperform a sample test from the record, recompute evidence digests, trace every objective to a result, and confirm no result relies solely on self-assertion. Independently review inherited controls.

## Gotchas

A policy document does not prove operation. “Other than satisfied” can mean insufficient evidence, not only a confirmed defect. Evidence itself may contain CUI and needs protection.

## Sources

- [NIST SP 800-171Ar3 HTML publication](https://nvlpubs.nist.gov/nistpubs/SpecialPublications/800-171Ar3/NIST.SP.800-171Ar3.html)
- [NIST final revisions announcement](https://www.nist.gov/news-events/news/2024/05/nist-issues-updated-security-requirements-and-assessment-procedures)
