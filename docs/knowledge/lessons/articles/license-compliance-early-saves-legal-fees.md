# license-compliance-early-saves-legal-fees

**Issue:** GPL or copyleft licenses embedded in a commercial product through transitive dependencies trigger legal obligations discovered only at acquisition or audit
**Date:** 2026-08-11
**Status:** documented

## What happened
During due diligence for an acquisition, a buyer's legal team discovered that the target's core product contained a dependency licensed under AGPL-3.0. The AGPL requires any network-accessible application using the code to release its source. The product's source was the company's entire competitive moat. The acquisition was delayed six months for legal remediation and the valuation was reduced.

## The lesson
Check the license of every dependency — direct and transitive — before it enters the codebase. Maintain an approved-license list (MIT, Apache-2.0, BSD typically safe for commercial software) and a blocked list (GPL, AGPL require careful evaluation). Automate license scanning in CI.

## Why it matters
License violations are discovered at the worst moments: acquisitions, funding rounds, enterprise sales, and regulatory audits. Remediation is expensive when the infringing code is deeply embedded. Catching it at PR time costs nothing.

## How to apply
- [ ] Define an approved license list for your business model (consult a lawyer for your specific situation).
- [ ] Run a license scanner (FOSSA, licensee, `license-checker` for npm) in CI and block PRs that introduce unapproved licenses.
- [ ] Audit existing dependencies immediately if license scanning has never been run.
- [ ] For borderline licenses (LGPL, MPL), get a legal opinion before shipping.
- [ ] Maintain a `LICENSES.md` or SBOM (software bill of materials) updated with each release.

## Related
- `open-source-dependency-audit.md`
- `gdpr-by-design-not-retrofit.md`
