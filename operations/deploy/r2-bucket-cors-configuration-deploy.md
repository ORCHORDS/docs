# R2 Bucket CORS Configuration Deploy Automation

- Date: 2026-08-23
- Author: example.com
- Status: production

## Symptom / Use-case

After deploying a new R2 bucket, browser clients (React apps, presigned-URL upload flows) get blocked by CORS errors because the bucket CORS policy was not provisioned as part of the deploy. Engineers apply CORS rules manually via the dashboard, creating drift between staging and production bucket configurations.

## Context

R2 bucket CORS rules are applied via the **R2 Bucket CORS API** and are separate from the bucket creation step. Like KV seeds, they must be provisioned *before* client traffic reaches the bucket. This article covers Wrangler-managed CORS configuration, a Terraform-based alternative, and a CI pipeline that gates browser smoke tests on confirmed CORS availability.

---

## 1. CORS Policy Manifest

Version-control a JSON CORS manifest per environment:

```json
// config/r2-cors.json
[
  {
    "AllowedOrigins": [
      "https://myapp.com",
      "https://staging.myapp.com"
    ],
    "AllowedMethods": ["GET", "PUT", "DELETE", "HEAD"],
    "AllowedHeaders": ["Content-Type", "Content-MD5", "Cache-Control"],
    "ExposeHeaders":  ["ETag"],
    "MaxAgeSeconds":  3600
  },
  {
    "AllowedOrigins": ["http://localhost:*"],
    "AllowedMethods": ["GET", "PUT"],
    "AllowedHeaders": ["*"],
    "MaxAgeSeconds":  60
  }
]
```

---

## 2. Apply CORS via Wrangler (CLI Approach)

```bash
# scripts/r2-set-cors.sh
set -euo pipefail

BUCKET="${R2_BUCKET_NAME}"
CORS_FILE="config/r2-cors.json"

wrangler r2 bucket cors set "$BUCKET" --rules "$(cat "$CORS_FILE")"

echo "CORS applied to bucket: $BUCKET"

# Verify immediately
wrangler r2 bucket cors get "$BUCKET"
```

---

## 3. Apply CORS via the REST API (Script Approach)

For more control and CI integration without Wrangler:

```typescript
// scripts/r2-apply-cors.ts
import { readFileSync } from "node:fs";
import { resolve }      from "node:path";

const ACCOUNT_ID  = process.env.CF_ACCOUNT_ID!;
const API_TOKEN   = process.env.CF_API_TOKEN!;
const BUCKET_NAME = process.env.R2_BUCKET_NAME!;

interface CORSRule {
  AllowedOrigins:  string[];
  AllowedMethods:  string[];
  AllowedHeaders?: string[];
  ExposeHeaders?:  string[];
  MaxAgeSeconds?:  number;
}

async function applyCORS(rules: CORSRule[]): Promise<void> {
  const url = `https://api.cloudflare.com/client/v4/accounts/${ACCOUNT_ID}/r2/buckets/${BUCKET_NAME}/cors`;

  const res = await fetch(url, {
    method:  "PUT",
    headers: {
      Authorization:  `Bearer ${API_TOKEN}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ rules }),
  });

  if (!res.ok) {
    const err = await res.text();
    throw new Error(`Failed to set CORS: ${res.status} ${err}`);
  }

  const data = await res.json() as any;
  if (!data.success) throw new Error(JSON.stringify(data.errors));
  console.log(`CORS applied to ${BUCKET_NAME}: ${rules.length} rule(s)`);
}

async function verifyCORS(): Promise<CORSRule[]> {
  const res  = await fetch(
    `https://api.cloudflare.com/client/v4/accounts/${ACCOUNT_ID}/r2/buckets/${BUCKET_NAME}/cors`,
    { headers: { Authorization: `Bearer ${API_TOKEN}` } }
  );
  const data = await res.json() as any;
  return data.result?.rules ?? [];
}

async function main() {
  const rules: CORSRule[] = JSON.parse(
    readFileSync(resolve("config/r2-cors.json"), "utf8")
  );

  await applyCORS(rules);

  const live = await verifyCORS();
  console.log("Live CORS rules:", JSON.stringify(live, null, 2));
}

main().catch(err => { console.error(err); process.exit(1); });
```

---

## 4. Terraform Alternative

```hcl
# terraform/r2_cors.tf
resource "cloudflare_r2_bucket_cors" "app_bucket_cors" {
  account_id  = var.cf_account_id
  bucket_name = cloudflare_r2_bucket.app_bucket.name

  rules = [
    {
      allowed = {
        origins = ["https://myapp.com", "https://staging.myapp.com"]
        methods = ["GET", "PUT", "DELETE", "HEAD"]
        headers = ["Content-Type", "Content-MD5", "Cache-Control"]
      }
      expose_headers   = ["ETag"]
      max_age_seconds  = 3600
    },
    {
      allowed = {
        origins = ["http://localhost:*"]
        methods = ["GET", "PUT"]
        headers = ["*"]
      }
      max_age_seconds = 60
    }
  ]
}
```

---

## 5. Presigned URL Worker — CORS-Aware Upload Flow

Workers that issue presigned URLs for direct browser-to-R2 uploads must ensure the signed URL's `Origin` constraint aligns with the CORS `AllowedOrigins`:

```typescript
// workers/presign/src/index.ts
export interface Env {
  MY_BUCKET: R2Bucket;
  ALLOWED_ORIGINS: string;  // comma-separated, from wrangler.toml [vars]
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const origin  = request.headers.get("Origin") ?? "";
    const allowed = env.ALLOWED_ORIGINS.split(",").map(o => o.trim());

    const corsHeaders = allowed.includes(origin)
      ? {
          "Access-Control-Allow-Origin":  origin,
          "Access-Control-Allow-Methods": "GET, PUT",
          "Access-Control-Allow-Headers": "Content-Type",
          "Access-Control-Max-Age":       "3600",
          Vary:                           "Origin",
        }
      : {};

    if (request.method === "OPTIONS") {
      return new Response(null, { status: 204, headers: corsHeaders });
    }

    if (request.method !== "POST") {
      return new Response("Method Not Allowed", { status: 405 });
    }

    const { key } = await request.json() as { key: string };
    if (!key || key.includes("..")) {
      return new Response("Invalid key", { status: 400 });
    }

    // Create a presigned upload URL valid for 15 minutes
    const presigned = await env.MY_BUCKET.createMultipartUpload(key);

    return new Response(
      JSON.stringify({ uploadId: presigned.uploadId, key }),
      { headers: { ...corsHeaders, "Content-Type": "application/json" } }
    );
  },
} satisfies ExportedHandler<Env>;
```

---

## 6. CORS Smoke Test in CI

```bash
# scripts/test-cors.sh — run after CORS is applied and Worker is deployed
set -euo pipefail

