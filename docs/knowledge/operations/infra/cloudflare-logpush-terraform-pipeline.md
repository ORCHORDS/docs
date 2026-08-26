# Cloudflare Logpush Terraform Pipeline Configuration

Date: 2026-08-23
Author: example.com
Status: production

---

## Symptom / Use-case

You need HTTP request logs, firewall events, and Workers trace data shipped continuously to a SIEM or data lake. Logpush jobs configured through the dashboard are invisible to your IaC pipeline, duplicated across zones, and accidentally disabled. You want Logpush pipelines declared as Terraform resources with per-environment field selection.

---

## Context

Cloudflare Logpush delivers structured logs asynchronously (latency ~1–2 min) to supported destinations: R2, S3, Azure Blob Storage, Google Cloud Storage, Datadog, Splunk, New Relic, Elastic, Sumo Logic, and HTTP endpoints. Each Logpush job is tied to a dataset (e.g. `http_requests`, `firewall_events`, `workers_trace_events`) and a destination. Jobs are managed per-zone or per-account. Terraform's `cloudflare_logpush_job` resource provisions jobs; `cloudflare_logpush_ownership_challenge` validates ownership of R2 and S3 destinations.

Log volume is large — HTTP request logs include every edge request. Select only fields required for your use-case to reduce egress and storage costs.

---

## R2 Destination — HTTP Request Logs

```hcl
# terraform/logpush.tf

variable "account_id" { type = string }
variable "zone_id"    { type = string }

# R2 bucket for log storage (managed separately or imported)
data "cloudflare_r2_bucket" "logs" {
  account_id = var.account_id
  name       = "cf-logs-production"
}

resource "cloudflare_logpush_job" "http_requests_r2" {
  account_id           = var.account_id
  zone_id              = var.zone_id
  name                 = "http-requests-r2-production"
  dataset              = "http_requests"
  enabled              = true
  frequency            = "high"  # "high" = ~1 min batches, "low" = ~5 min

  destination_conf = "r2://${data.cloudflare_r2_bucket.logs.name}/http-requests/{DATE}?account-id=${var.account_id}&access-key-id=${var.r2_access_key_id}&secret-access-key=${var.r2_secret_access_key}"

  logpull_options = join("&", [
    "fields=${join(",", [
      "ClientIP",
      "ClientRequestHost",
      "ClientRequestMethod",
      "ClientRequestURI",
      "EdgeResponseStatus",
      "EdgeStartTimestamp",
      "RayID",
      "WAFAction",
      "WAFRuleID",
      "FirewallMatchesActions",
      "OriginResponseStatus",
      "CacheCacheStatus",
      "WorkerStatus",
    ])}",
    "timestamps=rfc3339",
    "CVE-2021-44228=true",  # Log4Shell obfuscation protection
  ])
}
```

---

## Datadog Destination — Firewall Events

```hcl
variable "datadog_api_key" {
  type      = string
  sensitive = true
}

resource "cloudflare_logpush_job" "firewall_events_datadog" {
  account_id = var.account_id
  zone_id    = var.zone_id
  name       = "firewall-events-datadog"
  dataset    = "firewall_events"
  enabled    = true
  frequency  = "high"

  destination_conf = "datadog://?header_DD-API-KEY=${var.datadog_api_key}&ddsource=cloudflare&service=cf-waf&ddtags=env:production"

  logpull_options = "fields=Action,ClientIP,ClientRequestHost,ClientRequestMethod,ClientRequestURI,EdgeResponseStatus,Datetime,RayID,RuleID,Source,UserAgent&timestamps=rfc3339"
}
```

---

## Workers Trace Events — HTTP Endpoint

Ship Workers trace spans to a self-hosted OTEL collector or a managed observability backend:

```hcl
resource "cloudflare_logpush_job" "workers_trace_http" {
  account_id = var.account_id
  name       = "workers-trace-events-otel"
  dataset    = "workers_trace_events"
  enabled    = true
  frequency  = "high"

  # No zone_id — workers_trace_events is account-scoped
  destination_conf = "https://otel-collector.internal.example.com/v1/logs?header_Authorization=Bearer+${var.otel_bearer_token}"

  logpull_options = join("&", [
    "fields=Event,EventTimestampMs,Outcome,ScriptName,DiagnosticsChannelEvents",
    "timestamps=rfc3339",
  ])
}
```

---

## Account-Scoped Audit Logs Job

```hcl
resource "cloudflare_logpush_job" "audit_logs_s3" {
  account_id = var.account_id
  name       = "audit-logs-s3"
  dataset    = "audit_logs"
  enabled    = true
  frequency  = "low"

  destination_conf = "s3://my-siem-bucket/cloudflare-audit/{DATE}?region=us-east-1&sse=AES256"

  logpull_options = "fields=ActionResult,ActionType,ActorEmail,ActorID,ActorType,ID,Interface,Metadata,NewValue,OldValue,OwnerID,ResourceID,ResourceType,When&timestamps=rfc3339"
}
```

