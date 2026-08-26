# GitHub Actions OIDC with reusable workflows

**Date:** 2026-08-26
**Status:** documented
**Source:** https://docs.github.com/en/actions/how-tos/secure-your-work/security-harden-deployments/oidc-with-reusable-workflows

## Context

GitHub supports OpenID Connect with reusable workflows so deployment authentication can avoid long-lived cloud credentials while centralizing deployment logic.

## Pattern

- Put sensitive deployment logic in a controlled reusable workflow.
- Configure cloud trust conditions to recognize the intended repository/workflow identity rather than accepting any token from the organization.
- Keep token permissions minimal and issue OIDC tokens only to jobs that need them.
- Review caller/called workflow trust boundaries when repositories differ.
- Prefer short-lived OIDC federation over storing static cloud access keys in repository secrets when the provider supports it.

## Verification

1. An authorized caller can obtain the intended cloud role.
2. An unauthorized repository/workflow cannot satisfy the trust policy.
3. Removing or changing the approved reusable workflow breaks authorization as expected rather than falling back to a static credential.
4. Logs and error output do not expose OIDC tokens or cloud credentials.

## Gotcha

Centralizing deployment logic does not make the called workflow automatically trustworthy; protect its repository, refs, permissions, and change process as part of the trust boundary.
