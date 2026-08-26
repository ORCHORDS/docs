# Dependabot pull requests and GitHub Actions security

**Date:** 2026-08-26
**Status:** documented
**Source:** https://docs.github.com/en/code-security/tutorials/secure-your-dependencies/automate-dependabot-with-actions

## Context

Dependabot pull requests can trigger GitHub Actions, but automated dependency-update events have distinct trust and permission behavior. Treat them as automation-originated changes rather than ordinary maintainer pushes.

## Pattern

- Keep workflows triggered by Dependabot least-privileged.
- Do not assume secrets available to normal pushes will be available or appropriate for dependency-update PRs.
- Separate analysis/testing from privileged deployment or publishing actions.
- Require deterministic tests and policy checks before auto-merge.
- Base automation decisions on Dependabot metadata and repository policy, not on untrusted dependency-controlled text.

## Important GitHub behavior

GitHub documents that Dependabot itself runs on GitHub Actions when enabled, even if normal Actions policy configuration would otherwise disable Actions. This is a platform behavior to account for in threat modeling and governance.

## Verification

Create a safe test dependency update and inspect the event actor, token permissions, available secrets, triggered jobs, and any merge/deploy path. Confirm a Dependabot PR cannot directly obtain privileges reserved for trusted release workflows.
