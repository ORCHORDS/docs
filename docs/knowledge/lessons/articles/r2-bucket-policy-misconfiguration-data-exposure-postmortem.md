# R2 Bucket Policy Misconfiguration Data Exposure Postmortem

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom

A routine security scan surfaced that user-uploaded profile images and invoice PDFs were
publicly accessible without authentication for approximately 6 days. Any URL of the form
`https://<account>.r2.cloudflarestorage.com/<bucket>/<key>` returned the file without
credentials. No external party reported the exposure, but internal log analysis confirmed
~220 objects were accessed by IP addresses outside the company's egress range during the window.

## Context

The `user-assets` R2 bucket was created by a developer who copied a `wrangler.toml` snippet
from the public R2 documentation examples. That example included a `[r2_buckets]` binding with
`public = true` to demonstrate object serving via a custom domain — a setting intended for
static site asset buckets. The developer applied it to the user-content bucket without
understanding the implication: Cloudflare exposed the bucket via `r2.dev` subdomain (and the
account's default public endpoint) with no access controls. The issue was not caught in review
because the reviewer did not inspect the wrangler config diff.

---

## The Misconfiguration

```toml
# wrangler.toml — BEFORE (dangerous)
[[r2_buckets]]
binding = "USER_ASSETS"
bucket_name = "user-assets-prod"
# The line below exposes the bucket at a public r2.dev URL:
preview_bucket_name = "user-assets-dev"

# In the R2 bucket settings (set via dashboard or API):
# public_access = true   ← This was enabled during bucket creation
```

```bash
# Verify whether a bucket has public access enabled:
curl "https://api.cloudflare.com/client/v4/accounts/$CF_ACCOUNT_ID/r2/buckets/user-assets-prod" \
  -H "Authorization: Bearer $CF_API_TOKEN" | jq '.result.public_access'
# Should return null or false for private buckets
```

## Correct Access Pattern: Presigned URLs via Worker

```typescript
// src/workers/assets.ts
// Never expose R2 objects directly — always proxy or presign through a Worker
// that enforces authentication.

import { AwsClient } from 'aws4fetch'; // R2 supports S3-compatible signing

export default {
  async fetch(req: Request, env: Env): Promise<Response> {
    const session = await getSession(req, env);
    if (!session) return new Response('Unauthorized', { status: 401 });

    const url = new URL(req.url);
    const objectKey = url.pathname.slice(1); // strip leading /

    // Validate ownership — user can only access their own objects
    if (!objectKey.startsWith(`users/${session.userId}/`)) {
      return new Response('Forbidden', { status: 403 });
    }

    const object = await env.USER_ASSETS.get(objectKey);
    if (!object) return new Response('Not Found', { status: 404 });

    const headers = new Headers();
    object.writeHttpMetadata(headers);
    headers.set('Cache-Control', 'private, max-age=300');
    // Prevent downstream caches from storing user-specific content
    headers.set('Vary', 'Authorization');

    return new Response(object.body, { headers });
  },
};
```

## Generating Short-Lived Presigned URLs for Client Downloads

```typescript
// src/lib/r2-presign.ts
// Use S3-compatible presigning when the client must download directly
// (e.g. large video files where proxying through a Worker is too slow).

export async function presignR2GetUrl(
  env: Env,
  key: string,
  ttlSeconds = 300,
): Promise<string> {
  const r2 = new AwsClient({
    accessKeyId: env.R2_ACCESS_KEY_ID,
    secretAccessKey: env.R2_SECRET_ACCESS_KEY,
    service: 's3',
    region: 'auto',
  });

  const url = new URL(
    `https://${env.R2_BUCKET_NAME}.${env.CF_ACCOUNT_ID}.r2.cloudflarestorage.com/${key}`,
  );
  url.searchParams.set('X-Amz-Expires', String(ttlSeconds));

  const signed = await r2.sign(new Request(url, { method: 'GET' }), {
    aws: { signQuery: true },
  });

  return signed.url;
}
```

## Automated Policy Audit in CI

```typescript
// scripts/check-r2-policy.ts  — run in CI to catch public-access regressions
// Requires CF_API_TOKEN with R2 read permissions.

async function auditR2Buckets(): Promise<void> {
  const res = await fetch(
    `https://api.cloudflare.com/client/v4/accounts/${process.env.CF_ACCOUNT_ID}/r2/buckets`,
    { headers: { Authorization: `Bearer ${process.env.CF_API_TOKEN}` } },
  );
  const { result } = await res.json() as { result: Array<{ name: string; public_access?: boolean }> };

  const exposed = result.filter(b => b.public_access === true);
  if (exposed.length > 0) {
    console.error('PUBLIC R2 BUCKETS DETECTED:', exposed.map(b => b.name));
    process.exit(1); // Fail CI
  }
  console.log(`Audited ${result.length} buckets — all private.`);
}

