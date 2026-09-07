---
title: cert-manager X.509 Certificate Controller Version Governance
owner: Knowledge Engineering
status: approved
classification: public
last-reviewed: 2026-09-08
review-cycle: 180 days
next-review: 2027-03-07
source: cert-manager project (cert-manager/cert-manager); CNCF graduated; Jetstack; cert-manager documentation at cert-manager.io
---

# cert-manager X.509 Certificate Controller Version Governance

## 1. Purpose

This card governs how `orchords-docs` evaluates cert-manager across versions, CRD APIs, issuer backends, and renewal behavior. It is the reference input for any KB card that cites Kubernetes TLS automation, ACME/CA integration, or trust distribution.

## 2. Scope

In scope:

- cert-manager controller v1.15+ (apiVersion `cert-manager.io/v1`).
- Issuer backends: self-signed, CA, ACME (HTTP-01, DNS-01), Vault, Venafi TPP/Venafi Cloud.
- CRDs: `Certificate`, `Issuer`, `ClusterIssuer`, `CertificateRequest`, `Order`, `Challenge`.
- trust-manager (cert-manager sub-project) for bundle distribution (covered in `TRUST_MANAGER_VERSION_GOVERNANCE.md` if present; else link to cert-manager docs).
- External CA via CSI driver (e.g., AWS PCA, GCP CAS).

Out of scope:

- Keyless signing chains (see `COSIGN_VERSION_GOVERNANCE.md`, `FULCIO_VERSION_GOVERNANCE.md`).
- Service-mesh mTLS / SPIFFE issuance (see `SPIFFE_SPIRE_VERSION_GOVERNANCE.md`).

## 3. Versioning policy

- Pin to a specific minor (e.g. `v1.15.4`) and verify digest against the published SLSA provenance.
- Support the current minor and the previous minor (N-1); security backports only on N-1.
- `cert-manager.io/v1` is the only supported API; the legacy `v1alpha2` and `v1beta1` APIs are removed in 1.15+.
- Upgrade window: ≤ 60 days after a new minor; 14 days for security releases.
- Always upgrade controller, webhook, and cainjector together; never split versions across components.

## 4. Compatibility matrix

| cert-manager | Released | Status | Kubernetes tested | Notes |
|---|---|---|---|---|
| 1.17.x | August 2026 | current | 1.31 – 1.34 | Gateway API issuer stable; DNSPublicIP shim removed |
| 1.16.x | May 2026 | N-1 | 1.30 – 1.33 | stable; security fixes only |
| 1.15.x | February 2026 | N-2 | 1.29 – 1.32 | legacy; no backports |
| 1.14.x | November 2025 | EoL | 1.28 – 1.31 | EoL |

References: `https://github.com/cert-manager/cert-manager/releases`, `https://cert-manager.io/docs/`.

## 5. Issuer selection guidance

- Public trust (Let's Encrypt, ZeroSSL, Google Trust Services, Sectigo): ACME with DNS-01 for wildcard and high-trust flows; HTTP-01 only when port 80 is reachable.
- Internal CA: Venafi TPP for enterprise policy control, or a Vault PKI engine for greenfield.
- CSI driver issuance for hardware-backed keys (YubiHSM, AWS PCA) when private keys must never leave hardware.
- Avoid `selfSigned` for production ingress; reserve for short-lived dev sandboxes.

## 6. Renewal and policy

- Default renewal window is 30 days before expiry; lower to 7 days for CA-issued certs whose revocation channels are slow.
- Set `renewBefore` explicitly on every `Certificate` to avoid the implicit 2/3-of-duration fallback.
- Honor the controller's `--max-issuance-time` (default 90 m) and `--certificate-validity-duration` overrides only when an issuer explicitly supports them (e.g., Venafi).
- Reuse private keys across renewals only when the consuming workload does not require a fresh key (e.g., ingress); require a fresh key per issuance for service identities.

## 7. ACME DNS-01 providers

- Pin the DNS provider webhook image to a digest matching the chart release.
- Use `dns01RecursiveNameservers` only when the upstream provider requires it (large managed DNS).
- Honor provider rate limits; back off on 429 with a 60 s minimum retry.

## 8. Upgrade procedure

1. Read release notes; identify webhook/CAPI changes and CRD upgrades.
2. Run `cmctl upgrade migrate-api-version` if upgrading from `v1beta1` / `v1alpha2`.
3. Apply the chart upgrade to staging with `--dry-run --debug`.
4. Run `cmctl check api` against staging.
5. Roll production one cluster at a time; preserve prior `--issuer-ambient-credentials` setting for one cycle.

## 9. Rollback procedure

1. `helm rollback <release>` to the prior chart revision.
2. Validate `kubectl get certificates -A`; failures after downgrade usually mean the new API version has been persisted.
3. Re-run `cmctl check api` and confirm no `deprecated` annotations.
4. Re-issue any failed certificates with `--force-rotation` only when key continuity is acceptable to the consumer.
5. Document the rollback cause in the change ticket.

## 10. Observability

Required metrics:

- `certmanager_cert_expiration_seconds_seconds` (gauge per Certificate).
- `certmanager_certificate_ready_status{condition,reason}` (gauge).
- `certmanager_acme_client_request_count{host,method,status}`.

One alert:

- `CertManagerExpirationImminent` — page when `min(certmanager_cert_expiration_seconds_seconds) by (namespace, name) < 7 * 86400` for 30 minutes; also page on `certmanager_certificate_ready_status{condition="True"} == 0` for 5 minutes on any Certificate that should be ready.

References: `https://cert-manager.io/docs/metrics/`, `https://github.com/cert-manager/cert-manager/blob/master/docs/usage/observability.md`.

## 11. References

- cert-manager docs: `https://cert-manager.io/docs/`
- cert-manager repo: `https://github.com/cert-manager/cert-manager`
- Releases: `https://github.com/cert-manager/cert-manager/releases`
- trust-manager: `https://github.com/cert-manager/trust-manager`
- cmctl reference: `https://cert-manager.io/docs/cli/cmctl/`
- CNCF cert-manager: `https://www.cncf.io/projects/cert-manager/`
