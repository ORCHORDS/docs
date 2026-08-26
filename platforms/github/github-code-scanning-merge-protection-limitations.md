# GitHub code-scanning merge protection limitations

**Issue:** A ruleset appears to require code scanning but does not cover merge-queue groups or certain Dependabot/default-setup pull requests.

**Date:** 2026-08-17
**Author:** ORCHORDS
**Status:** documented

## Controls

Configure required tools and security/error thresholds in rulesets; separately ensure scanning is enabled and healthy; add compensating required checks for uncovered flows; test ruleset targeting and bypass actors; monitor required-tool absence and analysis-in-progress states.

## Verification

Create canary PRs with a safe fixture at each threshold; exercise normal, merge queue, Dependabot, and bypass paths; confirm alerts lie in the PR diff; verify organization and repository rule interactions.

## Gotchas

GitHub states merge protection is not a status check, does not apply to merge queue groups, and excludes Dependabot PRs analyzed by default setup. It only blocks when all alert lines exist in the diff.

## Sources

- [GitHub Docs: Code scanning merge protection](https://docs.github.com/en/code-security/concepts/code-scanning/merge-protection)
- [GitHub Docs: Set merge protection](https://docs.github.com/en/code-security/how-tos/find-and-fix-code-vulnerabilities/manage-your-configuration/set-merge-protection)
