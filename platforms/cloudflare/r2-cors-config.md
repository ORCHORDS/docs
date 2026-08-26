# r2-cors-config

**Issue:** Configure browser CORS correctly for R2 public URLs, custom domains, presigned S3 requests, and Worker-proxied objects without confusing the four access paths.
**Date:** 2026-08-20
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** verified against Cloudflare documentation updated 2026-07-31

## First choose the access path

R2 CORS behavior depends on where the browser sends the request:

1. **Public Development URL (`pub-<hash>.r2.dev`) or R2 custom domain:** R2 evaluates the bucket CORS policy and returns `Access-Control-*` headers for valid cross-origin requests.
2. **Presigned S3 API URL (`<ACCOUNT_ID>.r2.cloudflarestorage.com`):** the URL authorizes one S3 operation, but the bucket still needs a matching CORS policy for browser use.
3. **Worker route using an R2 binding (`env.BUCKET.get()`, `put()`, and related methods):** the browser talks to the Worker, not directly to R2. The Worker must validate `Origin`, answer preflight, and set response CORS headers itself.
4. **Server-side R2 binding call:** CORS is irrelevant because no browser is enforcing it.

Do not copy a CORS fix from one path to another without identifying which endpoint the browser actually calls.

## Current Wrangler and REST payload shape

Cloudflare's current Wrangler and REST API use the Cloudflare R2 API model: a top-level `rules` array with lower-case `allowed.origins`, `allowed.methods`, and `allowed.headers` fields.

`cors.json`:

```json
{
  "rules": [
    {
      "id": "app-browser-access",
      "allowed": {
        "origins": [
          "https://app.example.com",
          "http://localhost:5173"
        ],
        "methods": ["GET", "PUT", "HEAD"],
        "headers": ["Content-Type", "Content-MD5", "x-amz-checksum-sha256"]
      },
      "exposeHeaders": ["ETag", "Content-Length"],
      "maxAgeSeconds": 3600
    }
  ]
}
```

Apply and verify it:

```bash
npx wrangler r2 bucket cors set my-bucket --file cors.json
npx wrangler r2 bucket cors list my-bucket
```

The equivalent REST request sends the same JSON object:

```bash
curl --request PUT \
  "https://api.cloudflare.com/client/v4/accounts/$ACCOUNT_ID/r2/buckets/my-bucket/cors" \
  --header "Authorization: Bearer $CF_API_TOKEN" \
  --header "Content-Type: application/json" \
  --data @cors.json
```

Use a scoped API token and never commit it.

## Presigned browser upload: the correct boundary

An R2 Workers binding does **not** turn `createMultipartUpload()` into a browser URL. That method returns a server-side `R2MultipartUpload` object used by Worker code. For a direct browser PUT, generate an S3-compatible presigned URL on a trusted server or Worker with the AWS SDK and keep the R2 access-key secret server-side.

```ts
import { PutObjectCommand, S3Client } from '@aws-sdk/client-s3'
import { getSignedUrl } from '@aws-sdk/s3-request-presigner'

const s3 = new S3Client({
  region: 'auto',
  endpoint: `https://${accountId}.r2.cloudflarestorage.com`,
  credentials: {
    accessKeyId: env.R2_ACCESS_KEY_ID,
    secretAccessKey: env.R2_SECRET_ACCESS_KEY,
  },
})

const uploadUrl = await getSignedUrl(
  s3,
  new PutObjectCommand({
    Bucket: 'my-bucket',
    Key: 'uploads/file.png',
    ContentType: 'image/png',
  }),
  { expiresIn: 3600 },
)
```

The browser uses the returned URL without adding an `Authorization` header. Headers included in the signature must match exactly:

```ts
const response = await fetch(uploadUrl, {
  method: 'PUT',
  headers: { 'Content-Type': 'image/png' },
  body: file,
})

if (!response.ok) throw new Error(`R2 upload failed: ${response.status}`)
```

Presigned URLs are bearer credentials. Keep expiries short, scope each URL to one object and operation, and do not log the query string. R2 presigned URLs work on the S3 API domain, not on an R2 custom domain. R2 currently supports presigned `GET`, `HEAD`, `PUT`, and `DELETE`; HTML-form `POST` presigning is not supported.

## Worker-fronted R2: own the CORS policy in code

When a Worker reads through an R2 binding, validate the exact origin and return `Vary: Origin` whenever the response can differ by origin.

```ts
const ALLOWED_ORIGINS = new Set([
  'https://app.example.com',
  'http://localhost:5173',
])

function allowedOrigin(request: Request): string | null {
  const origin = request.headers.get('Origin')
  return origin && ALLOWED_ORIGINS.has(origin) ? origin : null
}

