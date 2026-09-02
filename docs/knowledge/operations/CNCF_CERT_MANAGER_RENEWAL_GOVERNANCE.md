# CNCF cert-manager Renewal Governance

## Purpose

cert-manager (CNCF Graduated) automates the issuance, renewal, and revocation of TLS certificates in Kubernetes clusters. The renewal governance pattern captures the issuer configuration (ACME, self-signed, Vault, internal CA), the renewal policy (renew-before-expiry threshold), the certificate template (common name, SAN list, key algorithm), and the failure-handling process for renewals that fail past their threshold. Without an explicit governance pattern, certificates expire silently and cause outages.

## Current context and source status

cert-manager 1.15 (released 2025) and cert-manager 1.16 (released 2026) are the current supported versions. cert-manager 1.17 entered beta in mid-2026. The project follows the CNCF Graduated governance model. cert-manager supports ACME (RFC 8555), internal CA issuers, Vault PKI, and Venafi TPP/Cloud integrations.

## Governance pattern

1. Pin cert-manager version, CRD version, and chart version in cluster bootstrap.
2. Use `Issuer` or `ClusterIssuer` with explicit `renewBefore` and `duration` (for example `renewBefore: 720h` for 30 days on a 90-day cert).
3. Separate staging and production issuers; never run production issuance against staging endpoints.
4. Use explicit `dns01` or `http01` solver configuration with named providers (Route53, Cloud DNS, Azure DNS).
5. Monitor `cert-manager` Prometheus metrics: `certmanager_certificate_ready_status`, `certmanager_certificate_expiration_timestamp_seconds`, `certmanager_controller_sync_total`.
6. Alert on certificates within 14 days of expiry; escalate on certificates within 7 days.
7. Rotate issuer account credentials on the documented cadence (for example ACME account key).
8. Maintain a Certificate inventory in version control with owner, common name, SAN list, and issuer reference.
9. Route failed renewals to the on-call runbook with documented ACME rate-limit handling.
10. Validate that the resulting chain matches the organization's trust store by periodic external scan.

## Validation and evidence

- cert-manager version and chart version recorded in cluster inventory.
- Issuer and ClusterIssuer resources committed to GitOps.
- Certificate inventory in version control.
- Prometheus alert rules defined for renewal failure and approaching expiry.
- External scan (for example `openssl s_client`, testssl.sh) confirms chain validity.
- Renewal runbook published and reviewed annually.

## Failure correction

Common defects include `renewBefore` too close to expiry (no buffer for retries), staging issuer accidentally promoted to production, and missing rate-limit handling for ACME providers. Corrective actions include extending `renewBefore`, restoring issuer separation, and adding rate-limit handling in the renewal runbook.

## Limitations

- cert-manager does not cover application-layer mTLS outside Kubernetes.
- Internal CA issuers require an external trust-store distribution process.
- cert-manager cannot enforce that consuming services reload certificates after renewal (for example, ingress controller reload).
- ACME rate limits are provider-specific and require separate operational runbooks.

## Scope note

This knowledge article is part of the **operations** leaf. Sibling leaves cover: **platforms** (cert-manager deployment and ACME solver topology), **security** (PKI governance and ACME), **engineering** (TLS 1.3 posture and renewal logic), and **templates** (certificate inventory template). Use this article together with those siblings where the topic overlaps.

## Canonical sources

- cert-manager documentation (CNCF Graduated): https://cert-manager.io/docs/
- cert-manager GitHub repository (CNCF Graduated): https://github.com/cert-manager/cert-manager
- RFC 8555, *Automatic Certificate Management Environment (ACME)* (IETF, for ACME provider protocol): https://www.rfc-editor.org/rfc/rfc8555

Sources were verified on September 1, 2026.