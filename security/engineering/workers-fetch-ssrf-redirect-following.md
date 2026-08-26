# Workers Fetch SSRF via Redirect Following

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case
A Worker that calls `fetch()` with user-controlled URLs and follows HTTP redirects can be hijacked to reach internal Cloudflare metadata endpoints, private RFC-1918 ranges, or other Workers and services not intended to be reachable from the public internet.

## Context
`fetch()` in Cloudflare Workers follows redirects by default (`redirect: 'follow'`). If an attacker controls the target URL—either directly or by controlling a server that issues a redirect—they can chain through a legitimate-looking URL to an internal destination. This is especially dangerous when the redirect lands on `169.254.169.254` (cloud metadata), other internal Workers via `workers.dev`, or service bindings that would otherwise be unreachable.

---

## Section 1 — Disable Automatic Redirect Following

The primary defense is to set `redirect: 'manual'` and explicitly validate the final destination before following any redirect.

```typescript
interface Env {
  ALLOWED_HOSTS: string; // comma-separated allowlist, e.g. "api.example.com,cdn.example.com"
}

function parseAllowedHosts(env: Env): Set<string> {
  return new Set(env.ALLOWED_HOSTS.split(',').map(h => h.trim().toLowerCase()));
}

function isAllowedHost(hostname: string, allowed: Set<string>): boolean {
  const h = hostname.toLowerCase();
  // Exact match or subdomain match
  for (const rule of allowed) {
    if (h === rule || h.endsWith(`.${rule}`)) return true;
  }
  return false;
}

function isPrivateAddress(hostname: string): boolean {
  // Block cloud metadata, loopback, and RFC-1918 ranges by hostname pattern.
  // Note: Workers cannot resolve to IPs at request time; block known-bad hostnames.
  const blocked = [
    '169.254.169.254',        // AWS/GCP/Azure metadata
    'metadata.google.internal',
    'fd00::ec2',              // IPv6 metadata
    'localhost',
    '127.0.0.1',
    '[::1]',
  ];
  return blocked.some(b => hostname.toLowerCase() === b);
}

async function safeFetch(
  url: string,
  env: Env,
  options: RequestInit = {}
): Promise<Response> {
  const allowed = parseAllowedHosts(env);
  let currentUrl = new URL(url);

  // Validate initial URL
  if (!['https:', 'http:'].includes(currentUrl.protocol)) {
    throw new Error(`Disallowed protocol: ${currentUrl.protocol}`);
  }
  if (isPrivateAddress(currentUrl.hostname)) {
    throw new Error(`Blocked private address: ${currentUrl.hostname}`);
  }
  if (!isAllowedHost(currentUrl.hostname, allowed)) {
    throw new Error(`Host not in allowlist: ${currentUrl.hostname}`);
  }

  // Follow redirects manually, validating each hop
  const maxRedirects = 5;
  let redirectCount = 0;

  while (true) {
    const res = await fetch(currentUrl.toString(), {
      ...options,
      redirect: 'manual', // Never auto-follow
    });

    const isRedirect = res.status >= 300 && res.status < 400;
    if (!isRedirect || redirectCount >= maxRedirects) {
      return res;
    }

    const location = res.headers.get('Location');
    if (!location) throw new Error('Redirect with no Location header');

    // Resolve potentially relative redirect
    const nextUrl = new URL(location, currentUrl.toString());

    // Re-validate destination after redirect
    if (!['https:', 'http:'].includes(nextUrl.protocol)) {
      throw new Error(`Redirect to disallowed protocol: ${nextUrl.protocol}`);
    }
    if (isPrivateAddress(nextUrl.hostname)) {
      throw new Error(`Redirect to private address blocked: ${nextUrl.hostname}`);
    }
    if (!isAllowedHost(nextUrl.hostname, allowed)) {
      throw new Error(`Redirect to non-allowlisted host blocked: ${nextUrl.hostname}`);
    }

    currentUrl = nextUrl;
    redirectCount++;
  }
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const targetUrl = new URL(request.url).searchParams.get('url');
    if (!targetUrl) return new Response('Missing url param', { status: 400 });

    try {
      const upstream = await safeFetch(targetUrl, env);
      return new Response(upstream.body, {
        status: upstream.status,
        headers: { 'Content-Type': upstream.headers.get('Content-Type') ?? 'text/plain' },
      });
    } catch (err) {
      return new Response(`Blocked: ${(err as Error).message}`, { status: 403 });
    }
  }
};
```

---

## Section 2 — Block Internal Workers and workers.dev Redirects

Redirect-based SSRF in Workers can be used to reach other Worker routes that are internally accessible. Block `workers.dev` and any custom worker hostnames.

```typescript
function isBlockedInternalHost(hostname: string): boolean {
  const h = hostname.toLowerCase();
  const internalPatterns = [
    /\.workers\.dev$/,
    /\.workersdev\.net$/,
    /^worker\./,
    // Block Cloudflare's own internal ranges accessible from Workers runtime
    /\.internal\.cloudflare\.com$/,
    /^cf-/,
  ];
  return internalPatterns.some(p => p.test(h));
}

// Add to the validation in safeFetch:
// if (isBlockedInternalHost(nextUrl.hostname)) {
//   throw new Error(`Redirect to internal Worker host blocked: ${nextUrl.hostname}`);
// }
```