function withCors(headers: Headers, origin: string): Headers {
  headers.set('Access-Control-Allow-Origin', origin)
  headers.append('Vary', 'Origin')
  return headers
}

export default {
  async fetch(request: Request, env: { BUCKET: R2Bucket }): Promise<Response> {
    const origin = allowedOrigin(request)

    if (request.method === 'OPTIONS') {
      if (!origin) {
        return new Response(null, {
          status: 403,
          headers: { Vary: 'Origin' },
        })
      }

      return new Response(null, {
        status: 204,
        headers: withCors(new Headers({
          'Access-Control-Allow-Methods': 'GET,PUT,HEAD,OPTIONS',
          'Access-Control-Allow-Headers': 'Content-Type,Authorization',
          'Access-Control-Max-Age': '3600',
        }), origin),
      })
    }

    const object = await env.BUCKET.get(new URL(request.url).pathname.slice(1))
    if (!object) return new Response('Not Found', { status: 404 })

    const headers = new Headers()
    object.writeHttpMetadata(headers)
    headers.set('ETag', object.httpEtag)
    if (origin) withCors(headers, origin)

    return new Response(object.body, { headers })
  },
}
```

CORS is not authentication. A disallowed browser cannot read the response through JavaScript, but non-browser clients can still send the request. Keep authorization checks on every protected Worker route.

## Diagnose a custom-domain-only CORS failure

A useful differential is the same preflight against the `workers.dev` hostname and the custom hostname:

```bash
curl --include --request OPTIONS \
  --header 'Origin: http://localhost:5173' \
  --header 'Access-Control-Request-Method: POST' \
  https://api.example.com/resource
```

If the Worker path succeeds on `workers.dev` but the custom hostname omits `Access-Control-Allow-Origin`:

1. Confirm the incoming request includes `Origin`; requests without it are not CORS requests and R2 intentionally emits no CORS headers.
2. Confirm the origin matches exactly as `scheme://host[:port]` with no path or trailing slash.
3. If the custom domain fronts R2 directly, purge cached assets after changing the bucket CORS policy; existing cached responses do not gain the new headers automatically.
4. If the custom domain routes to a Worker, log only the minimum diagnostic needed to confirm whether `request.headers.get('Origin')` is present. Do not log authorization values or presigned query strings.
5. Inspect **Request Header Transform Rules** and use **Cloudflare Trace**. Transform Rules can remove a request header before the request reaches the Worker or origin, and those transformed values are not visible in normal browser tooling or original-header Logpush fields.
6. Add a deployed regression probe that sends a real `OPTIONS` request with `Origin` to every production hostname and asserts the expected `Access-Control-Allow-Origin` value.

Do not claim a cache rule or transform rule is the root cause until Trace or origin-side evidence proves it.

## Gotchas

- `AllowedOrigins` values match exactly. `https://app.example.com/` is invalid because an origin has no path.
- A request without `Origin` will not receive CORS response headers.
- Include every non-safelisted request header the browser actually sends in the bucket policy or Worker preflight response.
- Add `ExposeHeaders` for response fields JavaScript must read, such as `ETag`, `Content-Length`, or `cf-cache-status`.
- An expired R2 presigned URL returns `403 ExpiredRequest` without CORS headers, so browser JavaScript cannot read its error body. Refresh before expiry or proxy through the application when the UI must inspect expiration errors.
- Use `Access-Control-Allow-Origin: *` only for deliberately public, non-credentialed reads. Echo a validated exact origin for authenticated application routes.
- Purge a custom domain's cache after changing R2 CORS policy.

## References

1. Cloudflare R2 — Configure CORS: https://developers.cloudflare.com/r2/buckets/cors/
2. Cloudflare R2 — Presigned URLs: https://developers.cloudflare.com/r2/api/s3/presigned-urls/
3. Cloudflare R2 — Upload objects: https://developers.cloudflare.com/r2/objects/upload-objects/
4. Cloudflare R2 — Workers API: https://developers.cloudflare.com/r2/get-started/workers-api/
5. Cloudflare Rules — Request Header Transform Rules: https://developers.cloudflare.com/rules/transform/request-header-modification/
6. Cloudflare Rules — Troubleshoot Transform Rules: https://developers.cloudflare.com/rules/transform/troubleshooting/
7. Cloudflare Rules — Trace a request: https://developers.cloudflare.com/rules/trace-request/

## Related

- `r2-best-practices.md`
- `r2-signed-urls.md`
- `r2-multipart-upload.md`
- `r2-custom-domains-cache-rules.md`
- `cors-pages-functions.md`
