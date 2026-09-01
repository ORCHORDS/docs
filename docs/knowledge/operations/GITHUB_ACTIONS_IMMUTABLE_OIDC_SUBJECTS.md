# GitHub Actions Immutable OIDC Subject Governance

## Purpose

GitHub Actions OpenID Connect (OIDC) lets workflows exchange short-lived identity tokens with cloud services instead of storing long-lived deployment credentials. The trust policy on the receiving service must match the identity format GitHub actually emits.

GitHub introduced an immutable default subject format for repositories created after July 15, 2026. The immutable format includes both owner and repository numeric IDs so that repository renames, transfers, or recycled names do not cause an unrelated repository to inherit the same default subject identity.

## Current GitHub behavior

For repositories using immutable subjects, the default `sub` includes both the owner name and owner ID and the repository name and repository ID. Repositories created before July 15, 2026 retain the previous name-based format unless they opt in. GitHub Enterprise Server does not currently support immutable subject claims.

Organizations and repositories can also customize OIDC subject claims. When immutable subjects are enabled, the immutable owner and repository IDs remain part of the repository segment even when claim customization is used.

## Governance pattern

1. Inventory every cloud or external trust policy that accepts GitHub Actions OIDC tokens.
2. Record whether each repository currently uses the previous name-based subject, the immutable subject, or a customized subject template.
3. Before opting an existing repository into immutable subjects, update the receiving trust policy to accept the new format so deployment access is not accidentally broken.
4. Bind trust to the narrowest practical workflow identity, environment, branch, repository, or reusable-workflow claim rather than trusting an entire organization without need.
5. Treat repository transfer and rename events as trust-policy review triggers.
6. Test the resulting token claims and receiving policy before removing the previous trust rule.
7. Remove obsolete subject patterns after migration so old namespace-based trust cannot remain usable indefinitely.

## Reusable workflows

When a deployment is performed by a reusable workflow, GitHub includes `job_workflow_ref` in the OIDC token. Where the receiving provider supports the claim, it can be used to require a specific reusable workflow rather than trusting every workflow in the caller repository.

For providers that only support standard claims, GitHub allows subject customization to include selected claims. Any customization should be reflected in the receiving trust condition before the GitHub-side change is applied.

## Failure modes

- Opting into immutable subjects before updating the receiving trust policy can block deployments.
- Keeping both old and new subject formats indefinitely can preserve unnecessary trust.
- Trusting only a mutable repository name leaves a namespace-reuse risk that immutable subjects are designed to reduce.
- Trusting a reusable workflow without checking the expected workflow reference can weaken centralized deployment controls.
- Assuming GitHub Enterprise Server has the same immutable-subject behavior as GitHub.com can create incorrect policy expectations.

## Sources

- GitHub Docs — OpenID Connect reference: https://docs.github.com/en/actions/reference/security/oidc
- GitHub Docs — Using OpenID Connect with reusable workflows: https://docs.github.com/en/actions/how-tos/secure-your-work/security-harden-deployments/oidc-with-reusable-workflows
- GitHub Docs — REST API endpoints for GitHub Actions OIDC: https://docs.github.com/en/rest/actions/oidc

## Scope note

This article describes GitHub.com OIDC trust governance. Cloud-provider syntax and enterprise policy capabilities vary, so receiving-side configuration should be verified against the provider's current documentation.