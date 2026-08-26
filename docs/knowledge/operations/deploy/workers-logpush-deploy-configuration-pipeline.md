# Workers Logpush Deploy Configuration Pipeline

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

Your Cloudflare Workers produce observability data (request logs, errors, CPU time,
`console.log` output via Tail Workers) that needs to be shipped to a SIEM or data warehouse.
The Logpush configuration is currently managed manually in the dashboard and silently
diverges from what is documented. The goal is to manage Logpush jobs as code alongside
Worker deploys so that a new environment gets the full observability stack automatically.

---

## Context

Cloudflare Logpush streams logs from a dataset (e.g. `workers-trace-events`,
`http_requests`, `firewall_events`) to a destination (R2, S3, BigQuery, Datadog, Splunk,
etc.) on a configurable interval. Each Logpush job has:

- A **dataset** — the source namespace.
- A **destination** — a URL with credentials embedded or referenced.
- A **filter** — optional JSON filter expression.
- A **field set** — which fields to include.
- An **output format** — `ndjson` (default) or `csv`.
- An **ownership challenge** — a one-time proof that you control the destination bucket.

Workers-specific datasets:

| Dataset | Content |
|---|---|
| `workers-trace-events` | Per-request invocation traces with CPU/wall time |
| `workers-tail-events` | `console.log` and exception output via Tail Workers |
| `ai-gateway-log-events` | AI Gateway request/response logs |

---

## Terraform-Managed Logpush Jobs

```hcl
# terraform/logpush.tf

resource "cloudflare_logpush_ownership_challenge" "workers_traces" {
  account_id       = var.cloudflare_account_id
  destination_conf = "r2://${var.r2_bucket_name}/workers-traces?account-id=${var.cloudflare_account_id}&access-key-id=${var.r2_access_key_id}&secret-access-key=${var.r2_secret_access_key}"
}

# After running `terraform apply` for the challenge, retrieve the ownership token:
# curl https://<bucket>.r2.dev/workers-traces/<challenge-filename>
# Then set var.logpush_ownership_token and apply again.

resource "cloudflare_logpush_job" "workers_traces" {
  account_id          = var.cloudflare_account_id
  name                = "workers-traces-${var.environment}"
  enabled             = true
  dataset             = "workers-trace-events"
  destination_conf    = "r2://${var.r2_bucket_name}/workers-traces?account-id=${var.cloudflare_account_id}&access-key-id=${var.r2_access_key_id}&secret-access-key=${var.r2_secret_access_key}"
  ownership_challenge = var.logpush_ownership_token

  # Only ship errors and slow requests to reduce volume
  filter = jsonencode({
    where = {
      or = [
        { key = "Outcome", operator = "!eq", value = "ok" },
        { key = "WallTimeUs", operator = "gt", value = 50000 }
      ]
    }
  })

  logpull_options = "fields=ScriptName,Outcome,CPUTimeUs,WallTimeUs,FetchStartTimestampMs,Exceptions&timestamps=rfc3339"
}

resource "cloudflare_logpush_job" "workers_console" {
  account_id          = var.cloudflare_account_id
  name                = "workers-console-${var.environment}"
  enabled             = true
  dataset             = "workers-tail-events"
  destination_conf    = "r2://${var.r2_bucket_name}/workers-console?account-id=${var.cloudflare_account_id}&access-key-id=${var.r2_access_key_id}&secret-access-key=${var.r2_secret_access_key}"
  ownership_challenge = var.logpush_ownership_token_console
  logpull_options     = "fields=Event,EventTimestampMs,ScriptName,Exceptions,Logs&timestamps=rfc3339"
}
```

---

## Automated Ownership Challenge Resolution

The ownership challenge is the main friction point in automating Logpush setup. The
following script resolves it end-to-end using R2 as the destination.

```typescript
// scripts/logpush-ownership.ts
// Usage: CLOUDFLARE_API_TOKEN=... CLOUDFLARE_ACCOUNT_ID=... npx ts-node scripts/logpush-ownership.ts

const ACCOUNT_ID = process.env.CLOUDFLARE_ACCOUNT_ID!;
const TOKEN = process.env.CLOUDFLARE_API_TOKEN!;
const R2_ACCOUNT_ID = process.env.CLOUDFLARE_ACCOUNT_ID!;
const R2_ACCESS_KEY = process.env.R2_ACCESS_KEY_ID!;
const R2_SECRET_KEY = process.env.R2_SECRET_ACCESS_KEY!;
const BUCKET = process.env.R2_BUCKET_NAME!;
const PREFIX = process.env.LOG_PREFIX ?? "workers-traces";

const DEST = `r2://${BUCKET}/${PREFIX}?account-id=${R2_ACCOUNT_ID}&access-key-id=${R2_ACCESS_KEY}&secret-access-key=${R2_SECRET_KEY}`;

