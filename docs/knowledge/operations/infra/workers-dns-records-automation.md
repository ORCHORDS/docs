# Automated DNS Record Management with Terraform

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

DNS records are manually created in the Cloudflare dashboard and drift from the actual Workers routes configuration. When a new Worker is deployed its route and CNAME are not created, causing 522 errors. You need DNS record creation to be part of the same Terraform apply that deploys the Worker, and you need apex domain CNAME flattening to work correctly without MX record conflicts.

## Context

Cloudflare's DNS is authoritative for all example.com zones. Workers routes require either:
1. A proxied DNS record (`orange-cloud`) at the hostname, or
2. A `workers.dev` subdomain (not suitable for production).

Because Cloudflare proxies the traffic, CNAME flattening at the apex (`@`) is handled transparently — Cloudflare resolves the CNAME internally and returns A/AAAA records to clients, bypassing the RFC 1034 restriction that prohibits CNAMEs at the zone apex.

The `cloudflare_record` Terraform resource manages all record types. For Workers, only `CNAME` (proxied) or `A` (proxied, pointing to `192.0.2.1` as a placeholder) are required — actual routing is handled by the Workers route, not DNS resolution.

## Solution

```hcl
# variables.tf
variable "zone_id" {
  type = string
}

variable "zone_name" {
  type    = string
  default = "example.com"
}

variable "workers" {
  description = "Map of worker name to hostname and script"
  type = map(object({
    hostname    = string
    script_name = string
    pattern     = string
  }))
  default = {
    api = {
      hostname    = "api.example.com"
      script_name = "orchords-api-worker"
      pattern     = "api.example.com/*"
    }
    webhooks = {
      hostname    = "hooks.example.com"
      script_name = "orchords-webhooks-worker"
      pattern     = "hooks.example.com/*"
    }
    dashboard = {
      hostname    = "app.example.com"
      script_name = "orchords-dashboard-worker"
      pattern     = "app.example.com/*"
    }
  }
}
```

```hcl
# dns_records.tf

# Proxied CNAME for each Worker hostname
# Points to the zone apex so Cloudflare handles routing internally.
# The actual value doesn't matter for Workers-proxied records;
# Cloudflare intercepts before DNS resolution.
resource "cloudflare_record" "worker_cname" {
  for_each = var.workers

  zone_id = var.zone_id
  name    = each.value.hostname
  type    = "CNAME"
  content = var.zone_name
  proxied = true
  ttl     = 1 # Auto — required when proxied = true

  comment = "Managed by Terraform — Worker: ${each.key} [wave-84]"

  lifecycle {
    # Prevent accidental deletion of live DNS records
    prevent_destroy = true
  }
}

# Workers routes tied to the DNS records
resource "cloudflare_workers_route" "worker_route" {
  for_each = var.workers

  zone_id     = var.zone_id
  pattern     = each.value.pattern
  script_name = each.value.script_name

  depends_on = [cloudflare_record.worker_cname]
}

# Apex domain — CNAME flattening for example.com root
# Cloudflare resolves this CNAME and returns A records to clients
resource "cloudflare_record" "apex_cname" {
  zone_id = var.zone_id
  name    = "@"
  type    = "CNAME"
  content = "app.example.com"
  proxied = true
  ttl     = 1

  comment = "Apex CNAME flattening — managed by Terraform"
}

# MX records — must coexist with apex CNAME flattening
# Cloudflare handles CNAME flattening without breaking MX records
resource "cloudflare_record" "mx_primary" {
  zone_id  = var.zone_id
  name     = "@"
  type     = "MX"
  content  = "aspmx.l.google.com"
  priority = 1
  ttl      = 3600
}

resource "cloudflare_record" "mx_secondary" {
  zone_id  = var.zone_id
  name     = "@"
  type     = "MX"
  content  = "alt1.aspmx.l.google.com"
  priority = 5
  ttl      = 3600
}

# SPF TXT record
resource "cloudflare_record" "spf" {
  zone_id = var.zone_id
  name    = "@"
  type    = "TXT"
  content = "v=spf1 include:_spf.google.com include:sendgrid.net ~all"
  ttl     = 3600
}

# DKIM — dynamically generated subdomain for email provider
resource "cloudflare_record" "dkim_google" {
  zone_id = var.zone_id
  name    = "google._domainkey"
  type    = "TXT"
  content = var.google_dkim_value
  ttl     = 3600
}

variable "google_dkim_value" {
  type      = string
  sensitive = true
}
```

```hcl
# external_data_dns.tf
# Dynamically generate DNS records from D1 database via external data source
# The script queries D1 for registered customer subdomains and returns JSON.

data "external" "custom_domains" {
  program = ["node", "${path.module}/scripts/fetch-custom-domains.js"]

  query = {
    d1_database_id = var.d1_database_id
    account_id     = var.cloudflare_account_id
  }
}

locals {
  # Parse JSON output from the external data source
  # Expected shape: { "domains": [{"name": "customer.example.com", "target": "origin.example.com"}] }
  custom_domains = jsondecode(data.external.custom_domains.result.domains_json)
}

resource "cloudflare_record" "custom_domain" {
  for_each = { for d in local.custom_domains : d.name => d }

  zone_id = var.zone_id
  name    = each.value.name
  type    = "CNAME"
  content = each.value.target
  proxied = true
  ttl     = 1

  comment = "Customer custom domain — auto-generated from D1"
}

variable "d1_database_id" {
  type = string
}

variable "cloudflare_account_id" {
  type = string
}
```

