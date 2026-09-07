---
title: Pomerium Identity-Aware Reverse Proxy Version Governance
owner: Knowledge Engineering
status: approved
classification: public
last-reviewed: 2026-09-08
review-cycle: 180 days
next-review: 2027-03-07
source: Pomerium project (pomerium/pomerium); Apache-2.0; documentation at pomerium.com/docs
---

# Pomerium Identity-Aware Reverse Proxy Version Governance

## Overview

Pomerium is an identity-aware reverse proxy that enforces authentication and authorization at the network edge, in front of HTTP applications that do not natively understand SSO. It brokers identity from upstream IdPs, evaluates policy per request, and forwards a verified, scoped JWT to the upstream service. This card governs how the KB evaluates Pomerium versions, edition differences, and operational concerns.

## Editions

Pomerium ships in three editions with overlapping feature surfaces but distinct upgrade paths:

- Pomerium CLI (open source, Apache-2.0): the `pomerium` binary; self-hosted; configuration via file, env, or `pomerium-context`. This is the edition the KB tracks for OSS users.
- Pomerium Zero: managed control plane operated by Pomerium Inc.; data plane still runs in the customer's environment. Configuration is delivered from Zero to the data plane.
- Pomerium Enterprise: self-hosted control plane with role-based access, policy context extensions, and enterprise IdP connectors; licensed.

Edition-specific behavior (authenticate flow, route schema, signed-cert issuance) is gated by the `identity-providers` and `policies` keys, which are version-gated even within a single binary series.

## Identity provider integrations

Pomerium brokers identity through external IdPs and forwards a verified JWT to the upstream service. Supported IdPs include:

- OpenID Connect (any compliant provider).
- SAML 2.0.
- GitHub (OAuth).
- GitLab (OAuth).
- Okta (OIDC and SAML).
- Google Workspace (OIDC).

IdP-specific quirks the KB tracks:

- Okta: app-embedded OAuth flow requires the `okta-claims` claim mapping for group retrieval.
- Google Workspace: hosted-domain enforcement; refresh-token rotation on admin-revoke.
- GitHub / GitLab: organization and team claims require the `set_authorization_groups_details` provider option.

## Datastore choices

Pomerium persists sessions, encrypted settings (Enterprise / Zero), and the audit log in a backing store. Supported:

- Postgres (recommended; required for Enterprise).
- Redis (recommended for high-rate session workloads; supports TLS and AUTH); MySQL (MySQL 8+).

When migrating between stores, follow the Pomerium `migrate` subcommand; session tokens do not transfer across stores, so cut-over requires a brief re-auth window.

## Authorization policy model

Policies in Pomerium are declarative `policy` blocks (CLI / Enterprise) or routes (Zero). Each policy defines:

- `from`: source (`any`, `and`, `or` blocks of source matchers).
- `to`: upstream destination URL.
- `allowed_users`, `allowed_groups`, `allowed_domains`.
- `policy` / `sub_policy` (Enterprise): positive/negative boolean logic across sources, IdP claims, and request metadata.
- `criteria`: time-window and geographic constraints.

JWTs forwarded to upstreams carry `email`, `groups`, `sub`, and custom claims from the IdP.

## JWT verification flow

Pomerium issues and verifies JWTs between its services (Pomerium Proxy, Pomerium Authorize) and the upstream. Verification steps:

1. Proxy obtains a signed JWT from Pomerium Authorize after IdP-mediated authentication.
2. Proxy forwards the JWT as `Authorization: Bearer ...` to the upstream (configurable).
3. Upstreams verify the JWT against Pomerium's JWKS endpoint (typically `/.well-known/pomerium/jwks.json`).
4. Claims (`pomerium.io/email`, `pomerium.io/groups`, `pomerium.io/expires`) are made available to the upstream for fine-grained authorization.

For self-hosted and CLI installations, expose the JWKS URL to upstreams; mTLS is recommended between Pomerium services and upstreams that consume the JWT.

## TLS / mTLS between Pomerium services

Pomerium encrypts:

- Edge traffic (client -> Proxy): TLS terminated by the Proxy; recommended to use ACME (Let's Encrypt) or operator-managed certs.
- Internal traffic (Proxy -> Authorize / datastore): mTLS where the configuration supports it; Postgres and Redis connections should also be TLS-only.
- Upstream traffic (Proxy -> application): TLS by default; mTLS optional via upstream-ca cert.

The KB requires `InsecureSkipVerify: false` everywhere and an explicit `client_ca_files` for any mTLS hop.

## Signing-key rotation

Pomerium rotates the signing key used for downstream JWTs on a schedule. Implications:

- JWKS exposes all currently valid public keys; clients cache keys with `kid` for the rotation window.
- Manual rotation: re-issue `SIGNING_KEY` via the Pomerium config; do not reuse a prior key across rotations.
- Rotate IdP client secrets on the same schedule; track via `pomerium debug` and the audit log.

## Postgres migration compatibility

Pomerium embeds schema migrations in the binary. Compatibility rules:

- Run the Pomerium binary against the target Postgres version before cutting over; the embedded `migrate` step runs on startup.
- Postgres major-version upgrades (12 -> 16) are supported as long as the new version is on Pomerium's compatibility matrix; minor upgrades are transparent.
- Redis upgrades: track `redis-server` minor versions; protocol compatibility is preserved across `redis-stack` minor releases.

## Review cadence

This card is reviewed every 180 days; the next scheduled review is 2027-03-07.

## References

- Pomerium docs: `https://www.pomerium.com/docs/`
- Pomerium repo: `https://github.com/pomerium/pomerium`
- Releases: `https://github.com/pomerium/pomerium/releases`
- Configuration reference: `https://www.pomerium.com/docs/reference/`
- Identity providers: `https://www.pomerium.com/docs/identity-providers/`
- Pomerium Zero: `https://www.pomerium.com/docs/zero/`
- Pomerium Enterprise: `https://www.pomerium.com/docs/enterprise/`