interface ChallengeResult {
  result: {
    filename: string;
    message: string;
    valid: boolean;
  };
  success: boolean;
  errors: Array<{ message: string }>;
}

async function requestChallenge(): Promise<string> {
  const res = await fetch(
    `https://api.cloudflare.com/client/v4/accounts/${ACCOUNT_ID}/logpush/ownership`,
    {
      method: "POST",
      headers: {
        Authorization: `Bearer ${TOKEN}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ destination_conf: DEST }),
    }
  );

  const data = (await res.json()) as ChallengeResult;
  if (!data.success) throw new Error(`Challenge request failed: ${JSON.stringify(data.errors)}`);
  console.log("Challenge file written to:", data.result.filename);
  return data.result.filename;
}

async function fetchChallengeToken(filename: string): Promise<string> {
  // The challenge token is written to the R2 bucket; retrieve it via S3-compatible API
  const url = `https://${R2_ACCOUNT_ID}.r2.cloudflarestorage.com/${BUCKET}/${filename}`;
  const res = await fetch(url, {
    headers: {
      // Use AWS Sig v4; simplified here — use @aws-sdk/client-s3 in production
      Authorization: `AWS ${R2_ACCESS_KEY}:placeholder`,
    },
  });
  if (!res.ok) throw new Error(`Failed to fetch challenge token: ${res.status}`);
  return res.text();
}

async function validateOwnership(token: string): Promise<void> {
  const res = await fetch(
    `https://api.cloudflare.com/client/v4/accounts/${ACCOUNT_ID}/logpush/ownership/validate`,
    {
      method: "POST",
      headers: {
        Authorization: `Bearer ${TOKEN}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ destination_conf: DEST, ownership_challenge: token }),
    }
  );

  const data = (await res.json()) as { result: { valid: boolean }; success: boolean };
  if (!data.success || !data.result.valid) {
    throw new Error("Ownership validation failed");
  }
  console.log("Ownership validated. Token:", token);
  console.log("Set TF_VAR_logpush_ownership_token in CI secrets.");
}

requestChallenge()
  .then(fetchChallengeToken)
  .then(validateOwnership)
  .catch((e) => { console.error(e.message); process.exit(1); });
```

---

## CI/CD Pipeline: Logpush as Part of Worker Deploy

```yaml
# .github/workflows/deploy-with-logpush.yml
name: Deploy Worker + Logpush

on:
  push:
    branches: [main]

jobs:
  deploy-worker:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: npm ci
      - name: Deploy Worker
        run: npx wrangler deploy
        env:
          CLOUDFLARE_API_TOKEN: ${{ secrets.CF_API_TOKEN }}

  sync-logpush:
    needs: deploy-worker
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Setup Terraform
        uses: hashicorp/setup-terraform@v3

      - name: Terraform Init
        run: terraform init
        working-directory: terraform

      - name: Terraform Apply (Logpush jobs only)
        run: |
          terraform apply -auto-approve \
            -target=cloudflare_logpush_job.workers_traces \
            -target=cloudflare_logpush_job.workers_console
        working-directory: terraform
        env:
          TF_VAR_cloudflare_account_id: ${{ secrets.CF_ACCOUNT_ID }}
          TF_VAR_environment: production
          TF_VAR_r2_bucket_name: ${{ secrets.R2_BUCKET_NAME }}
          TF_VAR_r2_access_key_id: ${{ secrets.R2_ACCESS_KEY_ID }}
          TF_VAR_r2_secret_access_key: ${{ secrets.R2_SECRET_KEY }}
          TF_VAR_logpush_ownership_token: ${{ secrets.LOGPUSH_OWNERSHIP_TOKEN }}
          TF_VAR_logpush_ownership_token_console: ${{ secrets.LOGPUSH_OWNERSHIP_TOKEN_CONSOLE }}
          CLOUDFLARE_API_TOKEN: ${{ secrets.CF_API_TOKEN }}

  verify-logpush:
    needs: sync-logpush
    runs-on: ubuntu-latest
    steps:
      - name: Confirm Logpush jobs are enabled
        run: |
          JOBS=$(curl -s \
            "https://api.cloudflare.com/client/v4/accounts/$CF_ACCOUNT_ID/logpush/jobs" \
            -H "Authorization: Bearer $CF_API_TOKEN")
          ENABLED_COUNT=$(echo "$JOBS" | jq '[.result[] | select(.enabled == true and (.dataset | startswith("workers")))] | length')
          echo "Enabled Workers Logpush jobs: $ENABLED_COUNT"
          [ "$ENABLED_COUNT" -ge 1 ] || { echo "No enabled Workers Logpush jobs found"; exit 1; }
        env:
          CF_ACCOUNT_ID: ${{ secrets.CF_ACCOUNT_ID }}
          CF_API_TOKEN: ${{ secrets.CF_API_TOKEN }}
```

---

## Querying Logs from R2 with Workers Analytics

Once logs land in R2, expose them via a Worker for internal querying.

```typescript
// src/log-query-worker.ts
interface Env {
  LOG_BUCKET: R2Bucket;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);
    const date = url.searchParams.get("date") ?? new Date().toISOString().slice(0, 10);
    const prefix = `workers-traces/${date}`;

    const list = await env.LOG_BUCKET.list({ prefix, limit: 20 });

    const files = await Promise.all(
      list.objects.map(async (obj) => {
        const file = await env.LOG_BUCKET.get(obj.key);
        if (!file) return null;
        const text = await file.text();
        return text
          .split("\n")
          .filter(Boolean)
          .map((line) => {
            try { return JSON.parse(line); }
            catch { return null; }
          })
          .filter(Boolean);
      })
    );

    const events = files.flat().filter(Boolean);
    return Response.json({ date, count: events.length, events: events.slice(0, 100) });
  },
};
```

---

## Anti-patterns

- **Storing R2 credentials inside the Logpush destination URL in plaintext Git** — The
  destination URL contains secret credentials. Store it in CI secrets, not in source code.
- **Enabling all fields with no filter** — Workers trace events include full request/response
  bodies when payload logging is on. Unfiltered high-volume Workers can generate hundreds
  of GBs/day in R2, incurring significant storage costs.
- **Skipping the ownership challenge step in automation** — The challenge is a one-time
  operation per destination, not per job. Automate it once and store the token as a CI secret;
  do not re-run it on every deploy.
- **Not pinning the logpull_options field list** — Cloudflare adds new fields to datasets
  over time. Omitting an explicit field list means downstream schemas can break silently.
- **Creating Logpush jobs at the zone level for a Workers dataset** — Workers trace events
  are account-level, not zone-level. Zone-level jobs for this dataset silently deliver no data.

---

## Gotchas

- Logpush has a delivery lag of up to 5 minutes. Do not use it for real-time alerting;
  use Tail Workers (`wrangler tail`) for sub-second observability.
- R2 Logpush destinations use AWS Signature Version 4 under the hood. The `account-id`
  query parameter in the destination URL is required and must match the account that owns
  the bucket.
- Disabling a Logpush job (not deleting it) preserves its ownership token. Re-enabling is
  instant and does not require another ownership challenge.
- The `filter` field in the Logpush job config uses Cloudflare's filter expression syntax,
  not a generic JSON Query Language. Field names are case-sensitive and dataset-specific.
- Logpush to Datadog/Splunk uses a push URL with an embedded API key. Rotating the key
  requires updating the job's `destination_conf`, which triggers a new ownership challenge
  if the destination URL structure changes.

---

## Verification

```bash
# List all Logpush jobs (account-level)
curl -s "https://api.cloudflare.com/client/v4/accounts/$CF_ACCOUNT_ID/logpush/jobs" \
  -H "Authorization: Bearer $CF_API_TOKEN" | jq '.result[] | {name, dataset, enabled, last_complete}'

# Force a manual Logpush run (useful in testing)
curl -s -X POST \
  "https://api.cloudflare.com/client/v4/accounts/$CF_ACCOUNT_ID/logpush/jobs/$JOB_ID/enable" \
  -H "Authorization: Bearer $CF_API_TOKEN"

# Verify logs are landing in R2
aws s3 ls s3://$R2_BUCKET_NAME/workers-traces/ \
  --endpoint-url "https://$CF_ACCOUNT_ID.r2.cloudflarestorage.com" \
  --no-sign-request
```

---

## Related

- `wrangler-tail-logs-deployment-verification.md`
- `workers-tail-worker-deploy-validation.md`
- `cloudflare-analytics-engine-deploy-observability.md`
- `r2-bucket-cors-configuration-deploy.md`
- `deploy-notification-webhooks-slack-teams-workers.md`

---

## Sources

- https://developers.cloudflare.com/logs/get-started/
- https://developers.cloudflare.com/logs/reference/log-fields/account/workers-trace-events/
- https://registry.terraform.io/providers/cloudflare/cloudflare/latest/docs/resources/logpush_job
- https://developers.cloudflare.com/logs/logpush/ownership-challenge/
