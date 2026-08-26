# Custom Domain and TLS Certificate Management for Workers and Pages

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case
You have deployed a Cloudflare Worker or Pages project and need to serve it from a custom domain (e.g., `api.example.com` or `app.example.com`) with automatic TLS. The Cloudflare dashboard lets you add domains manually, but you want the process to be declarative, repeatable, and integrated with your Terraform pipeline so that domain registration, DNS, and TLS are all tracked in code.

---

## Context
Cloudflare automatically provisions and renews TLS certificates for any hostname proxied through its network, whether attached to a Worker via `cloudflare_worker_domain` or to a Pages project via `cloudflare_pages_domain`. The certificate is issued through Cloudflare's managed CA (backed by DigiCert or Let's Encrypt depending on plan) within minutes of DNS propagation. The domain must be in a Cloudflare-managed zone (orange-cloud proxy enabled) for the Worker/Pages binding to take effect. Terraform manages both the DNS record and the domain binding in a single plan, ensuring the two are always in sync. DNS propagation can be verified with `dig` and TLS validity with `curl`.

---

## Section 1 — Terraform Config for Worker Custom Domain

```hcl
# terraform/custom_domain.tf

variable "custom_domain" {
  description = "Custom hostname to attach to the Worker"
  default     = "api.example.com"
}

variable "pages_project_name" {
  description = "Cloudflare Pages project name"
  default     = "orchords-frontend"
}

variable "pages_custom_domain" {
  description = "Custom hostname for the Pages project"
  default     = "app.example.com"
}

# ── DNS record for the Worker custom domain ────────────────────────────────────
resource "cloudflare_record" "worker_api" {
  zone_id = var.cloudflare_zone_id
  name    = "api"           # => api.example.com
  type    = "AAAA"
  value   = "100::"         # Cloudflare anycast placeholder for proxied Workers
  proxied = true            # Must be true for Workers to intercept
  ttl     = 1               # Auto when proxied
}

# ── Attach the Worker script to the custom domain ──────────────────────────────
resource "cloudflare_worker_domain" "api" {
  account_id = var.cloudflare_account_id
  zone_id    = var.cloudflare_zone_id
  hostname   = var.custom_domain
  service    = cloudflare_worker_script.api.name

  depends_on = [cloudflare_record.worker_api]
}

# ── Pages custom domain ────────────────────────────────────────────────────────
resource "cloudflare_record" "pages_app" {
  zone_id = var.cloudflare_zone_id
  name    = "app"
  type    = "CNAME"
  value   = "${var.pages_project_name}.pages.dev"
  proxied = true
  ttl     = 1
}

resource "cloudflare_pages_domain" "frontend" {
  account_id   = var.cloudflare_account_id
  project_name = var.pages_project_name
  domain       = var.pages_custom_domain

  depends_on = [cloudflare_record.pages_app]
}

# ── Outputs for verification ───────────────────────────────────────────────────
output "worker_custom_domain" {
  value = cloudflare_worker_domain.api.hostname
}

output "pages_custom_domain" {
  value = cloudflare_pages_domain.frontend.domain
}
```

## Section 2 — Certificate Verification and Failure Handling

```typescript
// scripts/verify-cert.ts — run with ts-node or bun after deployment
// Polls the domain until TLS is valid or times out

const MAX_ATTEMPTS = 20;
const RETRY_INTERVAL_MS = 15_000;

async function verifyCert(hostname: string): Promise<void> {
  console.log(`Verifying TLS for ${hostname}...`);

  for (let attempt = 1; attempt <= MAX_ATTEMPTS; attempt++) {
    try {
      const res = await fetch(`https://${hostname}/`, {
        method: "HEAD",
        // In Node 18+ / Bun, fetch respects system TLS — real cert validation
        redirect: "manual",
      });
      if (res.status < 500) {
        console.log(`[${attempt}/${MAX_ATTEMPTS}] TLS OK — HTTP ${res.status}`);
        const server = res.headers.get("server") ?? "";
        const cfRay  = res.headers.get("cf-ray") ?? "(none)";
        console.log(`  Server: ${server}, CF-Ray: ${cfRay}`);
        return;
      }
      console.warn(`[${attempt}/${MAX_ATTEMPTS}] HTTP ${res.status} — retrying...`);
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      console.warn(`[${attempt}/${MAX_ATTEMPTS}] Fetch error: ${msg}`);

      // Detect certificate not yet provisioned
      if (msg.includes("certificate") || msg.includes("SSL")) {
        console.log("  Certificate not yet provisioned — waiting...");
      }
    }

    if (attempt < MAX_ATTEMPTS) {
      await new Promise((r) => setTimeout(r, RETRY_INTERVAL_MS));
    }
  }

  throw new Error(
    `TLS verification failed for ${hostname} after ${MAX_ATTEMPTS} attempts`
  );
}

