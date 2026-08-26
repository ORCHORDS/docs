# TLS Certificate Lifecycle Management

**Date:** 2026-08-16
**Author:** the platform team
**Status:** published

## Symptom

Your TLS certificate expires unexpectedly, causing an outage. Or, with the
CA/Browser Forum's 2026 reduction to 200-day maximum validity (dropping to
100 days in 2027 and 47 days in 2029), your team's manual renewal process
can no longer keep pace and certificates start expiring before anyone notices.

## Context

The CA/Browser Forum voted to progressively shorten maximum TLS certificate
lifetimes:

| Effective date | Maximum validity |
|---|---|
| Before March 2026 | 398 days |
| March 15, 2026 | **200 days** |
| March 15, 2027 | 100 days |
| March 15, 2029 | 47 days |

This makes automated certificate management mandatory. Manual renewal at
47-day intervals is operationally unsustainable for any organization with
more than a handful of certificates.

## ACME protocol

ACME (Automatic Certificate Management Environment, RFC 8555) is the
standard protocol for automated certificate issuance and renewal. Let's
Encrypt popularized it; as of 2026, AWS Certificate Manager also supports
ACME for public certificates (45-day validity).

### ACME workflow
1. **Account registration** — create an ACME account with the CA.
2. **Order** — request a certificate for one or more domain names.
3. **Authorization** — prove domain control via HTTP-01 (file on webserver),
   DNS-01 (TXT record), or TLS-ALPN-01 challenge.
4. **Finalize** — submit CSR, CA issues the certificate.
5. **Renewal** — repeat automatically before expiry (typically at 2/3 of
   lifetime).

### ACME clients
- **certbot** — the reference ACME client. Best for traditional servers.
- **acme.sh** — lightweight shell-based client. Good for edge cases.
- **lego** — Go-based, supports 100+ DNS providers.
- **cert-manager** — Kubernetes-native certificate management (see below).

## cert-manager (Kubernetes)

cert-manager is the standard for certificate management in Kubernetes. It
automates issuance and renewal via ACME or internal CAs.

```yaml
apiVersion: cert-manager.io/v1
kind: ClusterIssuer
metadata:
  name: letsencrypt-prod
spec:
  acme:
    server: https://acme-v02.api.letsencrypt.org/directory
    email: ops@example.com
    privateKeySecretRef:
      name: letsencrypt-prod-key
    solvers:
      - http01:
          ingress:
            class: nginx
---
apiVersion: cert-manager.io/v1
kind: Certificate
metadata:
  name: app-tls
  namespace: production
spec:
  secretName: app-tls-secret
  issuerRef:
    name: letsencrypt-prod
    kind: ClusterIssuer
  dnsNames:
    - app.example.com
    - api.example.com
  renewBefore: 360h  # renew 15 days before expiry
```

## mTLS certificate rotation

For service-to-service mTLS, use short-lived certificates (hours to days)
issued by an internal CA:

- **SPIFFE/SPIRE** — workload identity framework. Issues X.509 SVIDs with
  configurable TTL (default 1 hour). Automatic rotation.
- **Istio Citadel** — issues mTLS certs to sidecar proxies, default 24h TTL.
- **Vault PKI** — HashiCorp Vault as internal CA with programmable TTL.

Short-lived certificates eliminate the need for CRL/OCSP revocation checking
— the certificate expires before a revocation would propagate.

## Anti-patterns

- **Manual renewal reminders** — calendar reminders fail. People leave, are
  on vacation, or forget. Automate with ACME.
- **Long-lived internal certificates** — internal certs with 10-year validity
  are a security risk. If the key is compromised, the window of exposure is
  a decade. Use short-lived certs with automated rotation.
- **Wildcard certificates everywhere** — wildcards reduce the number of certs
  to manage but increase blast radius if the key is compromised. Use per-
  service certificates where feasible.
- **Ignoring certificate transparency logs** — CT logs are public. Monitor
  them for unauthorized certificate issuance for your domains (crt.sh,
  Certspotter).

## Gotchas

- **DNS-01 challenge propagation delays** — DNS TXT records may take minutes
  to propagate. ACME clients must wait for propagation before verification.
- **Rate limits** — Let's Encrypt limits: 50 certificates per registered
  domain per week, 5 duplicate certificates per week. Plan around these for
  large deployments.
- **CAA records** — DNS CAA records restrict which CAs can issue for your
  domain. Ensure your chosen CA is listed in your CAA records.
- **cert-manager CRD upgrades** — cert-manager CRD upgrades require careful
  ordering (CRDs before the controller). Follow the upgrade guide exactly.
- **Clock skew** — certificate validity checking depends on accurate system
  time. Ensure NTP is configured on all hosts.

## Verification

- `openssl s_client -connect host:443` — verify the served certificate chain.
- `kubectl get certificates -A` — check cert-manager certificate status.
- Alert on certificates expiring within 14 days (`tls_certificate_expiry_monitoring.md`).
- Monitor CT logs for your domains using Certspotter or crt.sh.
- Test renewal by manually triggering a cert-manager renewal and verifying
  the new certificate is served.

## Related

- `documentation/docs/policies/monitoring/tls-certificate-expiry-monitoring.md`
- `documentation/docs/policies/security/dns-caa-certificate-issuance-policy.md`
- `documentation/docs/policies/security/spiffe-workload-identity-and-short-lived-mtls.md`
- `documentation/docs/policies/infra/arc-github-runners-k8s.md`

## Source URLs (verified 2026-08-16)

- TLS certificate lifetimes reduced to 47 days — https://www.digicert.com/blog/tls-certificate-lifetimes-will-officially-reduce-to-47-days
- SSL/TLS certificate lifespan reduction — https://www.manageengine.com/key-manager/ssl-tls-certificate-lifespan-reduced-to-47-days.html
- Certificate lifecycle management guide 2026 — https://accutivesecurity.com/navigating-certificate-lifecycle-management/
- The end of manual TLS certificate management — https://www.cloudmagazin.com/en/2026/07/18/automated-acme-tls-certificates-2026/
- CISOs prepare for short-lived TLS certificates — https://www.csoonline.com/article/4097721/how-cisos-can-prepare-for-the-new-era-of-short-lived-tls-certificates.html
