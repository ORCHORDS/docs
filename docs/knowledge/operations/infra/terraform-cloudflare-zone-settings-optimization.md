# Terraform Cloudflare Zone Settings Optimization

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

Zone-level performance and security knobs — TLS minimum version, HSTS, security level, Early Hints, HTTP/3, Rocket Loader, Browser Cache TTL — are changed manually in the dashboard, creating drift and making it impossible to replicate settings across staging and production zones consistently.

## Context

`cloudflare_zone_settings_override` lets you declare every zone-level toggle in Terraform. One resource controls the full settings block; Terraform computes only the delta and applies it, leaving unspecified settings at their current values. Most settings are eventually consistent (seconds); a few (HSTS preload, Universal SSL) take minutes and affect externally observable behaviour — plan and apply with care.

---

## Declaring the Resource

```hcl
resource "cloudflare_zone_settings_override" "orchords" {
  zone_id = var.zone_id

  settings {
    # TLS
    min_tls_version          = "1.2"
    tls_1_3                  = "zrt"          # 0-RTT enabled
    ssl                      = "strict"
    always_use_https         = "on"
    automatic_https_rewrites = "on"

    # HTTP version
    http3         = "on"
    http2         = "on"
    zero_rtt      = "on"

    # Performance
    early_hints         = "on"
    rocket_loader       = "off"     # breaks some SPAs
    browser_cache_ttl   = 14400
    cache_level         = "aggressive"
    development_mode    = "off"

    # Security
    security_level        = "medium"
    challenge_ttl         = 1800
    browser_check         = "on"
    hotlink_protection    = "on"
    email_obfuscation     = "on"
    server_side_exclude   = "on"

    # HSTS — changes propagate to preload lists; do not toggle lightly
    security_header {
      enabled            = true
      include_subdomains = true
      max_age            = 31536000
      nosniff            = true
      preload            = false   # keep false until you are certain
    }

    # Compression
    brotli  = "on"
    minify {
      js   = "off"   # use build-time minification instead
      css  = "off"
      html = "off"
    }
  }
}
```

## Separate Staging and Production with Variables

```hcl
# variables.tf
variable "zone_settings" {
  type = object({
    security_level    = string
    development_mode  = string
    browser_cache_ttl = number
  })
}

# terraform.tfvars — staging
zone_settings = {
  security_level    = "essentially_off"
  development_mode  = "on"
  browser_cache_ttl = 0
}

# terraform.tfvars — production
zone_settings = {
  security_level    = "medium"
  development_mode  = "off"
  browser_cache_ttl = 14400
}
```

## TLS Settings Module Pattern

```hcl
# modules/cloudflare-tls/main.tf
variable "zone_id"         { type = string }
variable "min_tls_version" { type = string; default = "1.2" }
variable "ssl_mode"        { type = string; default = "strict" }

resource "cloudflare_zone_settings_override" "tls" {
  zone_id = var.zone_id
  settings {
    min_tls_version          = var.min_tls_version
    ssl                      = var.ssl_mode
    tls_1_3                  = "zrt"
    always_use_https         = "on"
    automatic_https_rewrites = "on"
  }
}

output "applied_ssl_mode" {
  value = cloudflare_zone_settings_override.tls.settings[0].ssl
}
```

## Reading Current Zone Settings Before Import

```bash
# Fetch current settings JSON for a zone before terraform import
curl -s "https://api.cloudflare.com/client/v4/zones/${ZONE_ID}/settings" \
  -H "Authorization: Bearer ${CF_API_TOKEN}" | jq '.result[] | {id, value}'

# Import existing zone into Terraform state
terraform import cloudflare_zone_settings_override.orchords <zone_id>

# Check planned drift — no surprises before apply
terraform plan -var="zone_id=${ZONE_ID}"
```

## CI Gate: Detect Development Mode Drift

```yaml
# .github/workflows/zone-settings-guard.yml
name: zone-settings-guard
on:
  schedule:
    - cron: "0 * * * *"   # hourly

jobs:
  check:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: hashicorp/setup-terraform@v3

      - name: terraform plan
        env:
          CLOUDFLARE_API_TOKEN: ${{ secrets.CF_API_TOKEN }}
          TF_VAR_zone_id: ${{ secrets.CF_ZONE_ID }}
        run: |
          terraform init -input=false
          terraform plan -detailed-exitcode -out=tf.plan
        # exit code 2 = diff exists; treat as failure

      - name: alert on drift
        if: failure()
        run: echo "Zone settings have drifted — check Terraform plan output"
```

## Anti-patterns

- Setting `development_mode = "on"` in production Terraform — it bypasses cache and has a 3-hour auto-revert; remove it from the resource or Terraform will fight the revert.
- Enabling `rocket_loader = "on"` for React/Vue SPAs — it defers inline script execution and breaks hydration.
- Setting `preload = true` in the HSTS block before confirming all subdomains serve HTTPS — preloading removes a domain from browsers for months even after the header is removed.
- Using `browser_cache_ttl = 0` in production — it defeats edge caching and increases origin load.

## Gotchas

- `cloudflare_zone_settings_override` is additive/delta: Terraform only manages the settings you declare. Unspecified settings retain their dashboard values and do not appear in the plan.
- `tls_1_3 = "zrt"` enables both TLS 1.3 and 0-RTT. 0-RTT replays are a risk for non-idempotent POSTs — set to `"on"` (TLS 1.3 without 0-RTT) for APIs.
- `ssl = "strict"` requires a valid origin certificate. Switching from `"flexible"` to `"strict"` will break origins with self-signed certs that were relying on flexible mode.
- `development_mode` auto-reverts after 3 hours at the Cloudflare API level. Terraform will show a plan diff on the next run even if you did not change anything.

## Verification

```bash
# Verify TLS minimum version via external probe
curl -sv --tlsv1.1 --tls-max 1.1 https://example.com 2>&1 | grep -E "SSL|alert"
# Expect: "alert handshake failure" if min TLS 1.2 is enforced

# Verify HSTS header
curl -sI https://example.com | grep -i strict-transport
# Expect: Strict-Transport-Security: max-age=31536000; includeSubDomains

# Verify HTTP/3 advertisement
curl -sI https://example.com | grep -i alt-svc
# Expect: alt-svc: h3=":443"; ma=86400

# Check Terraform state matches live settings
terraform show -json | jq '.values.root_module.resources[] |
  select(.type=="cloudflare_zone_settings_override") | .values.settings'
```

## Related

- `terraform-cloudflare-waf-managed-rules-deployment.md`
- `terraform-cloudflare-rate-limiting-rules.md`
- `cloudflare-mtls-client-certificates-terraform.md`
- `ssl-tls-certificate-management.md`
- `terraform-cloudflare-dns-dnssec.md`

## Sources

- https://registry.terraform.io/providers/cloudflare/cloudflare/latest/docs/resources/zone_settings_override
- https://developers.cloudflare.com/fundamentals/reference/policies-compliances/cloudflare-limits/
- https://developers.cloudflare.com/ssl/edge-certificates/additional-options/http-strict-transport-security/
- https://developers.cloudflare.com/speed/optimization/protocol/http3/
