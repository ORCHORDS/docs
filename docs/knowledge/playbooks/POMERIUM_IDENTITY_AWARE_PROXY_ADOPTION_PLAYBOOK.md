# Pomerium Identity-Aware Proxy Adoption Playbook

## Purpose

Adopt Pomerium as an identity-aware reverse proxy in front of internal HTTP services that currently rely on VPN or static auth, with audit and metrics wired from day one.

## Audience

Platform engineers, security engineers, application owners migrating from VPN.

## Pre-conditions

- `docs/knowledge/reference/POMERIUM_VERSION_GOVERNANCE.md` reviewed and current.
- Identity provider picked (Okta, Google, GitHub, or any OIDC-compliant IdP) with the OIDC client secret stored in the secret manager.
- Postgres reachable and sized for the data tier (or the operator-managed store documented in the governance card).
- Pomerium signing-key pair generated and stored in KMS; the public half is pinned in the Pomerium config.
- Wildcard route and DNS target for the proxy registered with the network team.
- A documented list of upstream apps, their owners, and the policy that should apply to each.

## Procedure

### Step 1 — Deploy the Pomerium cluster

1. Choose All-In-One for non-production and a multi-replica Console deployment for production.
2. Pin the image to the version recorded in `POMERIUM_VERSION_GOVERNANCE.md`; do not float on `latest`.
3. Configure the secret manager integration so the signing key and IdP client secret are pulled at boot, not baked into the image.
4. Smoke test the bootstrap endpoint and confirm the cluster reports a healthy leader.

### Step 2 — Wire the OIDC identity provider

1. Register Pomerium as an OIDC client with the chosen IdP and store the client secret in the secret manager.
2. Configure `idp.provider`, `idp.client_id`, `idp.client_secret`, and `idp.scopes` in Pomerium's config.
3. Map IdP groups to Pomerium policy groups and document the mapping in the governance card.
4. Validate the login round-trip with a non-employee test account before any production traffic is routed.

### Step 3 — Define routes and policies for each upstream app

1. For each upstream app, declare a route with `from`, `to`, `policy`, and the JWT verification settings.
2. Restrict policies to the IdP groups that legitimately need access; default deny is the rule.
3. Enable enforced passthrough so the upstream app sees the verified user identity.
4. Confirm the route loads and the IdP groups resolve correctly via Pomerium's `/diagnostics` endpoint.

### Step 4 — Test enforced passthrough and JWT verification

1. Hit each route with a positive identity (should succeed) and a negative identity (should be denied).
2. Validate the JWT signature, audience, and expiry on a sample of upstream requests.
3. Confirm the upstream app receives `X-Pomerium-Claim-*` headers as documented.
4. File any policy gaps as security-engineering tickets before cutover.

### Step 5 — Enable audit logs and Prometheus metrics

1. Configure the audit log sink to the centralized log backend (Loki, per `LOKI_LOG_PIPELINE_ROLLOUT_PLAYBOOK.md`).
2. Enable the `/metrics` endpoint on Pomerium and scrape it from Prometheus.
3. Build Grafana dashboards for denied requests, IdP errors, and p99 proxy latency.
4. Run a non-employee access test: confirm an external IdP user cannot reach any internal route.

### Step 6 — Rotate the signing key and decommission VPN

1. Rotate the signing key on a documented cadence, using KMS to mint the new pair and publish the public half.
2. Monitor the dual-key window to confirm all routes have re-fetched the new public key.
3. Run VPN and Pomerium in parallel for one billing cycle, then decommission the VPN.
4. Capture decommission evidence in the change record and link it from `POMERIUM_VERSION_GOVERNANCE.md`.

## Rollback

1. Keep the IdP integration intact; the IdP client and groups remain valid even if Pomerium is rolled back.
2. Fall back to a vanilla nginx + mTLS-only deployment for the most sensitive routes if Pomerium is misbehaving.
3. Preserve the audit log; incident review may need it after rollback, so the sink must continue to receive events.
4. Validate the fallback path with the same non-employee access test that the Pomerium path passed.

## References

- `docs/knowledge/reference/POMERIUM_VERSION_GOVERNANCE.md`
- Pomerium Quickstart: `https://www.pomerium.com/docs/quickstart`
- Pomerium Identity Provider config: `https://www.pomerium.com/docs/identity-providers`
- Pomerium routes: `https://www.pomerium.com/docs/routes`
- Pomerium policy: `https://www.pomerium.com/docs/capabilities/policy`