ORIGIN="https://myapp.com"
BUCKET_ENDPOINT="https://pub-${R2_PUBLIC_BUCKET_ID}.r2.dev"

# Preflight request
RESPONSE=$(curl -si \
  -X OPTIONS \
  -H "Origin: $ORIGIN" \
  -H "Access-Control-Request-Method: PUT" \
  -H "Access-Control-Request-Headers: Content-Type" \
  "$BUCKET_ENDPOINT/test-cors-probe")

echo "$RESPONSE" | grep -i "access-control-allow-origin" \
  | grep -q "$ORIGIN" || { echo "CORS preflight failed"; exit 1; }

echo "CORS smoke test passed for origin: $ORIGIN"
```

---

## Anti-patterns

- **Applying CORS after deploying the Worker that issues presigned URLs** — clients will receive CORS errors for the first minutes of operation; apply CORS as the first step in your bucket provisioning job.
- **Using `AllowedOrigins: ["*"]` in production** — wildcard origins bypass the cross-origin isolation benefit; always enumerate origins explicitly.
- **Duplicating CORS logic in the Worker and on the bucket** — R2's native CORS handles direct-to-bucket browser uploads; Worker CORS handles Worker-served responses. Maintain them separately but in sync.
- **Not setting `ExposeHeaders: ["ETag"]`** — clients that verify upload integrity via ETag cannot access it without this explicit exposure.

## Gotchas

- **Public vs private bucket CORS scope** — CORS rules on private buckets only apply to presigned-URL requests and Worker-proxied requests. Direct API access ignores CORS because the browser never makes direct API requests without a Worker in front.
- **Wildcard in `AllowedHeaders`** — `"*"` is valid in `AllowedHeaders` but not in `AllowedOrigins` for credentialed requests (e.g., uploads with `withCredentials: true`). If clients use cookies, enumerate headers explicitly.
- **Rule order** — R2 applies the first matching rule. Place the most specific origins before wildcard or localhost rules.
- **PUT vs POST for multipart** — browser multipart upload parts use `PUT` per-part; ensure `AllowedMethods` includes both `PUT` and `POST` if you use the multipart upload API directly.
- **`MaxAgeSeconds` and CDN edge caching** — if your bucket is behind a CDN, the preflight response may be cached at the CDN level; invalidate cache after CORS rule changes.

## Verification

```bash
# Show live CORS rules
wrangler r2 bucket cors get "$R2_BUCKET_NAME"

# Preflight with curl
curl -si \
  -X OPTIONS \
  -H "Origin: https://myapp.com" \
  -H "Access-Control-Request-Method: PUT" \
  "https://pub-${R2_PUBLIC_BUCKET_ID}.r2.dev/example" \
  | grep -i "access-control"

# Run full CORS smoke test script
R2_BUCKET_NAME="$R2_BUCKET_NAME" \
R2_PUBLIC_BUCKET_ID="$R2_PUBLIC_BUCKET_ID" \
bash scripts/test-cors.sh
```

## Related

- `zero-downtime-r2-bucket-migration.md`
- `workers-assets-binding-deploy-patterns.md`
- `deploy-gate-e2e-tests-playwright-pages.md`
- `secrets-management-wrangler-vault.md`

## Sources

- R2 CORS documentation: https://developers.cloudflare.com/r2/buckets/cors/
- R2 CORS API: https://developers.cloudflare.com/api/resources/r2/subresources/buckets/subresources/cors/
- Wrangler r2 cors commands: https://developers.cloudflare.com/workers/wrangler/commands/#r2-bucket-cors
- R2 presigned URLs: https://developers.cloudflare.com/r2/api/s3/presigned-urls/
