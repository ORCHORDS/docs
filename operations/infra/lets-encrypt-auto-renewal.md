# lets-encrypt-auto-renewal

**Issue:** Automating Let's Encrypt certificate issuance and renewal without downtime
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Certificates issued via Certbot or ACME clients expire after 90 days. Manual renewal is error-prone and causes outages. The HTTP-01 challenge fails behind a CDN or load balancer; DNS-01 is the reliable alternative.

## Pattern / Solution
Use DNS-01 challenge with automatic DNS provider hooks for zero-downtime renewal.

**Certbot with DNS-01 (Cloudflare example):**
```bash
pip install certbot-dns-cloudflare

# /etc/letsencrypt/cloudflare.ini
dns_cloudflare_api_token = <zone-edit-token>

certbot certonly \
  --dns-cloudflare \
  --dns-cloudflare-credentials /etc/letsencrypt/cloudflare.ini \
  -d example.com -d "*.example.com" \
  --preferred-challenges dns-01

# Renew (run via cron or systemd timer)
certbot renew --quiet
```

**Systemd timer (preferred over cron):**
```ini
# /etc/systemd/system/certbot.timer
[Timer]
OnCalendar=*-*-* 02,14:00:00
RandomizedDelaySec=1h
Persistent=true

[Install]
WantedBy=timers.target
```

**Reload Nginx after renewal:**
```ini
# /etc/letsencrypt/renewal-hooks/deploy/reload-nginx.sh
#!/bin/bash
systemctl reload nginx
```

**Kubernetes (cert-manager):**
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
    - dns01:
        cloudflare:
          apiTokenSecretRef:
            name: cloudflare-api-token
            key: api-token
```

## Gotchas
- Rate limits: 50 certificates per registered domain per week; 5 duplicate certificates per week. Use staging (`acme-staging-v02`) for testing.
- HTTP-01 challenge requires port 80 to be reachable from Let's Encrypt servers; blocks if behind strict firewall or Cloudflare proxy.
- Wildcard certificates require DNS-01; HTTP-01 cannot issue wildcards.
- cert-manager uses a separate ACME account per `ClusterIssuer`; rotating the private key requires re-registering.

## Related
- `ssl-tls-certificate-management.md`
- `cloudflare-dns-api.md`
- `cert-manager-2026.md`
