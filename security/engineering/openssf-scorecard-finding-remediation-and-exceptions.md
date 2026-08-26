# OpenSSF Scorecard finding remediation and exceptions

**Issue:** OpenSSF Scorecard is often reduced to a badge or aggregate number, causing teams to chase points without validating individual findings, threat relevance, or safe remediation.

**Date:** 2026-08-17
**Author:** ORCHORDS
**Status:** documented

## Decision

Use OpenSSF Scorecard as a repeatable heuristic assessment for owned repositories and dependency review. Triage individual checks and evidence; never treat the aggregate score as certification or a substitute for threat modeling.

## Workflow

1. Run a pinned Scorecard release in a minimally privileged workflow.
2. Store machine-readable results and commit identity.
3. Triage high-risk checks first, including dangerous workflows, token permissions, branch protection, pinned dependencies, signed releases, and unresolved vulnerabilities.
4. Reproduce each finding against current repository settings and files.
5. Open a scoped remediation issue with the check, evidence, owner, target state, test, and rollback.
6. Where remediation is infeasible, record an owned, expiring exception and compensating control.
7. Rerun after the change and retain before/after evidence.
8. Monitor score and individual-check regressions; do not fail builds solely on aggregate movement without policy.

## Verification

- Confirm workflow `GITHUB_TOKEN` permissions are read-only unless a documented step requires more.
- Pin action dependencies to full commit SHAs and automate reviewed updates.
- Test a known-bad fixture to ensure results surface in the Security tab or selected report.
- Independently verify organization settings that public scanning cannot fully observe.
- Review tool-version changes because check criteria evolve.

## Gotchas

Public data can be stale or incomplete. Some checks require permissions unavailable to an external scan. A high score does not establish artifact safety, and indiscriminate fixes can break release automation.

## Sources

- [OpenSSF Scorecard project](https://github.com/ossf/scorecard)
- [OpenSSF Scorecard check documentation](https://github.com/ossf/scorecard/blob/main/docs/checks.md)
