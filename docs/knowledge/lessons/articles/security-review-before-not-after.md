# security-review-before-not-after

**Issue:** Security reviews performed after a feature ships find vulnerabilities that are expensive to fix and may already be exploited
**Date:** 2026-08-11
**Status:** documented

## What happened
A file upload feature was shipped to production. A security review was "planned for next sprint." Before the review happened, a researcher discovered that uploaded files were served directly from a publicly accessible URL with no content-type validation — enabling stored XSS via SVG uploads. By the time the review completed and the fix shipped, the vulnerability had been live for six weeks.

## The lesson
Security reviews must be a gate before production, not a follow-up task after shipping. Threat modeling should happen during design. Automated security scanning (SAST, dependency audit, secrets detection) should run in CI. A human security review should be a pull request requirement for high-risk features (auth, file handling, payment, PII).

## Why it matters
The cost of fixing a vulnerability grows exponentially after shipping: re-engineering an already-deployed feature, potential breach notification, regulatory scrutiny, and customer trust damage. Pre-ship review costs almost nothing by comparison.

## How to apply
- [ ] Add security review as a required PR check for features that touch: auth, file uploads, payment, PII storage, or external inputs.
- [ ] Run SAST tools (Semgrep, Snyk, Bandit) in CI on every PR.
- [ ] Conduct a threat model during technical design for any new data flow.
- [ ] Create a security-review checklist specific to your stack and include it in the PR template.
- [ ] Never mark a security-review task as "post-launch" — treat it as a launch blocker.

## Related
- `pen-test-surprises-are-expensive.md`
- `open-source-dependency-audit.md`
- `never-store-secrets-in-env-files.md`
