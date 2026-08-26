# GitHub Dependabot target-branch security-update split

**Issue:** A `target-branch` entry is assumed to redirect all Dependabot pull requests, leaving teams surprised when security updates still target the repository default branch and ignore ecosystem customizations attached to the non-default branch.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Contract

For version updates, `target-branch` selects the branch whose manifests Dependabot checks and the branch that version-update pull requests target. Dependabot security updates target the repository default branch. When `target-branch` is set for an ecosystem, the options in that configuration block no longer apply to security updates.

## Controls

- Keep security-relevant manifests and lockfiles current on the default branch.
- Omit `target-branch` when the same ecosystem configuration must customize security-update pull requests.
- When a staging branch is required for version updates, document the split and define an explicit default-branch security-update policy.
- Protect the default branch with required tests that exercise the real dependency graph and supported runtime matrix.
- Assign owners, labels, grouping, registries, and pull-request limits separately according to GitHub's supported security-update configuration.
- Monitor Dependabot alerts and security-update failures; do not infer coverage from scheduled version-update activity.
- After changing the default branch, immediately verify alerts, manifests, registry access, rulesets, and generated pull-request targets.

## Example

```yaml
version: 2
updates:
  - package-ecosystem: npm
    directory: /
    schedule:
      interval: weekly
    target-branch: dependency-staging
```

This block governs npm version updates on `dependency-staging`; it is not a policy that moves security updates away from the default branch.

## Verification

In a disposable repository, configure a non-default `target-branch`, trigger a normal version update, and confirm its base branch. Then use a vulnerable dependency supported by Dependabot security updates and confirm the security pull request targets the default branch. Assert both branches run the intended checks.

## Gotchas

The schedule controls version-update checks; security updates are advisory-triggered. A green staging-branch dependency PR does not prove the default-branch security update can merge. Branch drift can make the two update lanes produce materially different lockfiles.

## Official sources

- [GitHub Docs: Dependabot options reference—target-branch](https://docs.github.com/en/code-security/reference/supply-chain-security/dependabot-options-reference#target-branch)
- [GitHub Docs: Dependabot pull requests](https://docs.github.com/en/enterprise-cloud@latest/code-security/concepts/supply-chain-security/dependabot-pull-requests)
- [GitHub Docs: Customize Dependabot pull requests](https://docs.github.com/en/code-security/tutorials/secure-your-dependencies/customizing-dependabot-prs)
