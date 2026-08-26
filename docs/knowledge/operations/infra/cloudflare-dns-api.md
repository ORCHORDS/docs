# cloudflare-dns-api

**Issue:** Managing Cloudflare DNS records programmatically via the API and Terraform
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Manual record edits in the Cloudflare dashboard create drift, are not auditable, and block GitOps workflows. DNS changes need to be part of the same IaC pipeline as compute changes.

## Pattern / Solution
Use scoped API tokens (not the global API key) and manage records through Terraform or the Cloudflare CLI.

**Create a scoped token (Zone:DNS:Edit for specific zones only):**
```
Cloudflare Dashboard → My Profile → API Tokens → Create Token
Template: Edit zone DNS → limit to specific zone
```

**Terraform provider:**
```hcl
terraform {
  required_providers {
    cloudflare = {
      source  = "cloudflare/cloudflare"
      version = "~> 4.0"
    }
  }
}

provider "cloudflare" {
  api_token = <redacted-secret>
}

resource "cloudflare_record" "www" {
  zone_id = var.zone_id
  name    = "www"
  type    = "A"
  value   = "203.0.113.10"
  ttl     = 300
  proxied = false
}

resource "cloudflare_record" "wildcard" {
  zone_id = var.zone_id
  name    = "*"
  type    = "CNAME"
  value   = "example.com"
  ttl     = 1      # 1 = Auto when proxied
  proxied = true
}
```

**Raw API (bash):**
```bash
CF_TOKEN="your-token"
ZONE_ID="your-zone-id"

# List records
curl -s -X GET "https://api.cloudflare.com/client/v4/zones/$ZONE_ID/dns_records" \
  -H "Authorization: Bearer $CF_TOKEN" | jq '.result[] | {name, type, content}'

# Create a record
curl -s -X POST "https://api.cloudflare.com/client/v4/zones/$ZONE_ID/dns_records" \
  -H "Authorization: Bearer $CF_TOKEN" \
  -H "Content-Type: application/json" \
  --data '{"type":"A","name":"api","content":"203.0.113.20","ttl":300}'
```

## Gotchas
- `proxied = true` overrides TTL to 300 s and hides origin IP — verify proxy mode before applying.
- Deleting a proxied record also deletes all associated Page Rules and WAF overrides tied to that hostname.
- The API rate limit is 1200 requests per 5 minutes per token — avoid polling loops; use webhooks or Terraform state.
- Zone IDs are not secret but API tokens are; never commit tokens to version control.

## Related
- `dns-propagation-debugging.md`
- `dns-ttl-strategy.md`
- `lets-encrypt-auto-renewal.md`
- `wrangler-deploys.md`
