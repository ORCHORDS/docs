---
title: OpenSSF Scorecard and SLSA Verification Tooling Version Governance
owner: Knowledge Engineering
status: approved
classification: public
last-reviewed: 2026-09-07
review-cycle: 180 days
next-review: 2027-03-06
source: https://scorecard.dev/ ; https://github.com/ossf/scorecard
---

# OpenSSF Scorecard and SLSA Verification Tooling Version Governance

## 1. Purpose

This reference card governs the lifecycle of the **OpenSSF Scorecard** action and the **SLSA Verifier** tool — the off-the-shelf assurance checkers that grade every open-source dependency we ship.

## 2. Scope

In scope:

- OpenSSF Scorecard action v2.4.x and the `scorecard-go` CLI.
- SLSA Verifier CLI v2.x.
- Scorecard checks relevant to our adoption: Dangerous-Workflow, Binary-Artifacts, Branch-Protection, Token-Permissions, Pinned-Dependencies, Code-Review, SAST, CI-Tests.
- SLSA Conformance test fixtures for Build L1/L2/L3.

Out of scope:

- Self-hosted scorecard services (we use the public scorecard.dev batch API).
- CodeQL quality checks (covered by separate tooling).

## 3. Versioning policy

- Pin the Scorecard GitHub Action to a specific SHA (e.g. `ossf/scorecard-action@c3c1f7e`) — no floating tags.
- Pin the SLSA Verifier CLI to a specific release; verify checksums against the SLSA provenance.
- Score ≥ 7.0 is the minimum acceptable baseline for `Critical` dependencies.
- Score < 5.0 in any dependency triggers a waiver request.

## 4. Compatibility matrix

| Scorecard | Go runtime | SLSA Verifier | Notes |
| --- | --- | --- | --- |
| 2.3.x | 1.22+ | 2.5.x | Token Permissions stable |
| 2.4.x | 1.23+ | 2.6.x | New "Contributors" check |
| 2.5.x (RC) | 1.24+ | 2.7.x (RC) | Adds attestation-based checks |

## 5. Check semantics

- **Branch-Protection**: branch protection MUST be enabled on the default branch with ≥ 1 required review.
- **Pinned-Dependencies**: third-party GitHub Actions MUST be pinned to a SHA, not a tag.
- **Binary-Artifacts**: release binaries MUST be built from source in CI; no uploaded binaries.
- **SAST**: code MUST be analysed by at least one SAST tool in CI.
- **Token-Permissions**: GitHub Actions tokens MUST be declared as read-only at the workflow level.

## 6. Waiver procedure

1. Open a waiver issue using the `scorecard-waiver` template.
2. Justify the gap, propose a remediation date within 90 days.
3. Approval requires the dependency owner + Security Engineering sign-off.
4. Waivers are tracked in `policies/supply-chain/scorecard-waivers.md`.

## 7. CI integration

- Trigger: pull_request on dependency manifests; weekly cron on all repositories.
- Output: SARIF upload to the GitHub Code Scanning dashboard.
- Failure thresholds: a regression of ≥ 1.0 in the repo-level score blocks the PR.

## 8. Upgrade procedure

1. Review the release notes for new and removed checks.
2. Run a one-week soak against the staging dependency set.
3. Roll the GitHub Action SHA and re-run the cron against the production dependency set.
4. Promote after 7 days of green reports.

## 9. Rollback procedure

- Revert the GitHub Action SHA to the previous pinned commit.
- Existing SARIF reports remain valid because the schema is backward compatible.

## 10. Observability

- Required metrics: `scorecard_run_total{repo,result}`, `scorecard_score{check,value}`, `slsa_verifier_total{level,result}`.
- Alert on `scorecard_score{check="Branch-Protection",value="0"}` for any `Critical` dependency.

## 11. References

- OpenSSF Scorecard — https://scorecard.dev/
- SLSA Verifier — https://github.com/slsa-framework/slsa-verifier
- SLSA conformance — https://github.com/slsa-framework/slsa-github-generator
