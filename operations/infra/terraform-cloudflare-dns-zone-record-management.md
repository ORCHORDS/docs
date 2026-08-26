# Terraform Cloudflare DNS Zone and Record Management

Date: 2026-08-23 / Author: example.com / Status: production

## Symptom / Use-case

Your team owns multiple Cloudflare zones and manages hundreds of DNS records across
staging and production. Manual console edits cause drift. You need reproducible Terraform
code that owns the full zone lifecycle — creation, NS delegation, record CRUD, proxy
toggle, TTL, and import — without accidentally destroying records managed by other teams.

---

## Context

Cloudflare DNS is managed through `cloudflare_zone` (zone entity) and
`cloudflare_record` (individual DNS records) resources in the
`cloudflare/cloudflare` Terraform provider ≥ 4.x. Key facts:

- Zones are account-scoped; records are zone-scoped.
- The `proxied` flag routes traffic through Cloudflare's network (orange-cloud).
  Proxied records force TTL to 1 (auto); unproxied records accept custom TTL values.
- SPF, DKIM, and DMARC records are `TXT` type with no special resource type.
- SRV and CAA records require nested `data {}` blocks, not a flat `value`.
- Use `lifecycle { prevent_destroy = true }` on zone resources in production.

Provider version pin: `~> 4.40`

---

## 1. Provider and Zone Resource

```hcl
terraform {
  required_providers {
    cloudflare = {
      source  = "cloudflare/cloudflare"
      version = "~> 4.40"
    }
  }
}

provider "cloudflare" {
  api_token = <redacted-secret>
}

variable "cloudflare_api_token" {
  description = "Scoped API token with Zone:Edit permission"
  type        = string
  sensitive   = true
}

variable "account_id" {
  type = string
}
```

```hcl
resource "cloudflare_zone" "example" {
  account_id = var.account_id
  zone       = "example.com"
  plan       = "free"   # free | pro | business | enterprise
  type       = "full"   # full (authoritative) | partial (CNAME setup)

  lifecycle {
    prevent_destroy = true
  }
}

output "zone_id"          { value = cloudflare_zone.example.id }
output "name_servers"     { value = cloudflare_zone.example.name_servers }
output "zone_status"      { value = cloudflare_zone.example.status }
```

Zone `status` moves through `initializing → pending → active`. NS delegation at your
registrar is required to reach `active`.

---

## 2. A / AAAA Records (Proxied and Unproxied)

```hcl
# Proxied A record — TTL is managed by Cloudflare (set to 1 = auto)
resource "cloudflare_record" "root_a" {
  zone_id = cloudflare_zone.example.id
  name    = "@"           # @ resolves to the zone apex
  type    = "A"
  value   = "203.0.113.10"
  proxied = true
  # ttl is ignored when proxied = true; Terraform sets it to 1 automatically
}

# Unproxied A record with explicit TTL
resource "cloudflare_record" "origin_a" {
  zone_id = cloudflare_zone.example.id
  name    = "origin"
  type    = "A"
  value   = "203.0.113.10"
  proxied = false
  ttl     = 300
}

resource "cloudflare_record" "root_aaaa" {
  zone_id = cloudflare_zone.example.id
  name    = "@"
  type    = "AAAA"
  value   = "2001:db8::1"
  proxied = true
}
```

---

## 3. CNAME Records

```hcl
resource "cloudflare_record" "www_cname" {
  zone_id = cloudflare_zone.example.id
  name    = "www"
  type    = "CNAME"
  value   = "example.com"   # target
  proxied = true
}

# Subdomain for external SaaS (unproxied required)
resource "cloudflare_record" "sendgrid_cname" {
  zone_id = cloudflare_zone.example.id
  name    = "em1234"
  type    = "CNAME"
  value   = "u1234.wl.sendgrid.net"
  proxied = false
  ttl     = 3600
}
```

---

## 4. MX Records

```hcl
locals {
  mx_records = {
    "aspmx.l.google.com"      = 1
    "alt1.aspmx.l.google.com" = 5
    "alt2.aspmx.l.google.com" = 5
    "alt3.aspmx.l.google.com" = 10
    "alt4.aspmx.l.google.com" = 10
  }
}

resource "cloudflare_record" "mx" {
  for_each = local.mx_records

  zone_id  = cloudflare_zone.example.id
  name     = "@"
  type     = "MX"
  value    = each.key
  priority = each.value
  ttl      = 3600
  proxied  = false
}
```

---

## 5. TXT Records (SPF, DKIM, DMARC)

