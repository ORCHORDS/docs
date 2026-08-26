# Terraform: Cloudflare DNSSEC Zone Management

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case
You need to enable DNSSEC for Cloudflare-managed zones via Terraform, capture the DS record details, and automate DS record submission to the domain registrar so the full DNSSEC chain of trust is established without manual dashboard steps.

## Context
DNSSEC adds cryptographic signatures to DNS responses, preventing cache-poisoning and spoofing attacks. For zones hosted on Cloudflare's nameservers, Cloudflare acts as the signing authority — you enable DNSSEC on the zone and submit a Delegation Signer (DS) record to your registrar. Terraform's `cloudflare_zone_dnssec` resource manages the Cloudflare side; DS submission to the registrar depends on the registrar's API (shown here for Cloudflare Registrar). Full activation can take 24-48 hours to propagate.

## Enabling DNSSEC on the Zone

```hcl
terraform {
  required_providers {
    cloudflare = {
      source  = "cloudflare/cloudflare"
      version = "~> 4.40"
    }
  }
}

variable "cf_api_token" {
  type      = string
  sensitive = true
}
variable "zone_id" { type = string }
variable "zone_name" { type = string }  # e.g. "example.com"

provider "cloudflare" {
  api_token = <redacted-secret>
}

# The zone must already exist (imported or created separately).
# Enabling DNSSEC changes the zone's NS TTL to 86400; plan for that.
resource "cloudflare_zone_dnssec" "main" {
  zone_id = var.zone_id

  # modified_on is computed; no additional required arguments.
  # Terraform will call the DNSSEC activation API on create.
}

# Capture the DS record fields as outputs for registrar submission
output "dnssec_status" {
  value = cloudflare_zone_dnssec.main.status
}

output "ds_record" {
  description = "Full DS record string to submit to the registrar"
  value       = cloudflare_zone_dnssec.main.ds
}

output "dnssec_key_type" {
  value = cloudflare_zone_dnssec.main.key_type
}

output "dnssec_digest_type" {
  value = cloudflare_zone_dnssec.main.digest_type
}

output "dnssec_digest" {
  value = cloudflare_zone_dnssec.main.digest
}

output "dnssec_key_tag" {
  value = cloudflare_zone_dnssec.main.key_tag
}

output "dnssec_algorithm" {
  value = cloudflare_zone_dnssec.main.algorithm
}

output "dnssec_flags" {
  value = cloudflare_zone_dnssec.main.flags
}
```

## Submitting the DS Record to Cloudflare Registrar

```hcl
# If the domain is registered through Cloudflare Registrar, submit the DS record
# via the Cloudflare API. There is no native Terraform resource for this yet;
# use a null_resource with a local-exec provisioner or the `cloudflare_record` workaround.

# Option A: null_resource with curl (works in CI with CF token available)
resource "null_resource" "submit_ds_record" {
  depends_on = [cloudflare_zone_dnssec.main]

  triggers = {
    ds = cloudflare_zone_dnssec.main.ds
  }

  provisioner "local-exec" {
    command = <<-EOF
      curl -s -X POST \
        "https://api.cloudflare.com/client/v4/zones/${var.zone_id}/dnssec" \
        -H "Authorization: Bearer ${var.cf_api_token}" \
        -H "Content-Type: application/json" \
        -d '{"status":"active"}' | jq '{status: .result.status}'
    EOF
    # Note: For non-Cloudflare registrars, use their API here instead.
    # The DS values to submit are in the cloudflare_zone_dnssec outputs above.
  }
}
```

## Managing Multiple Zones with DNSSEC

```hcl
# zones.tf — centrally manage DNSSEC across a portfolio of zones
variable "zones" {
  type = map(string)
  default = {
    "example-com"    = "zone-id-1"
    "example-net"    = "zone-id-2"
    "example-org"    = "zone-id-3"
  }
}

resource "cloudflare_zone_dnssec" "all" {
  for_each = var.zones
  zone_id  = each.value
}

output "ds_records" {
  description = "DS records for all zones — submit to respective registrars"
  value = {
    for k, v in cloudflare_zone_dnssec.all :
    k => {
      ds       = v.ds
      status   = v.status
      key_tag  = v.key_tag
      digest   = v.digest
    }
  }
}
```

## Verifying the Chain of Trust with a Workers Cron