```javascript
// scripts/fetch-custom-domains.js
// Called by the `external` data source — reads stdin JSON, queries D1, writes JSON to stdout

const https = require('https');

async function queryD1(accountId, databaseId, sql, apiToken) {
  return new Promise((resolve, reject) => {
    const body = JSON.stringify({ sql, params: [] });
    const options = {
      hostname: 'api.cloudflare.com',
      path: `/client/v4/accounts/${accountId}/d1/database/${databaseId}/query`,
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${apiToken}`,
        'Content-Type': 'application/json',
        'Content-Length': Buffer.byteLength(body),
      },
    };
    const req = https.request(options, (res) => {
      let data = '';
      res.on('data', (chunk) => data += chunk);
      res.on('end', () => resolve(JSON.parse(data)));
    });
    req.on('error', reject);
    req.write(body);
    req.end();
  });
}

async function main() {
  const input = JSON.parse(await new Promise(r => {
    let buf = '';
    process.stdin.on('data', c => buf += c);
    process.stdin.on('end', () => r(buf));
  }));

  const apiToken = process.env.CLOUDFLARE_API_TOKEN;
  const result = await queryD1(
    input.account_id,
    input.d1_database_id,
    'SELECT subdomain AS name, origin_target AS target FROM custom_domains WHERE active = 1',
    apiToken
  );

  const domains = result.result?.[0]?.results ?? [];
  // External data source requires all values to be strings
  process.stdout.write(JSON.stringify({ domains_json: JSON.stringify(domains) }));
}

main().catch(e => { process.stderr.write(e.message); process.exit(1); });
```

## Implementation Details

**TTL behavior for proxied records.** When `proxied = true` the TTL is always 300 seconds (auto), regardless of what you set. Cloudflare ignores the `ttl` value for proxied records. Set `ttl = 1` (which means auto in the API) to avoid a perpetual diff in `terraform plan`.

**NS delegation.** If you delegate a subdomain to another nameserver (e.g., `payments.example.com` managed by a third party), use `type = "NS"` records. Do not proxy NS records — NS records cannot be proxied and must have `proxied = false`.

```hcl
resource "cloudflare_record" "ns_delegation" {
  zone_id = var.zone_id
  name    = "payments"
  type    = "NS"
  content = "ns1.thirdparty-dns.com"
  proxied = false
  ttl     = 86400
}
```

**`for_each` vs `count`.** Use `for_each` with a map keyed by a stable identifier (hostname). Using `count` with a list causes record recreation when list order changes.

**Import existing records.** Before managing an existing DNS record with Terraform, import it to avoid duplicate record conflicts:

```bash
terraform import 'cloudflare_record.worker_cname["api"]' <zone_id>/<record_id>
```

## Anti-patterns

- **Unproxied records for Worker hostnames.** If `proxied = false`, traffic bypasses Cloudflare entirely and the Worker is never invoked. Always set `proxied = true` for Worker-served hostnames.
- **Using `A` records with real IPs instead of CNAME for Workers.** Workers don't have a fixed IP. Use a placeholder IP (`192.0.2.1`) only if you cannot use CNAME, and always with `proxied = true`.
- **Hardcoding DNS records outside Terraform.** Dashboard-created records become orphaned and cause drift. Run `terraform plan` regularly and remediate drift immediately.
- **Deleting and recreating records to change TTL.** Cloudflare supports in-place TTL updates. Terraform detects TTL changes and updates without recreating the record.
- **Setting `ttl` on proxied records to anything other than `1`.** It causes perpetual plan drift because the API normalizes it to `1` regardless.

## Gotchas

- The `cloudflare_record` resource uses `content` (not `value`) for the record value in provider v4+. The old `value` attribute was removed.
- CNAME flattening at the apex only works when Cloudflare is the authoritative nameserver. It does not work for non-Cloudflare zones.
- The `external` data source re-runs on every `terraform plan`. Slow D1 queries will slow down every plan. Add a cache layer (e.g., write results to an S3 file and refresh it via a separate pipeline) if query latency is a concern.
- Creating a Workers route with `script_name` that doesn't exist yet returns an API error. Use `depends_on` to ensure the script is uploaded before the route is created.
- Cloudflare limits the number of DNS records per zone by plan tier. Check your limit before generating hundreds of records from D1 data.

## Verification

```bash
# Confirm DNS record exists and is proxied
curl -s "https://api.cloudflare.com/client/v4/zones/${ZONE_ID}/dns_records?name=api.example.com" \
  -H "Authorization: Bearer ${CF_API_TOKEN}" | jq '.result[] | {name, type, content, proxied}'

# Resolve the hostname and confirm Cloudflare IPs are returned (not origin)
dig +short api.example.com
# Should return Cloudflare anycast IPs (104.x.x.x or 172.64.x.x)

# Confirm Workers route is registered
curl -s "https://api.cloudflare.com/client/v4/zones/${ZONE_ID}/workers/routes" \
  -H "Authorization: Bearer ${CF_API_TOKEN}" | jq '.result[]'

# Test the Worker responds correctly via the DNS-resolved hostname
curl -sI https://api.example.com/v1/health | grep -E 'HTTP|cf-ray|server'
```

## Related

- `documentation/docs/policies/infra/terraform-cloudflare.md`
- `documentation/docs/policies/infra/workers-cdn-cache-rules-terraform.md`
- `documentation/docs/policies/infra/wrangler-environments-matrix.md`
- Cloudflare DNS docs: https://developers.cloudflare.com/dns/
- `cloudflare_record` Terraform resource reference

## Sources

- Cloudflare Terraform Provider v4 — cloudflare_record
- Cloudflare CNAME Flattening documentation
- Internal example.com DNS runbook v5
- Cloudflare Workers Routes and DNS integration guide