// Usage: bun run scripts/verify-cert.ts api.example.com
const hostname = process.argv[2];
if (!hostname) {
  console.error("Usage: verify-cert.ts <hostname>");
  process.exit(1);
}
verifyCert(hostname).catch((err) => {
  console.error(err.message);
  process.exit(1);
});
```

## Section 3 — DNS Propagation and TLS Verification

```bash
# ── Deploy Terraform ───────────────────────────────────────────────────────────
terraform apply -auto-approve

# ── Verify DNS record is proxied (orange-cloud) ────────────────────────────────
# Should return Cloudflare anycast IPs, not your origin
dig api.example.com A +short
dig api.example.com AAAA +short

# Confirm the CNAME for Pages
dig app.example.com CNAME +short
# Expected: orchords-frontend.pages.dev.

# ── Check TLS certificate details ──────────────────────────────────────────────
curl -vvI https://api.example.com/ 2>&1 | grep -E 'subject|issuer|expire|SSL|HTTP'

# Alternative: openssl for detailed cert info
echo | openssl s_client -connect api.example.com:443 -servername api.example.com 2>/dev/null \
  | openssl x509 -noout -subject -issuer -dates

# ── Verify the Worker is responding on the custom domain ───────────────────────
curl -i https://api.example.com/health
# Expect: HTTP/2 200, server: cloudflare

# ── Handle domain verification failure ────────────────────────────────────────
# If the Pages domain stays in "pending" state:
wrangler pages domain list --project-name orchords-frontend
# Remove and re-add the domain if stuck:
wrangler pages domain remove app.example.com --project-name orchords-frontend
wrangler pages domain add   app.example.com --project-name orchords-frontend

# ── Poll until TLS is ready (using the TypeScript script above) ───────────────
bun run scripts/verify-cert.ts api.example.com
bun run scripts/verify-cert.ts app.example.com

# ── Check certificate expiry on a schedule (put in CI cron) ───────────────────
CERT_EXPIRY=$(echo | openssl s_client -connect api.example.com:443 \
  -servername api.example.com 2>/dev/null \
  | openssl x509 -noout -enddate \
  | cut -d= -f2)
echo "Certificate expires: $CERT_EXPIRY"
```

---

## Anti-patterns
- **Setting `proxied = false` on the DNS record** — the Worker/Pages binding only intercepts traffic when the record is orange-cloud proxied; grey-cloud bypasses Cloudflare entirely.
- **Using an A record pointing to your origin instead of the anycast placeholder** — Workers are not served from your origin IP; the AAAA `100::` placeholder (or a CNAME to `<worker>.workers.dev`) is the correct approach.
- **Manually adding domains in the dashboard alongside Terraform** — creates state drift; Terraform will delete the domain on the next apply if it doesn't know about it.
- **Not waiting for DNS propagation before testing TLS** — certificates are provisioned after the CNAME resolves; calling `curl` immediately after `apply` will show a certificate error that resolves itself within minutes.

---

## Gotchas
- `cloudflare_pages_domain` will stay in `pending` state if the CNAME record doesn't resolve to `<project>.pages.dev` — verify the DNS record before troubleshooting the certificate.
- Cloudflare's managed TLS does not support HTTPS at the origin for Workers (Workers run at the edge, not at an origin server) — there is no origin certificate to manage.
- The `cloudflare_worker_domain` resource requires the Worker script to exist first; always ensure the `cloudflare_worker_script` resource is applied before (or in the same plan as) the domain resource.
- Custom domains on Pages projects can take up to 10 minutes to become active after DNS propagation — this is normal, not an error.
- Wildcard custom domains (`*.example.com`) require an Enterprise plan for Pages; on lower plans, each subdomain needs its own `cloudflare_pages_domain` resource.

---

## Verification

```bash
# Confirm Terraform state includes both resources
terraform state list | grep -E 'worker_domain|pages_domain'

# Check certificate is Cloudflare-issued
curl -sI https://api.example.com/ | grep -i 'cf-ray\|server'

# Verify Pages domain status via Cloudflare API
curl -s -H "Authorization: Bearer $CF_API_TOKEN" \
  "https://api.cloudflare.com/client/v4/accounts/$CF_ACCOUNT_ID/pages/projects/$PAGES_PROJECT/domains" \
  | jq '.result[] | {domain: .name, status: .status, cert: .certificate_authority}'

# Confirm auto-renewal will work (check next renewal date)
echo | openssl s_client -connect api.example.com:443 \
  -servername api.example.com 2>/dev/null \
  | openssl x509 -noout -dates
```

---

## Related
- `terraform-cloudflare-workers-kv-r2.md`
- `cloudflare-tunnel-private-service-workers.md`

---

## Sources
- Cloudflare Worker Custom Domains — https://developers.cloudflare.com/workers/configuration/routing/custom-domains/
- Cloudflare Pages Custom Domains — https://developers.cloudflare.com/pages/configuration/custom-domains/
- Cloudflare Terraform `cloudflare_worker_domain` — https://registry.terraform.io/providers/cloudflare/cloudflare/latest/docs/resources/worker_domain
- Cloudflare Managed SSL/TLS — https://developers.cloudflare.com/ssl/edge-certificates/
