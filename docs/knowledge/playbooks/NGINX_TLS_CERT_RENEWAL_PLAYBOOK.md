# NGINX TLS Certificate Renewal Playbook

## Purpose

Define the operational procedure for renewing TLS certificates served by NGINX or the NGINX Ingress Controller without service disruption. The procedure covers both ACME / Let's Encrypt and private CA scenarios.

## Audience

Platform engineers, SREs, and security engineers.

## Pre-conditions

- NGINX 1.22+ (per `NGINX_VERSION_GOVERNANCE.md`).
- Certificates are managed via cert-manager, acme.sh, or `lego`.
- The renewal job is automated.
- Monitoring alerts on certificate expiry < 30 days.

## Procedure

### Step 1 — Detect

1. Confirm the certificate is approaching expiry.
2. `echo | openssl s_client -servername <host> -connect <host>:443 2>/dev/null | openssl x509 -noout -dates`.
3. Alert threshold: 30 days, 14 days, 7 days.

### Step 2 — Renew

4. Trigger the renewal job:
   - `cert-manager`: annotation on the Ingress (`cert-manager.io/renew-before`).
   - `acme.sh`: `acme.sh --renew -d <domain>`.
   - `lego`: `lego renew --domain <domain>`.
5. Confirm the new certificate is issued.

### Step 3 — Reload NGINX

6. Reload NGINX with zero downtime:
   - `nginx -s reload`.
   - For ingress-nginx: `kubectl exec -n ingress-nginx <pod> -- nginx -s reload`.
7. Confirm the new certificate is in memory.

### Step 4 — Verify

8. Re-run the `openssl s_client` check.
9. Confirm the new `notAfter` date.
10. Confirm the chain is valid (intermediate + root).

### Step 5 — Validate against CT logs

11. Submit the certificate to CT logs (Let's Encrypt does this automatically).
12. Verify via `crt.sh` or `certspotter`.

### Step 6 — Cleanup

13. Remove the old certificate from the secret store.
14. Remove the old certificate file from disk.

### Step 7 — Monitor

15. Confirm monitoring does not alert after renewal.
16. Update the expiry tracker.

## Rollback

If a renewal breaks a domain:

1. Restore the previous certificate from the secret store.
2. Reload NGINX.
3. Investigate the renewal issue.

## References

- `NGINX_VERSION_GOVERNANCE.md`
- `TLS_RFC_8446_VERSION_GOVERNANCE.md`
- cert-manager: `https://cert-manager.io/docs/`
- acme.sh: `https://github.com/acmesh-official/acme.sh`
- Let's Encrypt: `https://letsencrypt.org/docs/`
