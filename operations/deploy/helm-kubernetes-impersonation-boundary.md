# Helm Kubernetes impersonation boundary

**Problem**

Helm user/group impersonation changes the identity evaluated by the API server and can be misused to test or deploy with unintended authority.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## When to use

Use for controlled authorization validation or delegated automation.

## Controls

- Require explicit approved user and groups.
- Keep the caller's impersonate permission narrowly scoped.
- Record effective identity without tokens.

## Implementation

- Pass `--kube-as-user` and groups only in protected workflows.
- Pair with target context/namespace verification.
- Run a server-side dry run first.

## Tests

- Test allowed/denied objects, namespaces, groups, hooks, rollback, and audit events.

## Gotchas

- Impersonation requires separate RBAC permission.
- Local rendering does not test authorization.
- Groups can broaden access unexpectedly.

## Official sources

- [Official documentation](https://kubernetes.io/docs/reference/access-authn-authz/authentication/#user-impersonation)
