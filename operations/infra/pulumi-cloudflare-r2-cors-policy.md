# Pulumi Cloudflare R2 Bucket CORS Policy

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

Your frontend uploads files directly to R2 from the browser using presigned URLs, but preflight (`OPTIONS`) requests fail with a CORS error. Alternatively, you want to serve assets from an R2 bucket on a custom domain and allow cross-origin fetches from your SPA — without routing traffic through a Worker for every request.

## Context

Cloudflare R2 supports S3-compatible CORS configuration at the bucket level. CORS rules are a list of `CORSRule` objects specifying allowed origins, methods, headers, and caching duration for preflight responses. In Pulumi, CORS rules are managed via the `cloudflare.R2BucketCors` resource (Pulumi Cloudflare provider ≥ 5.4). This is separate from the `cloudflare.R2Bucket` resource — the bucket must exist before CORS can be applied. The R2 CORS implementation follows the S3 specification closely: wildcard `*` in `allowedOrigins` allows any origin, while restricting to specific origins enforces tight cross-origin policy.

---

## Provider and Project Setup

```typescript
// package.json (relevant deps)
// "@pulumi/cloudflare": "^5.4.0"
// "@pulumi/pulumi": "^3.x"

import * as cloudflare from "@pulumi/cloudflare";
import * as pulumi from "@pulumi/pulumi";

const config = new pulumi.Config();
const accountId = config.requireSecret("cloudflareAccountId");
```

## Create the R2 Bucket

```typescript
// bucket.ts
const uploadBucket = new cloudflare.R2Bucket("upload-bucket", {
  accountId: accountId,
  name: "app-user-uploads",
  location: "WEUR",  // Western Europe; omit for auto-placement
});

export const bucketName = uploadBucket.name;
```

## Permissive CORS for Development

```typescript
// cors-dev.ts
// Allow all origins — useful for local dev and staging only
const devCors = new cloudflare.R2BucketCors("upload-bucket-cors-dev", {
  accountId: accountId,
  bucketName: uploadBucket.name,
  rules: [
    {
      allowedOrigins: ["*"],
      allowedMethods: ["GET", "PUT", "POST", "DELETE", "HEAD"],
      allowedHeaders: ["*"],
      exposeHeaders: ["ETag", "Content-Length"],
      maxAgeSeconds: 3600,
    },
  ],
});
```

## Strict CORS for Production

```typescript
// cors-prod.ts
const allowedFrontendOrigins = [
  "https://app.example.com",
  "https://www.example.com",
  "https://example.com",
];

const prodCors = new cloudflare.R2BucketCors("upload-bucket-cors-prod", {
  accountId: accountId,
  bucketName: uploadBucket.name,
  rules: [
    // Rule 1: presigned upload from browser — PUT/POST with Content-Type
    {
      allowedOrigins: allowedFrontendOrigins,
      allowedMethods: ["PUT", "POST"],
      allowedHeaders: [
        "Content-Type",
        "Content-Length",
        "Content-MD5",
        "x-amz-content-sha256",
        "x-amz-date",
        "Authorization",
      ],
      exposeHeaders: ["ETag"],
      maxAgeSeconds: 3600,
    },
    // Rule 2: read access for public assets
    {
      allowedOrigins: allowedFrontendOrigins,
      allowedMethods: ["GET", "HEAD"],
      allowedHeaders: ["Range", "If-None-Match", "If-Modified-Since"],
      exposeHeaders: [
        "ETag",
        "Content-Length",
        "Content-Range",
        "Last-Modified",
      ],
      maxAgeSeconds: 86400,  // 24 h preflight cache
    },
  ],
});
```

## Environment-aware CORS with Pulumi Stack Config

```typescript
// index.ts
import * as pulumi from "@pulumi/pulumi";
import * as cloudflare from "@pulumi/cloudflare";

const stack = pulumi.getStack();  // "dev", "staging", "prod"
const config = new pulumi.Config();
const accountId = config.requireSecret("cloudflareAccountId");

const isProd = stack === "prod";

const bucket = new cloudflare.R2Bucket("assets", {
  accountId: accountId,
  name: `company-assets-${stack}`,
});

// Origins differ per environment
const origins: string[] = isProd
  ? ["https://app.company.com", "https://company.com"]
  : [`https://${stack}.preview.company.com`, "http://localhost:3000"];

const corsMethods: string[] = isProd
  ? ["GET", "HEAD", "PUT"]
  : ["GET", "HEAD", "PUT", "POST", "DELETE"];