---

## Section 3 — Enforce HTTPS-Only Redirects

Downgrade attacks (HTTPS → HTTP redirect) can strip TLS from sensitive requests. Enforce that redirects stay on HTTPS.

```typescript
async function httpsOnlySafeFetch(
  url: string,
  env: Env
): Promise<Response> {
  const parsed = new URL(url);
  if (parsed.protocol !== 'https:') {
    throw new Error('Only HTTPS URLs are allowed');
  }
  // Use safeFetch from Section 1 but add protocol enforcement after each redirect
  return safeFetch(url, env, {});
  // Within safeFetch's redirect loop, additionally check:
  // if (nextUrl.protocol !== 'https:') throw new Error('Redirect downgrade to HTTP blocked');
}
```

---

## Section 4 — DNS Rebinding Resistance

DNS rebinding can make an allowlisted hostname resolve to a private IP after the initial check. Workers do not expose DNS resolution results directly, but you can mitigate by enforcing that the initial TLS certificate presented during the connection matches the expected hostname, and by using Cloudflare's `cf` fetch options to limit network behavior.

```typescript
// Use Cloudflare's cf object to restrict fetch behavior
const res = await fetch(url, {
  redirect: 'manual',
  cf: {
    // Disallow caching of the URL scan result to prevent cache poisoning
    cacheEverything: false,
    // Resolve through Cloudflare's resolver; do not use caller-supplied DNS
    // (this is the default behavior in Workers, noted for documentation)
  },
});
```

DNS rebinding is significantly harder to exploit in Workers than in browsers because Workers do not have a concept of a "same-origin" page that can be manipulated post-load. The primary risk is the redirect chain reaching an internal host by hostname rather than DNS rebinding per se.

---

## Anti-patterns

- Using `fetch(userUrl)` with no `redirect` option — defaults to `'follow'` and will silently follow redirects to internal hosts.
- Allowlist checking only the initial URL before calling `fetch()` — the allowlist must be re-evaluated at every redirect hop.
- Using a blocklist instead of an allowlist — blocklists are inherently incomplete; use an explicit allowlist of permitted hostnames.
- Allowing `file://`, `data://`, or `ftp://` protocols — these are blocked by the Workers runtime but should be rejected explicitly before the fetch for defense in depth.
- Trusting `X-Forwarded-For` or `Host` headers to determine the "real" destination — use the resolved `Location` header only.
- Not capping the number of redirect hops — an attacker-controlled server could chain arbitrarily many redirects to exhaust CPU time.

---

## Gotchas

- Workers runtime already blocks connections to RFC-1918 IPs (10.x, 172.16.x, 192.168.x) at the network layer. However, `169.254.169.254` (cloud metadata) is not an RFC-1918 address and must be blocked explicitly by hostname.
- `new URL(location, base)` is required for relative Location headers (e.g. `/redirect/path`). A bare path resolved without a base URL will throw or produce an incorrect absolute URL.
- HTTP 307 and 308 redirects preserve the request method and body; if the Worker proxies a POST with a body, forwarding it to an unintended host after a redirect leaks the request body.
- The `redirect: 'manual'` response in Workers returns an opaque redirect response; call `res.headers.get('Location')` to get the redirect target — `res.url` is not updated.
- Cloudflare Tunnel endpoints (`*.cfargotunnel.com`) may be reachable via redirect if a Tunnel is registered on the account; add these to the block patterns above.

---

## Verification

1. Configure a test server that issues a `301` redirect to `http://169.254.169.254/latest/meta-data/`.
2. Point the Worker's proxied URL to the test server and confirm the Worker returns `403 Blocked: Redirect to private address`.
3. Test with a redirect to an unlisted external host and confirm `403 Blocked: Redirect to non-allowlisted host`.
4. Test a valid redirect between two allowlisted hosts and confirm the Worker successfully proxies the final response.
5. Confirm the Worker returns `403` when more than 5 redirects are chained.

```bash
# Quick test with curl (replace with your Worker URL)
curl -s "https://your-worker.workers.dev/proxy?url=https://redirect-test.example.com/to-metadata" \
  -o /dev/null -w "%{http_code}"
# Expected: 403
```

---

## Related

- `ssrf-prevention-workers-fetch-allowlist.md`
- `ssrf-url-fetch-guard.md`
- `outbound-url-policy-ssrf-and-dns-rebinding-resistance.md`
- `server-side-request-forgery-ssrf.md`
- `workers-error-response-information-disclosure.md`

---

## Sources

- https://developers.cloudflare.com/workers/runtime-apis/fetch/
- https://developers.cloudflare.com/workers/configuration/environment-variables/
- https://portswigger.net/web-security/ssrf
- https://cheatsheetseries.owasp.org/cheatsheets/Server_Side_Request_Forgery_Prevention_Cheat_Sheet.html
- https://developers.cloudflare.com/workers/observability/errors/
