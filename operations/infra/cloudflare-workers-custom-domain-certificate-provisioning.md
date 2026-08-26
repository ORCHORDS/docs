# Cloudflare Workers Custom Domain Certificate Provisioning

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

You deploy a Cloudflare Worker and assign it a custom domain (e.g. `api.example.com`)
instead of the default `*.workers.dev` subdomain. TLS certificate provisioning silently
fails or takes unexpectedly long, the domain shows an SSL error, or Terraform plan
reports the `cloudflare_worker_domain` resource as perpetually out of sync. You need
to understand the full certificate lifecycle — from DNS delegation to issuance to
renewal — and manage it reliably via IaC.

## Context

When you attach a custom domain to a Worker, Cloudflare automatically provisions a
Universal SSL certificate for that hostname if the zone is on a Cloudflare plan. The
hostname must be orange-clouded (proxied) through Cloudflare; non-proxied (grey-cloud)
records cannot receive a Worker-issued certificate. Certificate issuance takes up to
15 minutes for new hostnames; renewal is automatic and opaque to the operator.

For advanced scenarios — custom SANs, client-facing SAN sharing across Workers, wildcard
certs, or Bring-Your-Own-Certificate (BYOC) — you must use the
`cloudflare_certificate_pack` resource or the Keyless SSL / Custom Hostname APIs.

---

## Section 1 — Basic Custom Domain Attachment via Terraform

```hcl
# terraform/workers_domain.tf

# The Worker script must exist first
resource "cloudflare_worker_script" "api" {
  account_id = var.cloudflare_account_id
  name       = "api-worker"
  content    = file("${path.module}/../../dist/worker.js")
}

# Attach the custom domain — Cloudflare provisions TLS automatically
resource "cloudflare_worker_domain" "api" {
  account_id = var.cloudflare_account_id
  hostname   = "api.${var.zone_name}"
  service    = cloudflare_worker_script.api.name
  zone_id    = var.cloudflare_zone_id

  # The hostname must already be an orange-clouded DNS record;
  # Terraform does not create the DNS record implicitly.
  depends_on = [cloudflare_record.api_cname]
}

# Orange-clouded CNAME that triggers automatic certificate provisioning
resource "cloudflare_record" "api_cname" {
  zone_id = var.cloudflare_zone_id
  name    = "api"
  type    = "CNAME"
  content = "${var.cloudflare_account_id}.workers.dev"
  proxied = true   # MUST be true; grey-cloud blocks certificate issuance
  ttl     = 1      # 1 = "automatic" when proxied
}
```

---

## Section 2 — Certificate Pack for Wildcard and Multi-SAN Coverage

Universal SSL covers a zone apex and one wildcard level (`*.example.com`). Workers on
subdomains deeper than one level (e.g. `v2.api.example.com`) need an Advanced Certificate
or a wildcard pack.

```hcl
# terraform/cert_pack.tf

resource "cloudflare_certificate_pack" "api_wildcard" {
  zone_id               = var.cloudflare_zone_id
  type                  = "advanced"
  validation_method     = "http"
  validity_days         = 90
  certificate_authority = "lets_encrypt"
  cloudflare_branding   = false

  hosts = [
    "example.com",
    "*.api.example.com",   # covers v2.api.example.com, v3.api.example.com, etc.
    "api.example.com",
  ]

  lifecycle {
    # Prevent destroy-recreate on certificate renewal; Cloudflare rotates in-place.
    prevent_destroy = true
  }
}
```

> Note: `type = "advanced"` requires a Business or Enterprise zone plan.
> `type = "universal"` is free but limited to the zone apex + single wildcard.

---

## Section 3 — Bring-Your-Own-Certificate (Custom Hostname / SSL for SaaS)

When your Worker serves traffic for customer-owned domains via SSL for SaaS (Custom
Hostnames), each customer domain needs its own certificate provisioning flow.

