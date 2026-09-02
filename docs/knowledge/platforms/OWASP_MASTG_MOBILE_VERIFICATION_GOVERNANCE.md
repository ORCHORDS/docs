# OWASP MASVS/MASTG Mobile Verification Governance

## Purpose

Govern the application of the OWASP Mobile Application Security Verification Standard (MASVS) and the Mobile Application Security Testing Guide (MASTG) so that mobile application security verification uses a current, standard framework with defined requirements, reproducible test cases, and evidence-backed results rather than ad-hoc checklists.

## Scope

Applies to every native and hybrid mobile application the studio ships, on iOS and Android. Covers MASVS verification level selection, MASTG test application, and evidence requirements for verification results. Does not cover server-side API security (covered by API security guidance) or mobile device management.

## Workflow

1. Select the MASVS verification profile — L1 (standard security), L2 (defense-in-depth), or the resilience-focused requirements (R) — based on data sensitivity and threat model; record the rationale per application.
2. Map each applicable MASVS requirement to the MASTG test cases that verify it; the MASTG provides the test procedures, the MASVS the requirements being verified.
3. Execute verification per MASTG test procedure and record evidence: tool output, screenshots, or dynamic-analysis captures sufficient for an independent reviewer to reproduce the result.
4. Classify each requirement pass, fail, or not-applicable with the justification; "not-applicable" requires a reason tied to the application's architecture, not convenience.
5. Feed failures into the application's remediation backlog with severity derived from the MASVS category and the application's data classification.
6. Re-verify on major releases and when the threat model changes; MASVS/MASTG revisions are tracked and the verification plan updated on publication of new versions.
7. Store verification records so they satisfy audit needs: application version, platform, tool versions, and tester identity.

## Controls and evidence

- Per-application verification plan stating MASVS profile, scope, and platform coverage.
- Test execution records mapping each MASVS requirement to MASTG test cases and evidence.
- Remediation backlog entries for failures with severity and target dates.
- Re-verification triggers and completion records per application.

## Validation

- Sample 10 verification results and confirm each has reproducible evidence and a defensible pass/fail/not-applicable classification.
- Confirm each application's selected MASVS profile matches its data classification and threat model.
- Confirm re-verification occurred after the last major release or documented change trigger.

## Failure correction

- **Verification result without evidence** → invalidate the result, re-execute the MASTG test case, and record proper evidence.
- **Profile too weak for the data handled** → raise the profile, re-plan verification, and run the delta requirements before the next release.
- **MASTG test obsolete after platform change** → update the test procedure, re-run affected requirements, and record the version transition.

## Limitations

- MASVS/MASTG target application-level security; platform store policies and device-level threats need separate controls.
- Reverse engineering resistance (resilience requirements) raises engineering cost and is never absolute; apply where threat model justifies.
- Tooling versions affect dynamic-analysis results; record them with the evidence.

## Scope note

This article is part of the platforms leaf. Cross-reference: `OWASP_CLOUD_NATIVE_TOP_10_GOVERNANCE.md`, `OWASP_API_SECURITY_TOP_10_2023_GOVERNANCE.md` (security leaf), and `CLOUDFLARE_RULESET_PHASE_ORDER_GOVERNANCE.md`.

## Canonical sources

- OWASP MASVS — Mobile Application Security Verification Standard: https://mas.owasp.org/MASVS/
- OWASP MASTG — Mobile Application Security Testing Guide: https://mas.owasp.org/MASTG/
- OWASP — Mobile Security Project: https://owasp.org/www-project-mobile-security/
- NIST SP 800-163 Rev 1 — Vetting the Security of Mobile Applications: https://csrc.nist.gov/pubs/sp/800/163/r1/final
- OWASP Mobile Top 10: https://owasp.org/www-project-mobile-top-10/
