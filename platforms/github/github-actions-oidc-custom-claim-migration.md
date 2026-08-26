# GitHub Actions OIDC custom-claim migration

**Issue:** Broad cloud trust based only on repository names can grant more workflow contexts access than intended, while changing token subject format without coordination can break deployments.

**Date:** 2026-08-17
**Author:** ORCHORDS
**Status:** documented

## Guidance

GitHub supports customizing OIDC token audience and subject claims and using claims such as repository identity, visibility, reusable workflow, or custom properties. Cloud-side trust must validate exact intended claims.

Before changing the GitHub subject template, create and test the matching cloud-provider condition. The customization replaces the previous subject format, so unsynchronized rollout can cause every new token to be rejected.

## Controls

- Grant `id-token: write` only to jobs that federate.
- Bind trust to immutable identifiers where supported.
- Restrict environment and reusable-workflow context.
- Validate audience and issuer exactly.
- Never log JWTs.
- Keep a tested rollback and staged migration.

## Verification

1. Decode only non-sensitive claim names/values in an isolated test.
2. Confirm an allowed workflow obtains the intended role.
3. Confirm branch, fork, repository, and workflow negatives are denied.
4. Apply cloud policy before the GitHub template change.
5. Audit cloud access logs after rollout.

## Sources

- [GitHub Docs: OpenID Connect reference](https://docs.github.com/en/actions/reference/security/oidc)
- [GitHub Docs: OIDC in cloud providers](https://docs.github.com/en/actions/how-tos/secure-your-work/security-harden-deployments/oidc-in-cloud-providers)
