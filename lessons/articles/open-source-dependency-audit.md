# open-source-dependency-audit

**Issue:** Unaudited open-source dependencies introduce known vulnerabilities and supply-chain attack vectors
**Date:** 2026-08-11
**Status:** documented

## What happened
A Node.js application used a popular utility library that was compromised in a supply-chain attack (malicious maintainer published a new version with credential-stealing code). The application had no automated dependency scanning. The malicious version ran in production for 11 days before the npm advisory was published and an engineer happened to see it.

## The lesson
Every dependency is a trust decision. Automate vulnerability scanning in CI (npm audit, Snyk, Dependabot) and block merges that introduce known high or critical CVEs. Pin dependency versions and require a deliberate human decision to upgrade. Monitor security advisories for your direct and transitive dependencies.

## Why it matters
Modern applications have hundreds of transitive dependencies. Each is a potential attack vector. Unpatched known CVEs are the lowest-effort attack path for adversaries. Supply-chain attacks via compromised maintainers are an increasing threat that only automated monitoring can catch quickly.

## How to apply
- [ ] Run `npm audit`, `pip-audit`, or equivalent in CI — fail the build on high/critical CVEs.
- [ ] Configure Dependabot or Renovate to open PRs for security updates automatically.
- [ ] Pin all dependencies to exact versions (or lockfiles) so updates require explicit human action.
- [ ] Monitor advisory feeds (GitHub Security Advisories, NVD) for your stack.
- [ ] Review new dependencies before adding: check maintainer activity, download count, and recent release history.

## Related
- `supplier-breach-affects-you.md`
- `license-compliance-early-saves-legal-fees.md`
- `security-review-before-not-after.md`
