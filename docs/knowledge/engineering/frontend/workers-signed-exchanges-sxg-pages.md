# Workers Signed Exchanges (SXG) Pages

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

Google Search's prefetch cache (and Chrome's Signed Exchange support) can prefetch your Cloudflare Pages site cross-origin while showing your URL in the address bar instead of Google's cache URL. Without SXG, Google's AMP Cache serves a cached copy under `https://www.google.com/...` — confusing for analytics, OAuth redirects, and brand trust. With SXG via Cloudflare Workers, you get instant prefetched loads from Google without the AMP URL problem.

## Context

A Signed Exchange (SXG) is a file format (`.sxg`) that cryptographically binds an HTTP response to a URL and a publisher certificate. Chrome 73+ can treat an SXG as a valid navigation to the signed URL even if it was delivered by a third-party (Google's cache). The signature is valid for 7 days. Cloudflare offers automatic SXG generation via the `sxg` flag in `wrangler.toml` for Workers, and as a Zone setting for Cloudflare-proxied domains. Cloudflare Pages does not automatically produce SXG; you need either a Worker in front of Pages or a Cloudflare Zone-level toggle.

---

## 1. Enable SXG at the Zone Level (Simplest Path)

```bash
# Requires an Enterprise or Business zone with SXG enabled.
# Via Wrangler (Cloudflare API):
wrangler pages project sxg enable --project-name=my-pages-project

# Via curl (Cloudflare API v4):
curl -X PATCH "https://api.cloudflare.com/client/v4/zones/${ZONE_ID}/settings/signed_exchanges" \
  -H "Authorization: Bearer ${CF_API_TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{"value":"on"}'
```

When the Zone toggle is on, Cloudflare automatically generates `.sxg` files for cacheable HTML responses from Pages. No code changes are needed. Confirm it is working:

```bash
curl -sI -H "Accept: application/signed-exchange;v=b3" \
  https://your-pages-project.pages.dev/ | grep content-type
# Expect: content-type: application/signed-exchange;v=b3
```

---

## 2. Workers Shim: SXG Generation for Pages Without Zone Access

```typescript
// worker/sxg-proxy.ts
// Uses the @cloudflare/sxg-rs WASM library (publish separately to R2 or bundle).
// Requires: npm install sxg-rs-cloudflare-workers
import { SxgWorker } from 'sxg-rs-cloudflare-workers';

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const sxgWorker = await SxgWorker.fromEnv({
      cert: env.SXG_CERT_PEM,       // ECC P-256 cert chain PEM
      privKey: env.SXG_PRIVATE_KEY, // PKCS8 private key PEM
      htmlHost: env.PAGES_HOST,     // e.g. my-project.pages.dev
    });

    // Only sign HTML responses accepted via SXG
    const accept = request.headers.get('Accept') ?? '';
    const wantsSXG = accept.includes('application/signed-exchange;v=b3');

    // Proxy to Pages origin
    const pagesUrl = `https://${env.PAGES_HOST}${new URL(request.url).pathname}`;
    const originResponse = await fetch(pagesUrl, {
      headers: { ...Object.fromEntries(request.headers), host: env.PAGES_HOST },
    });

    if (!wantsSXG || !originResponse.headers.get('content-type')?.includes('text/html')) {
      return originResponse;
    }

    const html = await originResponse.text();
    const signed = await sxgWorker.createSignedExchange({
      url: request.url,
      html,
      status: originResponse.status,
    });

    return new Response(signed.body, {
      status: 200,
      headers: {
        'Content-Type': 'application/signed-exchange;v=b3',
        'Cache-Control': 'public, max-age=604800', // 7-day SXG max validity
        'X-Content-Type-Options': 'nosniff',
        'Vary': 'Accept',
      },
    });
  },
} satisfies ExportedHandler<Env>;

interface Env {
  SXG_CERT_PEM: string;
  SXG_PRIVATE_KEY: string;
  PAGES_HOST: string;
}
```

---

## 3. Certificate Requirements and `/.well-known/sxg-certs` Endpoint

```typescript
// worker/sxg-cert.ts
// SXG requires a CanSignHttpExchanges OID in the TLS cert.
// DigiCert and Sectigo offer these; Let's Encrypt does not (as of 2026).
// Browsers fetch the cert via the cbor-encoded certUrl in the SXG header.

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);

    if (url.pathname.startsWith('/.well-known/sxg-certs/')) {
      const certId = url.pathname.split('/').pop()!;
      const cert = await env.SXG_CERTS.get(certId);  // KV
      if (!cert) return new Response('Not found', { status: 404 });

      return new Response(cert, {
        headers: {
          'Content-Type': 'application/cert-chain+cbor',
          'Cache-Control': 'public, max-age=86400',
        },
      });
    }

    // Fall through to SXG proxy logic…
    return new Response('Not implemented', { status: 501 });
  },
} satisfies ExportedHandler<Env>;