```hcl
resource "cloudflare_record" "spf" {
  zone_id = cloudflare_zone.example.id
  name    = "@"
  type    = "TXT"
  value   = "v=spf1 include:_spf.google.com ~all"
  ttl     = 3600
}

resource "cloudflare_record" "dmarc" {
  zone_id = cloudflare_zone.example.id
  name    = "_dmarc"
  type    = "TXT"
  value   = "v=DMARC1; p=reject; rua=mailto:dmarc@example.com; pct=100"
  ttl     = 3600
}

# DKIM (value sourced from Google Workspace or email provider)
resource "cloudflare_record" "dkim" {
  zone_id = cloudflare_zone.example.id
  name    = "google._domainkey"
  type    = "TXT"
  value   = var.dkim_txt_value   # long TXT value from email provider
  ttl     = 3600
}
```

---

## 6. SRV and CAA Records (Nested Data Blocks)

```hcl
# SRV record — requires data block, not value
resource "cloudflare_record" "sip_srv" {
  zone_id = cloudflare_zone.example.id
  name    = "_sip._tcp"
  type    = "SRV"

  data {
    service  = "_sip"
    proto    = "_tcp"
    name     = "example.com"
    priority = 10
    weight   = 20
    port     = 5060
    target   = "sip.example.com"
  }
}

# CAA record — restricts which CAs may issue certificates
resource "cloudflare_record" "caa_letsencrypt" {
  zone_id = cloudflare_zone.example.id
  name    = "@"
  type    = "CAA"

  data {
    flags = 0
    tag   = "issue"
    value = "letsencrypt.org"
  }
}

resource "cloudflare_record" "caa_wildcard" {
  zone_id = cloudflare_zone.example.id
  name    = "@"
  type    = "CAA"

  data {
    flags = 0
    tag   = "issuewild"
    value = "letsencrypt.org"
  }
}
```

---

## 7. Importing Existing Records

```bash
# Format: <zone_id>/<record_id>
terraform import cloudflare_record.root_a <ZONE_ID>/<RECORD_ID>

# Get record ID via API
curl -s "https://api.cloudflare.com/client/v4/zones/$ZONE_ID/dns_records?type=A&name=example.com" \
  -H "Authorization: Bearer $CF_API_TOKEN" | jq '.result[].id'
```

Generate import blocks (Terraform ≥ 1.5) for bulk import:

```hcl
import {
  to = cloudflare_record.root_a
  id = "<zone_id>/<record_id>"
}
```

---

## Anti-patterns

- **Using `allow_overwrite = true` in production** — silently clobbers records managed by
  other Terraform states or external tools; never set this outside sandbox environments.
- **Managing NS and SOA records** — Cloudflare owns these; Terraform will error if you
  try to create them. Filter them out of any import automation.
- **Setting `ttl` on proxied records** — Terraform will flip it back to 1 on the next
  apply. Remove the attribute for proxied records.
- **One giant `cloudflare_record` block per record** — use `for_each` over a map for
  groups of homogeneous records (MX, multiple A records) to reduce boilerplate.
- **No `prevent_destroy` on zone resources** — destroying a zone removes all records and
  breaks DNS immediately.

---

## Gotchas

- Zone apex (`@`) CNAME is not standard DNS; Cloudflare supports it only when `proxied
  = true` (CNAME flattening). Unproxied apex CNAMEs will fail validation.
- Duplicate MX records with the same `value` at different priorities are allowed by the
  API but cause `for_each` key collisions in Terraform — use the hostname as the map key.
- `cloudflare_zone` `type = "partial"` (CNAME setup) zones do not get Cloudflare NS —
  you keep your registrar's NS. The resource behaves differently in this mode.
- Free plan zones cannot use some record types (e.g., DS records).
- After zone creation, Cloudflare may auto-scan and import existing DNS records.
  Run `terraform plan` after creation to detect unexpected resources.

---

## Verification

```bash
# Confirm zone is active
terraform output zone_status

# Check NS delegation
dig NS example.com +short

# Validate a specific record
dig A example.com @1.1.1.1 +short

# List all records in zone via API
curl -s "https://api.cloudflare.com/client/v4/zones/$ZONE_ID/dns_records?per_page=100" \
  -H "Authorization: Bearer $CF_API_TOKEN" | jq '.result[] | {name, type, content: .value // .data}'
```

---

## Related

- `cloudflare-dns-api.md`
- `cloudflare-email-routing-terraform-dns.md`
- `terraform-cloudflare-workers-routes-zone-config.md`
- `dns-ttl-strategy.md`
- `lets-encrypt-auto-renewal.md`

---

## Sources

- `cloudflare_zone` resource: https://registry.terraform.io/providers/cloudflare/cloudflare/latest/docs/resources/zone
- `cloudflare_record` resource: https://registry.terraform.io/providers/cloudflare/cloudflare/latest/docs/resources/record
- Cloudflare DNS record types: https://developers.cloudflare.com/dns/manage-dns-records/reference/dns-record-types/
- CNAME flattening: https://developers.cloudflare.com/dns/cname-flattening/
