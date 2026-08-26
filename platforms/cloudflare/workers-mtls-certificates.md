# workers-mtls-certificates

**Issue:** Using mTLS client certificates in Workers to authenticate outbound requests
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Some APIs (payment processors, internal services) require mutual TLS (mTLS) where the client presents a certificate. Workers support mTLS via the `MTLS_CERTIFICATE` binding, which attaches a managed client certificate to outbound `fetch` calls.

## Pattern / Solution

**Step 1 — Upload the certificate to Cloudflare:**
```bash
# Upload client cert + private key (PEM format)
curl -X POST "https://api.cloudflare.com/client/v4/accounts/$ACCOUNT_ID/mtls_certificates" \
  -H "Authorization: Bearer $CF_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "my-client-cert",
    "certificates": "<PEM_CERT>",
    "private_key": "<PEM_KEY>"
  }'
# Returns: { "id": "cert-uuid-here", ... }
```

**Step 2 — Bind in `wrangler.toml`:**
```toml
[[mtls_certificates]]
binding = "MY_CERT"
certificate_id = "cert-uuid-here"
```

**Step 3 — Use in Worker:**
```typescript
export interface Env {
  MY_CERT: Fetcher; // type is Fetcher when used via fetch binding
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    // Attach the cert to an outbound request using the cf.mtlsClientAuth option
    const response = await fetch('https://secure-api.example.com/endpoint', {
      method: 'POST',
      body: JSON.stringify({ data: 'value' }),
      headers: { 'Content-Type': 'application/json' },
      // @ts-ignore — cf options are not fully typed yet
      cf: {
        mtlsClientAuth: {
          certBinding: 'MY_CERT',
        },
      },
    });

    return new Response(await response.text(), { status: response.status });
  },
};
```

**Alternative — using the binding as a Fetcher:**
```typescript
// Some versions bind mTLS as a Fetcher; call it directly
const response = await env.MY_CERT.fetch('https://secure-api.example.com/endpoint', {
  method: 'GET',
});
```

## Gotchas
- The private key is stored encrypted by Cloudflare; it is never returned after upload.
- Certificate rotation: upload a new cert, get its `certificate_id`, update `wrangler.toml`, and redeploy.
- mTLS bindings only work with **outbound** requests from the Worker — you cannot enforce mTLS on inbound requests this way (use Cloudflare Access for that).
- The cert must be in PEM format; DER/P12 formats must be converted first (`openssl pkcs12 -in cert.p12 -out cert.pem -nodes`).
- mTLS is a paid feature; it is not available on the free plan.
- If the upstream rejects the cert, the fetch will throw a network error, not return a 4xx — wrap in try/catch.

## Related
- `workers-fetch-api-patterns.md`
- `cloudflare-access-jwt-validation.md`
- `workers-best-practices.md`
