# CNCF cert-manager TLS Certificate Lifecycle Governance

## Purpose

cert-manager is a CNCF Graduated project that automates the issuance, renewal, and management of TLS certificates in Kubernetes. It integrates with Let's Encrypt, HashiCorp Vault, Venafi, and other certificate authorities. Governance ensures that certificate issuance policy is enforced, that renewals occur before expiry, and that certificate revocation is handled.

## Current context and source status

cert-manager is a CNCF Graduated project. Versions and Issuers, ClusterIssuers, and Certificate CRDs evolve; verify the current cert-manager documentation before treating any specific configuration as a current requirement.

## Governance workflow and controls

### 1. Adopt cert-manager

Adopt cert-manager for TLS certificate management. Deploy it cluster-wide.

### 2. Configure Issuers

Configure Issuers and ClusterIssuers per certificate authority. Document the certificate hierarchy.

### 3. Configure Certificate resources

Configure Certificate resources per workload. Specify the dnsNames, the Issuer, the duration, and the renewBefore.

### 4. Configure ingress integration

Configure ingress integration with the cert-manager annotation (`cert-manager.io/issuer`). Document the annotation policy.

### 5. Configure renewal

Configure renewal with adequate renewBefore (typically 1/3 of the certificate lifetime). Monitor renewal failures.

### 6. Configure revocation

Configure revocation on Certificate deletion. Use the cleanup policy.

### 7. Configure CA rotation

Configure CA rotation for the in-cluster CA. Apply a documented procedure.

### 8. Audit certificate activity

Audit certificate issuance and renewal. Send events to a central destination.

### 9. Apply policy controls

Apply policy controls (Kyverno, OPA) to enforce Issuer usage and prevent manual certificate creation.

## Validation and evidence

- Issuer configuration.
- Certificate inventory.
- Renewal records.
- Audit logs.

## Failure correction

Common defects include renewal failures (rate limits, DNS), missing certificate revocation, and policy gaps. Corrective actions include a renewal monitoring alert, a revocation procedure test, and a policy enforcement review.

## Limitations

- cert-manager is specific to Kubernetes.
- ACME challenges have rate limits; design for renewals.
- Some Certificate Authorities require additional configuration.
- Private CA integration requires careful trust setup.

## Canonical sources

- CNCF, cert-manager documentation, current edition.
- CNCF, cert-manager reference architecture, current edition.

## Scope note

This article belongs to the engineering leaf and cross-references the platforms leaf for Kubernetes platforms, the security leaf for cryptographic controls, and the operations leaf for certificate operations.