const cors = new cloudflare.R2BucketCors(`assets-cors-${stack}`, {
  accountId: accountId,
  bucketName: bucket.name,
  rules: [
    {
      allowedOrigins: origins,
      allowedMethods: corsMethods,
      allowedHeaders: ["*"],
      exposeHeaders: ["ETag", "Content-Length"],
      maxAgeSeconds: isProd ? 86400 : 60,
    },
  ],
});

export const corsRules = cors.rules;
```

## Verifying Preflight Requests in a Worker

```typescript
// worker.ts — wrapper Worker that adds CORS headers if R2 CORS is not sufficient
export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const origin = request.headers.get("Origin") ?? "";
    const allowed = ["https://app.example.com", "https://example.com"];

    if (request.method === "OPTIONS") {
      if (allowed.includes(origin)) {
        return new Response(null, {
          status: 204,
          headers: {
            "Access-Control-Allow-Origin": origin,
            "Access-Control-Allow-Methods": "GET, PUT, HEAD",
            "Access-Control-Allow-Headers": "Content-Type, Authorization",
            "Access-Control-Max-Age": "86400",
            Vary: "Origin",
          },
        });
      }
      return new Response("Forbidden", { status: 403 });
    }

    // Pass through to R2 (or handle via binding)
    const response = await env.BUCKET.get(new URL(request.url).pathname.slice(1));
    if (!response) return new Response("Not Found", { status: 404 });

    const headers = new Headers();
    response.writeHttpMetadata(headers);
    if (allowed.includes(origin)) {
      headers.set("Access-Control-Allow-Origin", origin);
      headers.set("Vary", "Origin");
    }
    return new Response(response.body, { headers });
  },
} satisfies ExportedHandler<Env>;
```

---

## Anti-patterns

- **Using `allowedOrigins: ["*"]` in production**: Any site can read or upload to your bucket. Always restrict to your known origins in production.
- **Omitting `Vary: Origin` in downstream caches**: If a CDN caches a CORS response without `Vary: Origin`, users from non-allowed origins receive a cached response with the wrong (or missing) `Access-Control-Allow-Origin` header.
- **Setting `maxAgeSeconds` to 0**: Every cross-origin request triggers a preflight, adding latency. Set at least 3600 (1 h) for stable APIs.
- **Applying CORS only via a Worker without setting bucket-level CORS**: Direct R2 presigned upload URLs bypass the Worker — if the bucket has no CORS policy, the browser's preflight to the `*.r2.cloudflarestorage.com` endpoint will fail.
- **Using `allowedHeaders: ["*"]` in production**: Overly broad header allowlists can leak authorization tokens from unexpected request headers.

## Gotchas

- `cloudflare.R2BucketCors` replaces the entire CORS configuration on every update — it is not additive. Manage all rules in a single resource block.
- R2 CORS rules apply only to requests that include an `Origin` header. Same-origin requests (no `Origin`) are not subject to CORS and bypass these rules entirely.
- The S3 wildcard `*` in `allowedHeaders` is valid, but `*` in `exposeHeaders` is not — list each header explicitly.
- CORS rules on R2 only apply to the public bucket endpoint. Worker bindings (`env.BUCKET.get()`) bypass CORS entirely and are not affected.
- Presigned URL requests must include the `Origin` header in the preflight; the signature covers only the upload request, not the preflight itself.

## Verification

```bash
# Preflight OPTIONS request against R2 public endpoint
curl -sI -X OPTIONS \
  "https://pub-<hash>.r2.dev/test.txt" \
  -H "Origin: https://app.example.com" \
  -H "Access-Control-Request-Method: GET" \
  | grep -i "access-control"
# Expect: Access-Control-Allow-Origin: https://app.example.com

# Pulumi stack output
pulumi stack output corsRules --show-secrets

# Check bucket CORS via S3-compatible API (using rclone or aws-cli pointed at R2)
aws s3api get-bucket-cors --bucket app-user-uploads \
  --endpoint-url "https://<account-id>.r2.cloudflarestorage.com"
```

## Related

- `cloudflare-r2-presigned-urls-workers.md`
- `terraform-cloudflare-r2-cors-lifecycle.md`
- `pulumi-cloudflare-r2-lifecycle-policy-automation.md`
- `cloudflare-r2-backup-restore-strategy.md`

## Sources

- https://www.pulumi.com/registry/packages/cloudflare/api-docs/r2bucketcors/
- https://developers.cloudflare.com/r2/buckets/cors/
- https://developers.cloudflare.com/r2/api/s3/presigned-urls/
- https://fetch.spec.whatwg.org/#http-cors-protocol