---

## Workers TypeScript — Log Enrichment Before Forwarding

Pipe Logpush data through a Worker for enrichment before delivery to a downstream SIEM:

```typescript
// src/log-router.ts
export interface Env {
  LOG_SINK_URL: string;
  HMAC_SECRET: string;
}

interface CloudflareLogLine {
  RayID: string;
  ClientIP: string;
  EdgeResponseStatus: number;
  WorkerStatus?: string;

}

export default {
  async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    if (request.method !== "POST") return new Response("Method Not Allowed", { status: 405 });

    const body = await request.text();
    const lines: CloudflareLogLine[] = body
      .split("\n")
      .filter(Boolean)
      .map((l) => JSON.parse(l));

    const enriched = lines.map((line) => ({
      ...line,
      environment: "production",
      ingestedAt: new Date().toISOString(),
    }));

    ctx.waitUntil(
      fetch(env.LOG_SINK_URL, {
        method: "POST",
        headers: { "Content-Type": "application/x-ndjson" },
        body: enriched.map((l) => JSON.stringify(l)).join("\n"),
      })
    );

    return new Response("OK");
  },
};
```

---

## Anti-patterns

- **Pushing all fields for all datasets**: HTTP request logs with all fields enabled can reach 1 KB/request; at 10 M req/day that is 10 GB/day before compression. Select only what analysts actually query.
- **Using `frequency = "low"` for security events**: firewall events on low frequency have a 5-minute lag — use `high` for anything feeding a real-time SIEM.
- **Storing R2 access keys in Terraform state unencrypted**: use Terraform Cloud/Enterprise with encrypted state, or pass keys via environment variables (`TF_VAR_r2_secret_access_key`) never in `.tfvars` committed to git.
- **One job per zone manually**: for multi-zone accounts, use `for_each` over a zone list to create identical jobs programmatically.
- **Ignoring the `enabled` field**: a job disabled in the dashboard after Terraform creates it will be re-enabled on next apply unless `enabled = false` is set explicitly.

---

## Gotchas

- The `account_id` + `zone_id` combination determines dataset availability: `http_requests` requires `zone_id`; `audit_logs` and `workers_trace_events` require only `account_id` (do not set `zone_id`).
- Destination URL secrets (API keys, access keys) appear in Terraform state as plaintext. Use a secrets backend or `ignore_changes` with out-of-band secret rotation.
- Logpush does not guarantee exactly-once delivery. Downstream consumers must be idempotent — deduplicate on `RayID`.
- Datadog's Logpush destination requires the `ddsource=cloudflare` tag to activate the built-in Cloudflare integration pipeline in Datadog.
- `CVE-2021-44228=true` in `logpull_options` sanitizes Log4Shell-style patterns in logged URIs before they reach your SIEM — always include this.
- Changing `destination_conf` forces a resource replacement (destroy + create), which causes a gap in log delivery.

---

## Verification

```bash
# List all Logpush jobs for a zone
curl -s "https://api.cloudflare.com/client/v4/zones/$CF_ZONE_ID/logpush/jobs" \
  -H "Authorization: Bearer $CF_API_TOKEN" | jq '.result[] | {id, name, dataset, enabled, destination_conf}'

# Check job health (last successful push timestamp)
curl -s "https://api.cloudflare.com/client/v4/zones/$CF_ZONE_ID/logpush/jobs/$JOB_ID" \
  -H "Authorization: Bearer $CF_API_TOKEN" | jq '.result | {last_complete, last_error}'

# Verify R2 bucket is receiving files
aws s3 ls s3://cf-logs-production/http-requests/ --recursive | tail -5
```

---

## Related

- `otel-grafana-cloud-observability-pipeline.md`
- `cloudflare-network-analytics-ddos-forensics.md`
- `workers-opentelemetry-tail-workers.md`
- `cloudflare-r2-backup-restore-strategy.md`
- `terraform-state-management-remote-backend.md`

---

## Sources

- Cloudflare Logpush Overview: https://developers.cloudflare.com/logs/about/
- Terraform cloudflare_logpush_job: https://registry.terraform.io/providers/cloudflare/cloudflare/latest/docs/resources/logpush_job
- Logpush Datasets & Fields: https://developers.cloudflare.com/logs/reference/log-fields/
- Logpush Destinations: https://developers.cloudflare.com/logs/get-started/enable-destinations/
- Workers Trace Events: https://developers.cloudflare.com/workers/observability/logpush/