interface Env { SXG_CERTS: KVNamespace; }
```

---

## 4. `wrangler.toml` for SXG-Enabled Worker

```toml
# wrangler.toml
name = "sxg-proxy"
main = "src/worker/sxg-proxy.ts"
compatibility_date = "2026-01-01"

[vars]
PAGES_HOST = "my-project.pages.dev"

[[kv_namespaces]]
binding = "SXG_CERTS"
id = "xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"

[secrets]
# Store cert and key as secrets:
# wrangler secret put SXG_CERT_PEM
# wrangler secret put SXG_PRIVATE_KEY

[[routes]]
pattern = "www.example.com/*"
zone_name = "example.com"
```

---

## 5. Prefetch Link Header for Google Discover

```typescript
// Add Link header so Google can prefetch the SXG before the user taps.
// This goes in the *HTML* response (not the SXG itself), typically via a Pages header rule.

// _headers (Cloudflare Pages)
// /blog/*
//   Link: <https://www.example.com$path>; rel="alternate"; type="application/signed-exchange;v=b3"
//   Vary: Accept

// Programmatically in a Worker:
function addSXGLinkHeader(response: Response, url: URL): Response {
  const mutable = new Response(response.body, response);
  mutable.headers.append(
    'Link',
    `<${url.href}>; rel="alternate"; type="application/signed-exchange;v=b3"`
  );
  mutable.headers.set('Vary', 'Accept');
  return mutable;
}
```

---

## 6. Validation and Debugging

```bash
# Install the SXG validator CLI:
npm install -g sxg-validator

# Fetch an SXG response and validate locally:
curl -sH "Accept: application/signed-exchange;v=b3" \
  https://www.example.com/blog/post-1 -o post-1.sxg

sxg-validator validate post-1.sxg \
  --cert ./chain.pem \
  --url https://www.example.com/blog/post-1

# Chrome DevTools: navigate to chrome://web-sxg-internals for per-navigation SXG status.

# Check Google's AMP Cache SXG:
curl -sI "https://www-example-com.cdn.ampproject.org/v/s/www.example.com/" \
  -H "Accept: application/signed-exchange;v=b3" | grep content-type
```

---

## Anti-patterns

- **Signing mutable or user-personalised HTML** — SXG is cached and replayed for all users; never sign pages with auth-gated content, CSRF tokens, or session-specific data.
- **Setting `Cache-Control: no-store` on HTML** — this prevents SXG generation; Pages responses must be publicly cacheable for Cloudflare to sign them.
- **Using an RSA TLS cert for SXG** — SXG requires an ECC P-256 cert with the `CanSignHttpExchanges` OID; your normal RSA wildcard cert will be rejected.
- **Signing redirects** — SXGs can only be generated for 200 responses; redirect your short URLs to canonical before signing.

## Gotchas

- SXG validity is capped at 7 days (604 800 seconds) by the spec; signing at deploy time means you need a key rotation/re-signing strategy before 7 days or Google's cache will serve stale content.
- The cert chain must include the `CanSignHttpExchanges` OID in the EE cert's extended key usage; Cloudflare's Zone-level SXG manages this automatically via its internal CA partnership.
- Chrome requires the inner URL in the SXG to match the outer URL exactly, including scheme and port; `https://` on port 443 only.
- Firefox does not support SXG; only Chromium-based browsers process it. Server `Vary: Accept` is essential so non-Chrome clients receive regular HTML.

## Verification

```bash
# Confirm Zone-level SXG is on:
curl -s "https://api.cloudflare.com/client/v4/zones/${ZONE_ID}/settings/signed_exchanges" \
  -H "Authorization: Bearer ${CF_API_TOKEN}" | jq '.result.value'
# Expect: "on"

# Check that the SXG accept header triggers the right Content-Type:
curl -sI -H "Accept: application/signed-exchange;v=b3,*/*;q=0.1" \
  https://www.example.com/ | grep -i "content-type"
# Expect: content-type: application/signed-exchange;v=b3
```

## Related

- `early-hints-103-cloudflare-pages.md`
- `cloudflare-pages-routes-json-spa-fallback.md`
- `prefetching-strategies.md`
- `http3-quic-frontend-loading-performance.md`
- `speculation-rules-api-prerender.md`

## Sources

- https://developers.cloudflare.com/speed/optimization/other/signed-exchanges/
- https://web.dev/signed-exchanges/
- https://wicg.github.io/webpackage/draft-yasskin-http-origin-signed-responses.html
- https://github.com/google/webpackager
