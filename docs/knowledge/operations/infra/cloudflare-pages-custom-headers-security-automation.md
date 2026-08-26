# Cloudflare Pages Custom Headers Security Automation

Date: 2026-08-23 / Author: example.com / Status: production

## Symptom / Use-case

Static sites deployed to Cloudflare Pages need strict HTTP security headers (CSP,
HSTS, X-Frame-Options, Permissions-Policy) to pass security audits and avoid
misconfiguration regression on every deploy.  Manually editing `_headers` files
inside the repo works but breaks when build tooling overwrites public/ output,
and there is no drift detection when a developer removes a header by accident.

## Context

Cloudflare Pages evaluates a `_headers` file at the root of the build output.
Headers are applied at the CDN edge before the response reaches the browser.
Unlike Workers, Pages has no programmatic header hook — all configuration lives
in the `_headers` plaintext format or, for redirect/rewrite rules, `_redirects`.
The IaC strategy is therefore a two-layer approach:

1. A CI step that generates and validates the `_headers` file before every build.
2. A Cloudflare Snippet or Transform Rule (Terraform-managed) that enforces a
   fallback header policy for routes where `_headers` is absent or incomplete.

---

## 1. Canonical `_headers` File Structure

```plaintext
# _headers  (placed in your framework's public/static output directory)
/*
  X-Frame-Options: DENY
  X-Content-Type-Options: nosniff
  Referrer-Policy: strict-origin-when-cross-origin
  Permissions-Policy: camera=(), microphone=(), geolocation=()
  Strict-Transport-Security: max-age=63072000; includeSubDomains; preload

/
  Content-Security-Policy: default-src 'self'; script-src 'self' 'nonce-{{nonce}}'; style-src 'self' 'unsafe-inline'; img-src 'self' data: https:; connect-src 'self' https://api.example.com; frame-ancestors 'none'

/api/*
  Cache-Control: no-store, no-cache
  Pragma: no-cache
```

Place this file in the directory that becomes the `pages_build_output_directory`
in `wrangler.toml` (e.g. `dist/`, `out/`, `.next/`).

---

## 2. CI Header Validation Script

```bash
#!/usr/bin/env bash
# scripts/validate-headers.sh — runs in CI before wrangler pages deploy
set -euo pipefail

HEADERS_FILE="${BUILD_OUTPUT_DIR:-dist}/_headers"
REQUIRED_HEADERS=(
  "X-Frame-Options"
  "X-Content-Type-Options"
  "Strict-Transport-Security"
  "Referrer-Policy"
  "Content-Security-Policy"
)

if [[ ! -f "$HEADERS_FILE" ]]; then
  echo "ERROR: $HEADERS_FILE not found after build" >&2
  exit 1
fi

for header in "${REQUIRED_HEADERS[@]}"; do
  if ! grep -q "$header" "$HEADERS_FILE"; then
    echo "ERROR: required header '$header' missing from $HEADERS_FILE" >&2
    exit 1
  fi
done

echo "All required security headers present in $HEADERS_FILE"
```

Add to GitHub Actions:

```yaml
# .github/workflows/deploy.yml
- name: Validate security headers
  env:
    BUILD_OUTPUT_DIR: dist
  run: bash scripts/validate-headers.sh

- name: Deploy to Pages
  run: wrangler pages deploy dist --project-name=example project-frontend
```

---

## 3. Terraform Transform Rule Fallback Policy

For requests that reach the edge without a `_headers` match (e.g. 404 pages or
edge-cached assets), a Cloudflare Transform Rule ensures the baseline headers
are always present.