```hcl
# terraform/custom_hostname.tf

resource "cloudflare_custom_hostname" "tenant" {
  for_each = var.tenant_domains   # map of { "acme" = "acme.example-customer.com" }

  zone_id  = var.cloudflare_zone_id
  hostname = each.value

  ssl {
    method = "http"   # or "txt" for DNS-01 validation
    type   = "dv"
    settings {
      http2         = "on"
      tls13         = "on"
      min_tls_version = "1.2"
      ciphers       = ["ECDHE-RSA-AES128-GCM-SHA256", "AES128-SHA"]
    }
  }

  custom_metadata = {
    tenant_id = each.key
  }
}

output "custom_hostname_ownership_verification" {
  value = {
    for k, ch in cloudflare_custom_hostname.tenant :
    k => ch.ownership_verification
  }
  sensitive = false
}
```

After `terraform apply`, read `ownership_verification` and create the required TXT or HTTP
record on the customer's domain to complete DV validation.

---

## Section 4 — Monitoring Certificate Status in TypeScript

Poll certificate status from a Worker cron trigger to catch stalled issuance early.

```typescript
// worker/src/cert-monitor.ts
interface CertPackStatus {
  id: string;
  hosts: string[];
  status: "initializing" | "pending_validation" | "active" | "expired";
  expires_on: string;
}

export async function checkCertificates(env: Env): Promise<void> {
  const url = `https://api.cloudflare.com/client/v4/zones/${env.CF_ZONE_ID}/ssl/certificate_packs`;

  const resp = await fetch(url, {
    headers: {
      Authorization: `Bearer ${env.CF_API_TOKEN}`,
      "Content-Type": "application/json",
    },
  });

  if (!resp.ok) throw new Error(`CF API error ${resp.status}`);

  const { result } = (await resp.json()) as { result: CertPackStatus[] };
  const now = Date.now();

  for (const pack of result) {
    const expiresMs = new Date(pack.expires_on).getTime();
    const daysUntilExpiry = (expiresMs - now) / 86_400_000;

    if (pack.status !== "active") {
      console.error(`[CERT] Pack ${pack.id} is in status '${pack.status}' for hosts: ${pack.hosts.join(", ")}`);
      await env.ALERT_QUEUE.send({ type: "cert_not_active", packId: pack.id, status: pack.status });
    } else if (daysUntilExpiry < 14) {
      console.warn(`[CERT] Pack ${pack.id} expires in ${daysUntilExpiry.toFixed(1)} days`);
      await env.ALERT_QUEUE.send({ type: "cert_expiry_warning", packId: pack.id, daysLeft: daysUntilExpiry });
    }
  }
}

export default {
  async scheduled(_event: ScheduledEvent, env: Env, ctx: ExecutionContext): Promise<void> {
    ctx.waitUntil(checkCertificates(env));
  },
};
```

---

## Section 5 — Terraform Data Source for Certificate Expiry Assertions

Use a null_resource + local-exec to fail the Terraform plan if any cert is within 7 days
of expiry, as a CI gate.

```hcl
# terraform/cert_check.tf

data "http" "cf_cert_packs" {
  url = "https://api.cloudflare.com/client/v4/zones/${var.cloudflare_zone_id}/ssl/certificate_packs"
  request_headers = {
    Authorization = "Bearer ${var.cloudflare_api_token}"
  }
}

locals {
  cert_packs = jsondecode(data.http.cf_cert_packs.response_body).result
  expiring_soon = [
    for p in local.cert_packs :
    p if p.status != "active" || timecmp(p.expires_on, timeadd(timestamp(), "168h")) < 0
  ]
}

resource "null_resource" "cert_expiry_gate" {
  count = length(local.expiring_soon) > 0 ? 1 : 0

  provisioner "local-exec" {
    command = "echo 'ERROR: Certificate expiring or not active: ${jsonencode(local.expiring_soon)}' && exit 1"
  }
}
```

---

## Section 6 — Pulumi Equivalent

```typescript
// infra/index.ts (Pulumi TypeScript)
import * as cloudflare from "@pulumi/cloudflare";

const apiRecord = new cloudflare.Record("api-cname", {
  zoneId: zoneId,
  name: "api",
  type: "CNAME",
  content: `${accountId}.workers.dev`,
  proxied: true,
});

