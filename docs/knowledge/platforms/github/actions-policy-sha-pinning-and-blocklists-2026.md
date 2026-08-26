# github-actions-policy-sha-pinning-and-blocklists-2026

**Issue:** CI executes third-party GitHub Actions referenced by mutable tags or ungoverned repositories.
**Date:** 2026-08-11
**Author:** ORCHORDS
**Status:** documented

## Symptom

A workflow uses `owner/action@v4` and a repository-level review cannot establish the immutable code that will run later. Security teams discover an unapproved action only after it executes in CI.

## Root cause

Workflow YAML is executable supply-chain configuration. Artifact provenance answers how a released artifact was built; Actions policy controls which third-party code may run before the build. Mutable tags do not provide the same reviewable identity as a full commit SHA.

**Source:** [GitHub Actions policy documentation](https://docs.github.com/en/organizations/managing-organization-settings/disabling-or-limiting-github-actions-for-your-organization) and [GitHub’s SHA-pinning/blocking announcement](https://github.blog/changelog/2025-08-15-github-actions-policy-now-supports-blocking-and-sha-pinning-actions/).

## Fix

- inventory external actions and reusable workflows;
- allow only required actions and explicitly deny prohibited publishers or actions;
- pin approved external actions to full immutable commit SHAs, with a version comment;
- stage policy in a low-risk repository before enforcing it broadly;
- assign an owner, expiry, and review for each exception;
- assess reusable workflows and local actions separately.

## Verification

- An approved pinned action succeeds.
- A deliberately prohibited action is blocked before execution.
- A mutable-tag reference is detected by policy or CI.
- Every exception is still valid at its scheduled review.

## Gotchas

- SHA pinning prevents tag movement; it does not establish that the pinned commit is safe.
- Artifact attestations complement this control but do not replace it.
- Broad allow rules can defeat precise blocklists; test the effective policy.

## Related

- `security/supply-chain-npm-security.md`
- `worktree/sbom-slsa-2026.md`
