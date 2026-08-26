# Cloudflare API token least privilege and rotation governance

**Issue:** A deployment, automation, or integration receives a broad Cloudflare credential, making a leak or misconfigured workflow capable of changing unrelated accounts, zones, or services.
**Date:** 2026-08-12
**Author:** ORCHORDS
**Status:** documented

## Decision

Use a scoped API token for each automation identity. Do not use a Global API Key for new automation. Give the token only the account or zone resources and permissions required by its declared operation.

A deployment token, DNS-update token, log-read token, and Secrets Store administration token are separate capabilities with separate owners and rotation paths.

**Sources:**

- [Create API tokens — Cloudflare](https://developers.cloudflare.com/fundamentals/api/get-started/create-token/)
- [Cloudflare API authentication](https://developers.cloudflare.com/fundamentals/api/get-started/keys/)
- [Workers secrets API authentication](https://developers.cloudflare.com/api/go/resources/workers/subresources/scripts/subresources/secrets/methods/update/)

## Implementation pattern

1. Write down the operation, target account/zone, owning service, expiration/review date, and incident contact.
2. Start from a narrowly relevant Cloudflare template or create a custom token.
3. Select only the required permission(s) and resource scope. Do not grant “all accounts” or “all zones” when one account, zone, or Worker is sufficient.
4. Store the token only in the deployment platform’s protected secret facility. Pass it directly to the command that needs it; never commit it, put it in a Worker `vars` block, print it, or expose it in a client bundle.
5. Keep destructive administration (for example, Secret Store writes) in a separately approved workflow from ordinary application deployment.
6. Rotate by creating and validating a replacement first, switching the consumer, then revoking the previous token. Record the token identifier and expiry, never the secret value.

## Verification

- A token used by the deployment can deploy only the intended Worker/project and cannot modify an unrelated account, zone, or service.
- A DNS token cannot deploy Workers; a Workers deployment token cannot edit DNS unless that capability was intentionally approved.
- CI logs, artifacts, debug output, and failure reports contain no token value.
- Rotation is rehearsed: new token succeeds, old token is revoked, and a request using the old token is rejected.
- Token inventory has an owner, purpose, allowed resources, last-rotation date, and next review date.

## Failure handling

If a token leaks, revoke it immediately, create a replacement with the same or narrower scope, identify deployments and workflows that used it, and review audit/deployment history. Do not “fix” the incident by merely masking a log line or changing the token’s display name.

## Gotchas

- “Read” permissions can still disclose sensitive operational information; scope them deliberately.
- API tokens are bearer credentials. A redacted screenshot or a secret name is not proof that no value leaked; inspect the distribution path.
- A successful deployment is not proof of least privilege. Negative authorization tests are required.
- Use application secrets or Secrets Store bindings for runtime credentials; a CI API token is not automatically appropriate for Worker runtime use.

## Related

- `cloudflare/secrets-store-binding-selection-and-blast-radius-control.md`
- `cloudflare/workers-binding-rotation-and-global-scope-safety.md`
- `github/github-actions-secrets-management.md`
- `security/secrets-rotation-runbook-2026.md`