const workerDomain = new cloudflare.WorkerDomain("api-domain", {
  accountId: accountId,
  hostname: pulumi.interpolate`api.${zoneName}`,
  service: apiWorker.name,
  zoneId: zoneId,
}, { dependsOn: [apiRecord] });

// Advanced cert pack for wildcard coverage
const certPack = new cloudflare.CertificatePack("api-wildcard-cert", {
  zoneId: zoneId,
  type: "advanced",
  validationMethod: "http",
  validityDays: 90,
  certificateAuthority: "lets_encrypt",
  cloudflareBranding: false,
  hosts: [zoneName, pulumi.interpolate`*.api.${zoneName}`, pulumi.interpolate`api.${zoneName}`],
});

export const certPackId = certPack.id;
```

---

## Anti-patterns

- **Grey-cloud CNAME for a Worker domain** — a non-proxied record will never receive
  a TLS certificate from Cloudflare. Always set `proxied = true`.
- **Creating the `cloudflare_worker_domain` before the DNS record exists** — the resource
  creates successfully but certificate issuance silently fails until the DNS record
  appears. Use `depends_on`.
- **Manually ordering certificate renewal** — Cloudflare auto-renews; manually triggering
  a new `cloudflare_certificate_pack` resource before expiry creates a duplicate and may
  cause a brief validation period.
- **Assuming `pending_validation` resolves immediately** — DV validation via HTTP-01 can
  take up to 15 minutes; via TXT up to 24 hours if DNS TTL is high.

---

## Gotchas

- `cloudflare_worker_domain` does not expose a `status` attribute in Terraform state.
  Use the API or dashboard to confirm certificate issuance after apply.
- Certificate packs with `type = "universal"` are zone-wide; you cannot delete the
  Universal SSL pack while the zone is active — Terraform will error if you try.
- Custom Hostnames (SSL for SaaS) require the **zone** to be on a Business or Enterprise
  plan, regardless of the customer's plan.
- Wildcard certificates provisioned by Cloudflare cover only `*.example.com`, not
  deeper wildcards like `*.api.example.com` — use `advanced` type for the latter.
- Certificates are provisioned per zone, not per Worker. Moving a Worker to a different
  zone requires re-provisioning; the old zone retains its cert.

---

## Verification

```bash
# Check certificate status via API
curl -s -H "Authorization: Bearer $CF_API_TOKEN" \
  "https://api.cloudflare.com/client/v4/zones/$ZONE_ID/ssl/certificate_packs" \
  | jq '.result[] | {id, status, hosts, expires_on}'

# Check TLS from command line
echo | openssl s_client -connect api.example.com:443 -servername api.example.com 2>/dev/null \
  | openssl x509 -noout -dates -subject

# Terraform output to show worker_domain
terraform output -json | jq '.custom_hostname_ownership_verification'

# Validate proxied status
dig api.example.com +short   # should return Cloudflare anycast IPs, not origin
```

---

## Related

- `terraform-cloudflare-workers-custom-domain-routing.md`
- `cloudflare-mtls-client-certificates-terraform.md`
- `cloudflare-pages-custom-headers-security-automation.md`
- `ssl-tls-certificate-management.md`
- `lets-encrypt-auto-renewal.md`

---

## Sources

- Cloudflare Docs — Custom Domains for Workers: https://developers.cloudflare.com/workers/configuration/routing/custom-domains/
- Cloudflare Docs — Certificate Packs: https://developers.cloudflare.com/ssl/edge-certificates/advanced-certificate-manager/
- Cloudflare Docs — SSL for SaaS (Custom Hostnames): https://developers.cloudflare.com/cloudflare-for-platforms/cloudflare-for-saas/security/certificate-management/
- Terraform cloudflare_certificate_pack: https://registry.terraform.io/providers/cloudflare/cloudflare/latest/docs/resources/certificate_pack
- Terraform cloudflare_worker_domain: https://registry.terraform.io/providers/cloudflare/cloudflare/latest/docs/resources/worker_domain