```typescript
// A periodic Worker that checks DNSSEC validation health for monitored zones
export interface Env {
  ZONE_NAMES: string;   // comma-separated list stored as var: "example.com,example.net"
  ALERT_WEBHOOK: string; // Slack or PagerDuty webhook URL
}

interface DnssecStatus {
  zone: string;
  valid: boolean;
  ad: boolean;   // authenticated data bit set
}

async function checkDnssec(zone: string): Promise<DnssecStatus> {
  // Query Cloudflare's DNS over HTTPS — AD bit confirms DNSSEC validation
  const res = await fetch(
    `https://cloudflare-dns.com/dns-query?name=${zone}&type=SOA&do=1`,
    { headers: { Accept: "application/dns-json" } }
  );
  const data = await res.json<{ AD: boolean; Status: number }>();
  return {
    zone,
    valid: data.Status === 0,
    ad: data.AD === true,
  };
}

export default {
  async scheduled(_event: ScheduledEvent, env: Env, ctx: ExecutionContext): Promise<void> {
    const zones = env.ZONE_NAMES.split(",").map((z) => z.trim());
    const results = await Promise.all(zones.map(checkDnssec));

    const failures = results.filter((r) => !r.ad);
    if (failures.length === 0) {
      console.log("DNSSEC validation OK for all zones");
      return;
    }

    // Alert on broken chain of trust
    const message = failures
      .map((f) => `${f.zone}: AD=${f.ad}, valid=${f.valid}`)
      .join("\n");

    ctx.waitUntil(
      fetch(env.ALERT_WEBHOOK, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          text: `DNSSEC alert — chain of trust broken:\n${message}`,
        }),
      })
    );
  },
};
```

## Anti-patterns
- Enabling DNSSEC before nameservers have fully propagated — the zone must be authoritative at Cloudflare's nameservers before DNSSEC signatures are valid; check `dig NS example.com` first
- Deleting `cloudflare_zone_dnssec` without removing the DS record from the registrar — this breaks DNS resolution for the zone entirely (SERVFAIL) until the DS record TTL expires
- Running `terraform destroy` on DNSSEC in production without a pre-planned DS record removal at the registrar
- Using zone-level API tokens without `Zone: DNSSEC: Edit` permission — the DNSSEC activation call requires an explicit permission not included in general `Zone: Edit`
- Expecting immediate activation — DNSSEC status cycles through `pending` → `active`; poll `cloudflare_zone_dnssec.status` with a data source rather than hardcoding a `time_sleep`

## Gotchas
- `cloudflare_zone_dnssec` has no `status` attribute you can read back in the same plan — use a `data "cloudflare_zone_dnssec"` data source in a subsequent plan to confirm `status == "active"`
- Key rollover is automatic on Cloudflare's side; DS records submitted to the registrar do not need to be re-submitted after a key rollover — Cloudflare uses CDNSKEY and CDS records to signal rollovers to registrars that support RFC 8078
- Disabling DNSSEC (`terraform destroy` or setting status to inactive via API) while DS records exist at the registrar will cause SERVFAIL responses until DS records propagate out
- The `ds` output is a pre-formatted string like `2371 13 2 <digest>` — copy it verbatim to the registrar; breaking it into fields and re-composing can introduce whitespace errors
- Free Cloudflare zones support DNSSEC; no plan upgrade is required

## Verification
```bash
# Check DNSSEC activation status via API
curl -s "https://api.cloudflare.com/client/v4/zones/$CF_ZONE_ID/dnssec" \
  -H "Authorization: Bearer $CF_API_TOKEN" | jq '{status: .result.status, ds: .result.ds}'

# Verify DS record at the registrar has propagated to the root
dig DS example.com @a.root-servers.net +short

# Verify DNSSEC chain of trust end-to-end (AD bit must be set)
dig SOA example.com @1.1.1.1 +dnssec | grep -E "^;; flags|RRSIG"

# Check with DNSSEC Analyzer
# https://dnssec-analyzer.verisignlabs.com/example.com

# Terraform output to get DS record for registrar submission
terraform output ds_record
```

## Related
- `terraform-cloudflare-dns-zone-record-management.md` — DNS zone and record management with Terraform
- `cloudflare-dns-api.md` — programmatic DNS record operations via the Cloudflare API
- `cloudflare-workers-cron-triggers-terraform.md` — provisioning Workers cron triggers for monitoring
- `ssl-tls-certificate-management.md` — TLS certificate management alongside DNS security

## Sources
- https://developers.cloudflare.com/dns/dnssec/
- https://registry.terraform.io/providers/cloudflare/cloudflare/latest/docs/resources/zone_dnssec
- https://developers.cloudflare.com/dns/dnssec/multi-signer-dnssec/
- https://www.cloudflare.com/dns/dnssec/how-dnssec-works/
- https://datatracker.ietf.org/doc/html/rfc8078
