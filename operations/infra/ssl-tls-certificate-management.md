# ssl-tls-certificate-management

**Issue:** Managing TLS certificate lifecycle — issuance, renewal, rotation, and monitoring
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Certificates expire silently, causing outages. Certificate stores across load balancers, CDNs, and internal services diverge. Wildcard certificates create false confidence when new subdomains emerge.

## Pattern / Solution
Treat certificates as infrastructure: automate issuance, track expiry, and alert early.

```bash
# Check expiry of a live certificate
echo | openssl s_client -connect example.com:443 -servername example.com 2>/dev/null \
  | openssl x509 -noout -dates

# Check a certificate file on disk
openssl x509 -noout -dates -in /etc/ssl/certs/example.crt

# Verify cert chain is complete (no intermediate missing)
openssl s_client -connect example.com:443 -showcerts 2>/dev/null | grep "s:/\|i:/"
```

Alert thresholds (Prometheus / blackbox_exporter):
```yaml
# prometheus rules
- alert: CertExpiryWarning
  expr: probe_ssl_earliest_cert_expiry - time() < 30 * 24 * 3600
  labels:
    severity: warning
- alert: CertExpiryCritical
  expr: probe_ssl_earliest_cert_expiry - time() < 7 * 24 * 3600
  labels:
    severity: critical
```

Storage locations to audit:
- Load balancer / CDN (Cloudflare, AWS ACM, GCP Certificate Manager)
- Kubernetes secrets (`kubectl get secret -A | grep tls`)
- Nginx / HAProxy config directories
- Internal CA for mTLS (service mesh)

Rotation checklist:
1. Issue new certificate (staging → prod ACME or CA)
2. Deploy to all listeners simultaneously
3. Verify with `openssl s_client` from multiple vantage points
4. Delete old certificate after 24 h observation

## Gotchas
- Wildcard certs (`*.example.com`) do not cover the apex (`example.com`) or second-level subdomains (`a.b.example.com`).
- CT (Certificate Transparency) logs are public — anyone can enumerate your subdomains via `crt.sh`.
- OCSP stapling must be explicitly enabled in Nginx (`ssl_stapling on;`); without it, browsers make blocking OCSP requests.
- AWS ACM certificates cannot be exported; mTLS scenarios require importing a custom CA.

## Related
- `lets-encrypt-auto-renewal.md`
- `nginx-reverse-proxy-config.md`
- `prometheus-alertmanager-config.md`