```hcl
# infra/cloudflare_pages_headers.tf

resource "cloudflare_ruleset" "pages_security_headers" {
  zone_id     = var.zone_id
  name        = "Pages security header fallback"
  description = "Apply security headers to all Pages responses"
  kind        = "zone"
  phase       = "http_response_headers_transform"

  rules {
    action = "rewrite"
    action_parameters {
      headers {
        name      = "X-Frame-Options"
        operation = "set"
        value     = "DENY"
      }
      headers {
        name      = "X-Content-Type-Options"
        operation = "set"
        value     = "nosniff"
      }
      headers {
        name      = "Referrer-Policy"
        operation = "set"
        value     = "strict-origin-when-cross-origin"
      }
      headers {
        name      = "Strict-Transport-Security"
        operation = "set"
        value     = "max-age=63072000; includeSubDomains; preload"
      }
    }
    expression  = "(http.host contains \"pages.dev\" or http.host eq \"${var.pages_custom_domain}\")"
    description = "Security headers for Pages project"
    enabled     = true
  }
}
```

---

## 4. Pulumi Equivalent (TypeScript)

```typescript
// infra/pagesHeaders.ts
import * as cloudflare from "@pulumi/cloudflare";

const pagesHeadersRuleset = new cloudflare.Ruleset("pages-security-headers", {
  zoneId: zoneId,
  name: "Pages security header fallback",
  kind: "zone",
  phase: "http_response_headers_transform",
  rules: [{
    action: "rewrite",
    actionParameters: {
      headers: [
        { name: "X-Frame-Options",       operation: "set", value: "DENY" },
        { name: "X-Content-Type-Options", operation: "set", value: "nosniff" },
        { name: "Referrer-Policy",        operation: "set", value: "strict-origin-when-cross-origin" },
        { name: "Permissions-Policy",     operation: "set", value: "camera=(), microphone=()" },
      ],
    },
    expression: `(http.host eq "${pagesDomain}")`,
    description: "Baseline security headers",
    enabled: true,
  }],
});
```

---

## 5. Testing Header Presence After Deploy

```bash
# Spot-check deployed headers
DOMAIN="https://app.example.com"
curl -sI "$DOMAIN" | grep -iE \
  "x-frame-options|x-content-type|strict-transport|referrer-policy|content-security"

# Automated with httpx (CI-friendly)
httpx -u "$DOMAIN" -include-response-headers \
  -match-string "X-Frame-Options: DENY" -silent
```

---

## Anti-patterns

- Do not rely solely on `_headers` without the Transform Rule fallback — on a
  CDN cache HIT the `_headers` file is re-evaluated but edge rules are not
  bypassed; Transform Rules run after cache, ensuring consistent application.
- Do not put `Cache-Control: no-store` in `/*` — it defeats the Pages CDN for
  all assets.  Scope no-cache rules to `/api/*` and authenticated routes only.
- Do not hardcode nonces in `_headers`; nonces must be generated per-request and
  injected by a Worker or removed from the CSP if using static generation.

## Gotchas

- The `_headers` file must live in the **build output** directory, not the repo
  root.  If your framework copies only certain files, add an explicit copy step.
- Transform Rules run **after** `_headers`; if both set the same header the
  Transform Rule wins for `set`, but `add` accumulates duplicates — always use
  `set` in Transform Rules to avoid duplicate header values.
- Pages preview deployments on `*.pages.dev` require the Transform Rule
  expression to match the preview subdomain pattern, not just the custom domain.

## Verification

```bash
# Check HSTS preload eligibility
curl -sI https://app.example.com | grep -i strict-transport
# Expected: Strict-Transport-Security: max-age=63072000; includeSubDomains; preload

# Confirm no duplicate headers
curl -sI https://app.example.com | grep -ic "x-frame-options"
# Expected: 1
```

## Related

- `cloudflare-snippets-terraform-edge-js.md`
- `terraform-cloudflare-rate-limiting-rules.md`
- `cloudflare-workers-api-token-scoping.md`
- `workers-cold-start-bundle-size-optimization.md`

## Sources

- https://developers.cloudflare.com/pages/configuration/headers/
- https://developers.cloudflare.com/rules/transform/response-header-modification/
- https://registry.terraform.io/providers/cloudflare/cloudflare/latest/docs/resources/ruleset
- https://owasp.org/www-project-secure-headers/
