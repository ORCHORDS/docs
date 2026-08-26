# Cloudflare Secrets Store binding selection and blast-radius control

**Issue:** Multiple Workers need the same third-party API credential, but teams either duplicate long-lived values per Worker or replace a shared value without knowing every affected consumer.
**Date:** 2026-08-12
**Author:** ORCHORDS
**Status:** documented

## Decision

Use Cloudflare Secrets Store only when a centrally managed, account-level secret is intentionally shared across multiple consumers. Bind each Worker to a named secret and use scope, ownership, and rollout controls so rotation does not become an undocumented account-wide change.

For a credential used by one Worker only, an ordinary Worker secret may have a smaller blast radius. Never place a secret value in Wrangler `vars`, source code, repository files, or a client-side bundle.

**Sources:**

- [Cloudflare Secrets Store Workers integration](https://developers.cloudflare.com/secrets-store/integrations/workers/)
- [Manage Cloudflare Secrets Store secrets](https://developers.cloudflare.com/secrets-store/manage-secrets/how-to/)
- [Cloudflare Workers secrets](https://developers.cloudflare.com/workers/configuration/secrets/)
- [Cloudflare Workers environment variables](https://developers.cloudflare.com/workers/configuration/environment-variables/)

## Selection guide

| Need | Preferred mechanism |
|---|---|
| Non-sensitive deploy configuration | Wrangler `vars` |
| Sensitive value for one Worker | Worker secret |
| Sensitive value deliberately shared by several Workers | Secrets Store secret binding |
| Local development value | ignored `.dev.vars` or `.env`; use one, not both |

## Safe rotation procedure

1. Inventory bindings before changing the value: consumer Worker, environment, owner, provider account, and rollback contact.
2. Create or validate the replacement credential at the upstream provider.
3. Update the central secret only in an approved change window. A Secrets Store replacement affects every service using that secret.
4. Validate every declared consumer with a non-sensitive health check and verify the previous credential is no longer accepted where the provider supports revocation.
5. Preserve an auditable change record containing names and identifiers only—never values.
6. Do not delete a secret until all bindings and provider-side dependencies have been removed or migrated.

## Verification

- Each binding uses the intended store ID and secret name, and no production Worker has a plaintext runtime credential in `vars`.
- The secret’s Workers scope and the administration token’s `Secrets Store Write` capability are limited to authorized operators.
- A staged rotation proves each declared consumer works; an unrelated Worker cannot read or use the binding.
- Local secret files are ignored by Git, and required-name validation prevents a deployment from silently using an unintended local variable.
- Monitoring records authentication failures by consumer after rotation without logging credentials.

## Gotchas

- Secret values are intentionally not viewable after they are saved; treat loss of the source credential as a recovery event, not a reason to store a backup in Git.
- A central secret is a shared dependency. It is not automatically safer than per-Worker secrets.
- Secret names cannot contain spaces.
- Configuration can name a binding without proving the target secret exists or is valid for the upstream service; deploy-time and runtime checks remain necessary.

## Related

- `cloudflare/api-token-least-privilege-and-rotation-governance.md`
- `cloudflare/workers-binding-rotation-and-global-scope-safety.md`
- `github/github-actions-secrets-management.md`
- `security/secrets-rotation-runbook-2026.md`