auditR2Buckets();
```

## Remediation: Disable Public Access and Rotate Object Keys

```typescript
// src/scripts/remediate-exposure.ts
// 1. Disable public access via API (idempotent)
async function disablePublicAccess(env: Env): Promise<void> {
  const res = await fetch(
    `https://api.cloudflare.com/client/v4/accounts/${env.CF_ACCOUNT_ID}/r2/buckets/${env.BUCKET_NAME}`,
    {
      method: 'PATCH',
      headers: {
        Authorization: `Bearer ${env.CF_API_TOKEN}`,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ public_access: false }),
    },
  );
  if (!res.ok) throw new Error(`Failed to disable public access: ${res.status}`);
}

// 2. Re-key sensitive objects to invalidate any cached URLs
async function rekeyObjects(env: Env): Promise<void> {
  const { objects } = await env.USER_ASSETS.list();
  for (const obj of objects) {
    const data = await env.USER_ASSETS.get(obj.key);
    if (!data) continue;
    const newKey = `v2/${obj.key}`; // new path — old URLs are broken
    await env.USER_ASSETS.put(newKey, data.body, {
      httpMetadata: data.httpMetadata,
      customMetadata: data.customMetadata,
    });
    await env.USER_ASSETS.delete(obj.key);
  }
}
```

## CORS Policy Lockdown

```typescript
// R2 CORS should only allow your own domain, not wildcard origins.
// Set via API — there is no wrangler.toml equivalent.
async function setCorsPolicy(env: Env): Promise<void> {
  await fetch(
    `https://api.cloudflare.com/client/v4/accounts/${env.CF_ACCOUNT_ID}/r2/buckets/${env.BUCKET_NAME}/cors`,
    {
      method: 'PUT',
      headers: {
        Authorization: `Bearer ${env.CF_API_TOKEN}`,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        cors_rules: [
          {
            allowed_origins: ['https://app.example.com'],
            allowed_methods: ['GET'],
            max_age_seconds: 300,
          },
        ],
      }),
    },
  );
}
```

---

## Anti-Patterns

- **Copy-pasting public documentation examples into production configs.** Docs often use
  `public = true` for convenience; never apply it to user-content buckets.
- **No CI check for bucket policy settings.** Infrastructure drift goes undetected until
  a scan or incident surfaces it.
- **Storing predictable object keys.** Even "private" URLs are discoverable if keys follow
  sequential or UUID patterns. Add a random salt per object.
- **Overly broad CORS (`*` origin).** Allows cross-origin data exfiltration from any site.
- **No access log analysis.** The exposure lasted 6 days; access logs existed but were not
  monitored for anomalous IP ranges.

## Gotchas

- Cloudflare's `r2.dev` public domain is enabled at the bucket level and is separate from
  custom-domain serving. Disabling `public_access` removes the `r2.dev` URL but does not
  affect a custom domain configured via Workers Routes.
- `env.R2_BUCKET.get(key)` inside a Worker is always authenticated (uses the binding's
  service token). The exposure was on the direct public endpoint, not the Worker binding.
- Presigned URLs issued before the policy change remain valid until their TTL expires. After
  a data exposure, short TTLs (≤5 min) limit the remediation window.
- R2 does not support bucket-level IAM conditions like S3. Access control is enforced entirely
  by the Worker layer or presigned URL scoping.

## Verification

```bash
# Confirm bucket is private
curl -I "https://$CF_ACCOUNT_ID.r2.cloudflarestorage.com/user-assets-prod/test.jpg"
# Expect: 403 or connection refused, NOT 200

# Run the CI audit script
CF_ACCOUNT_ID=... CF_API_TOKEN=... npx tsx scripts/check-r2-policy.ts

# Check access logs for anomalous requests during the exposure window
wrangler r2 object list user-assets-prod --remote 2>/dev/null | head
```

## Related

- `r2-cors-preflight-misconfiguration-incident.md`
- `r2-presigned-url-expiry-misconfiguration-postmortem.md`
- `r2-presigned-url-race-condition-upload-incident.md`
- `security-review-before-not-after.md`
- `data-minimization-reduces-breach-impact.md`

## Sources

- R2 public buckets docs: https://developers.cloudflare.com/r2/buckets/public-buckets/
- R2 CORS configuration: https://developers.cloudflare.com/r2/buckets/cors/
- R2 S3 presigned URLs: https://developers.cloudflare.com/r2/api/s3/presigned-urls/
- aws4fetch: https://github.com/mhart/aws4fetch
