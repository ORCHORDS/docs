# shift-left-security-testing

**Issue:** Security vulnerabilities are found in production or in a final security review, making them expensive to fix
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
The security team reviews code weeks after it's written. They find SQL injection risks, insecure deserialization, or missing auth checks. Fixing them requires revisiting design decisions that are now baked in.

## Pattern / Solution
"Shift left" means moving security testing earlier in the development lifecycle — into the developer's local workflow and CI pipeline.

**Layer 1: Developer's machine (pre-commit)**
- SAST (Static Application Security Testing): `semgrep`, `bandit` (Python), `gosec` (Go), `eslint-plugin-security` (JS)
- Secret scanning: `gitleaks` or `trufflehog` as a pre-commit hook
- Dependency audit: `npm audit`, `pip-audit`, `trivy` for container images

**Layer 2: CI pipeline**
- SAST scan on every PR — fail the build on high-severity findings
- Dependency vulnerability scan (e.g. Dependabot, Snyk, or OSV-Scanner)
- Container image scan before push to registry
- License compliance check (SBOM generation)

**Layer 3: Design phase**
- Threat modeling for new features: "what can an attacker do with this?"
- Checklist in the Definition of Ready: "Have we considered auth, input validation, and data exposure?"

**Threat modeling lightweight approach (STRIDE per feature):**
- Spoofing: Can someone impersonate a user or service?
- Tampering: Can data be modified in transit or at rest?
- Repudiation: Can actions be denied without a log?
- Information disclosure: What sensitive data is exposed?
- Denial of service: What can be exhausted or abused?
- Elevation of privilege: Can a low-privileged user gain higher access?

## Gotchas
- SAST produces false positives — tune rules before mandating zero-findings builds
- Secret scanning must be in pre-commit, not just CI; a committed secret is already leaked
- Security left to a single "security sprint" is not shifting left — it's just a later review

## Related
- `dependency-upgrade-workflow.md`
- `definition-of-done-checklist.md`
- `sbom-slsa-2026.md`
