# subdomain-takeover-prevention

**Issue:** Dangling DNS records pointing to deprovisioned cloud resources enable subdomain takeover
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
When a CNAME or A record points to a cloud service (S3 bucket, GitHub Pages, Heroku dyno, Azure endpoint) that has been deleted, an attacker can register that resource and serve content under your subdomain — bypassing same-origin policy, stealing cookies, and hosting phishing pages.

## Pattern / Solution
```bash
# Check for dangling CNAMEs
dig staging.example.com CNAME
# If it returns something like *.s3.amazonaws.com but bucket doesn't exist — vulnerable

# Audit with can-i-take-over-xyz tooling
nuclei -t takeovers/ -u https://staging.example.com

# Prevention workflow
# 1. Before deleting cloud resource, remove DNS record first
# 2. Maintain a DNS record inventory linked to resource lifecycle
# 3. Use CNAME flattening (ALIAS records) at apex where supported
```
```yaml
# GitHub Actions: scan for takeover candidates weekly
- name: Subdomain takeover scan
  run: nuclei -t takeovers/ -list subdomains.txt -o results.json
```

## Gotchas
- GitHub Pages takeover: claim the repo before the attacker does if you see a dangling CNAME.
- Wildcard DNS `*.example.com` pointing to a shared service is particularly dangerous.
- Azure CDN, Fastly, and Heroku endpoints are frequent targets due to easy claim mechanics.
- Some services (Cloudflare) protect against takeover by requiring domain ownership verification.

## Related
- `open-redirect-prevention.md`
- `supply-chain-npm-security.md`
