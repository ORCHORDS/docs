# SSRF Prevention in Cloudflare Workers fetch() Calls — Allowlist-Based URL Validation

- **Date:** 2026-08-22
- **Author:** example.com
- **Status:** production

---

## Symptom / Use-Case

Your Worker accepts a URL from user input — a webhook endpoint, an avatar URL, an import source, an API proxy target — and calls `fetch(userUrl)`. An attacker supplies `http://169.254.169.254/latest/meta-data/` (the AWS IMDS endpoint), `http://10.0.0.1/admin`, or `http://localhost:8080/internal`. Because Workers run in Cloudflare's network, the fetch may succeed and return internal data the attacker was not supposed to reach. You need a layered defense: an allowlist that validates the URL before fetch, RFC 1918/loopback/metadata-IP blocking, redirect-chain validation, and Cloudflare WAF rules as a fallback.

---

## Context

Server-Side Request Forgery (SSRF) in Cloudflare Workers is subtly different from traditional server SSRF:

- **Workers cannot reach RFC 1918 IPs directly** through Cloudflare's network in most cases, but the exact routing depends on the account configuration, Cloudflare Tunnel attachments, and whether the Worker has access to a VPN-connected private network via Cloudflare Access.
- **DNS rebinding** can bypass IP checks made at URL-parse time. The hostname resolves to a public IP during the check but is rebinded to an internal IP when `fetch()` resolves it again.
- **Redirect chains** can route an apparently safe initial URL to an internal target after one or more 3xx responses.
- **IPv6 representation variants** can bypass naive regex checks: `::1`, `0000:0000:0000:0000:0000:0000:0000:0001`, and `[::1]` all represent loopback.

Defense in depth means: allowlist first, IP check second, disable redirect-following third, WAF fourth.

---

## Section 1 — Allowlist-Based URL Validation

The most secure pattern: define exactly which hostnames (or host+path prefixes) are permitted, and reject everything else.

```typescript
// worker/src/lib/ssrf-guard.ts

export interface AllowlistEntry {
  hostname: string;           // exact match or glob suffix
  allowedSchemes: string[];   // ["https"] almost always; never "file://"
  pathPrefix?: string;        // optional path restriction
}

// Configure per Worker — externalize to KV or wrangler.toml vars for dynamic updates
const ALLOWLIST: AllowlistEntry[] = [
  { hostname: "api.stripe.com",       allowedSchemes: ["https"] },
  { hostname: "hooks.slack.com",      allowedSchemes: ["https"] },
  { hostname: "api.github.com",       allowedSchemes: ["https"] },
  { hostname: "uploads.example.com",  allowedSchemes: ["https"], pathPrefix: "/avatars/" },
];

export class SSRFGuardError extends Error {
  constructor(
    message: string,
    public readonly url: string,
    public readonly reason: string
  ) {
    super(message);
    this.name = "SSRFGuardError";
  }
}

/**
 * Validate a URL against the allowlist.
 * Throws SSRFGuardError if the URL fails any check.
 * Returns a validated URL object on success.
 */
export function validateUrl(rawUrl: string): URL {
  let parsed: URL;
  try {
    parsed = new URL(rawUrl);
  } catch {
    throw new SSRFGuardError(
      "Invalid URL",
      rawUrl,
      "URL failed to parse"
    );
  }

  // 1. Scheme check — reject non-http(s) before anything else
  if (!["http:", "https:"].includes(parsed.protocol)) {
    throw new SSRFGuardError(
      "Disallowed URL scheme",
      rawUrl,
      `Scheme '${parsed.protocol}' is not permitted`
    );
  }

  // 2. Allowlist check
  const match = ALLOWLIST.find((entry) => {
    if (!entry.allowedSchemes.includes(parsed.protocol.replace(":", ""))) {
      return false;
    }
    if (parsed.hostname !== entry.hostname) return false;
    if (entry.pathPrefix && !parsed.pathname.startsWith(entry.pathPrefix)) {
      return false;
    }
    return true;
  });

  if (!match) {
    throw new SSRFGuardError(
      "URL not in allowlist",
      rawUrl,
      `Hostname '${parsed.hostname}' is not an allowed target`
    );
  }

  // 3. Inline IP check — catch literal IPs that slipped into hostname field
  blockPrivateIp(parsed.hostname, rawUrl);

  return parsed;
}
```

---

## Section 2 — Blocking RFC 1918, Loopback, and Metadata IPs

Even with an allowlist, validate literal IP addresses to catch misconfigurations or dynamic allowlist entries that could be set to internal IPs.

```typescript
// worker/src/lib/ssrf-guard.ts (continued)

// RFC 1918 private ranges
const PRIVATE_IPV4_RANGES = [
  /^10\.\d{1,3}\.\d{1,3}\.\d{1,3}$/,                          // 10.0.0.0/8
  /^172\.(1[6-9]|2\d|3[01])\.\d{1,3}\.\d{1,3}$/,              // 172.16.0.0/12
  /^192\.168\.\d{1,3}\.\d{1,3}$/,                              // 192.168.0.0/16
  /^127\.\d{1,3}\.\d{1,3}\.\d{1,3}$/,                         // 127.0.0.0/8 loopback
  /^169\.254\.\d{1,3}\.\d{1,3}$/,                              // 169.254.0.0/16 link-local
  /^0\.0\.0\.0$/,                                               // unspecified
  /^100\.(6[4-9]|[7-9]\d|1[01]\d|12[0-7])\.\d{1,3}\.\d{1,3}$/, // 100.64.0.0/10 CGNAT
];

// Cloud metadata service endpoints
const METADATA_HOSTNAMES = new Set([
  "169.254.169.254",    // AWS/GCP/Azure IMDS
  "metadata.google.internal",
  "169.254.170.2",      // ECS credential endpoint
]);

// IPv6 ranges to block
const PRIVATE_IPV6_PREFIXES = [
  "::1",          // loopback
  "fc",           // fc00::/7 unique local
  "fd",           // fd00::/8 unique local
  "fe80",         // fe80::/10 link-local
  "::ffff:0:0",   // IPv4-mapped IPv6
];

export function blockPrivateIp(hostname: string, rawUrl: string): void {
  // Strip brackets from IPv6 literals: [::1] → ::1
  const host = hostname.replace(/^\[|\]$/g, "").toLowerCase();

  // Check metadata hostnames
  if (METADATA_HOSTNAMES.has(host)) {
    throw new SSRFGuardError(
      "Blocked metadata service address",
      rawUrl,
      `'${host}' is a cloud metadata endpoint`
    );
  }

  // Check IPv4 private ranges
  for (const range of PRIVATE_IPV4_RANGES) {
    if (range.test(host)) {
      throw new SSRFGuardError(
        "Blocked private IP address",
        rawUrl,
        `'${host}' is in a private IPv4 range`
      );
    }
  }

  // Check IPv6 private prefixes
  for (const prefix of PRIVATE_IPV6_PREFIXES) {
    if (host === prefix || host.startsWith(prefix + ":")) {
      throw new SSRFGuardError(
        "Blocked private IPv6 address",
        rawUrl,
        `'${host}' is in a private IPv6 range`
      );
    }
  }
}
```

---

## Section 3 — DNS Rebinding Resistance: Resolve Before Fetch

DNS rebinding attacks work by having the hostname resolve to a public IP during the allowlist check but resolve to an internal IP when `fetch()` calls the resolver again. To mitigate, resolve the hostname once (using `DNS.resolve()` or a trusted DNS-over-HTTPS endpoint), validate the resolved IP, and then pass the IP directly to `fetch()` with the original `Host` header.

Workers do not expose a synchronous `getaddrinfo()` equivalent, but you can query Cloudflare's own `1.1.1.1` DoH API:

```typescript
// worker/src/lib/ssrf-guard.ts (continued)

/**
 * Resolve hostname via Cloudflare DoH, then validate the resolved IPs.
 * Returns the first valid IPv4 address.
 * Throws SSRFGuardError if any resolved IP is in a blocked range.
 */
export async function resolveAndValidate(hostname: string): Promise<string> {
  const dohUrl =
    `https://cloudflare-dns.com/dns-query?name=${encodeURIComponent(hostname)}&type=A`;

  const res = await fetch(dohUrl, {
    headers: { Accept: "application/dns-json" },
  });
  if (!res.ok) {
    throw new SSRFGuardError(
      "DNS resolution failed",
      hostname,
      `DoH returned ${res.status}`
    );
  }

  const data = (await res.json()) as {
    Answer?: Array<{ type: number; data: string }>;
  };

  const aRecords = (data.Answer ?? [])
    .filter((r) => r.type === 1)
    .map((r) => r.data.trim());

  if (aRecords.length === 0) {
    throw new SSRFGuardError(
      "No A records found",
      hostname,
      "Hostname did not resolve to any IPv4 address"
    );
  }

  // Validate every resolved IP — reject if ANY is in a private range
  for (const ip of aRecords) {
    blockPrivateIp(ip, `resolved from ${hostname}`);
  }

  return aRecords[0]; // Use first valid IP
}
```

Usage in the guarded fetch wrapper:

```typescript
// worker/src/lib/safe-fetch.ts
import { validateUrl, resolveAndValidate, SSRFGuardError } from "./ssrf-guard";

export async function safeFetch(
  rawUrl: string,
  init?: RequestInit
): Promise<Response> {
  // 1. Allowlist + scheme + literal-IP validation
  const validated = validateUrl(rawUrl);

  // 2. DNS rebinding protection: resolve hostname and validate IPs
  const resolvedIp = await resolveAndValidate(validated.hostname);

  // 3. Build a new URL using the resolved IP, preserving path/query/fragment
  const targetUrl = new URL(rawUrl);
  targetUrl.hostname = resolvedIp;

  // 4. Fetch with redirect:follow disabled (see Section 4)
  const response = await fetch(targetUrl.toString(), {
    ...init,
    redirect: "manual",
    headers: {
      ...(init?.headers ?? {}),
      // Preserve the original Host header so TLS SNI / virtual hosts work
      Host: validated.hostname,
    },
  });

  return response;
}
```

Note: passing a bare IP as the URL hostname while setting `Host` header manually requires the remote server to support IP-based connections or you to use TLS with explicit SNI. For most public APIs in the allowlist this is unnecessary — apply DNS pinning only to untrusted, user-supplied domains outside the allowlist.

---

## Section 4 — Preventing Redirect-Following to Internal Targets

`fetch()` in Workers follows redirects by default (`redirect: "follow"`). A redirect chain like:

```
https://safe.example.com/redirect → 302 → http://169.254.169.254/metadata
```

bypasses your URL validation entirely. Set `redirect: "manual"` and handle 3xx responses explicitly:

```typescript
// worker/src/lib/safe-fetch.ts (continued)
export async function safeFetchWithRedirects(
  rawUrl: string,
  init?: RequestInit,
  maxRedirects = 3
): Promise<Response> {
  let currentUrl = rawUrl;
  let hops = 0;

  while (hops <= maxRedirects) {
    const validated = validateUrl(currentUrl);

    const res = await fetch(currentUrl, {
      ...init,
      redirect: "manual",
    });

    // Non-redirect: done
    if (res.status < 300 || res.status >= 400) return res;

    // Extract Location header
    const location = res.headers.get("Location");
    if (!location) {
      throw new SSRFGuardError(
        "Redirect without Location header",
        currentUrl,
        `${res.status} response had no Location`
      );
    }

    // Resolve relative redirects against the current URL
    const nextUrl = new URL(location, currentUrl).toString();

    // Validate the redirect target — this is where SSRF via redirect is caught
    validateUrl(nextUrl);  // throws if not in allowlist or private IP

    currentUrl = nextUrl;
    hops++;

    // Re-use init only on the first hop; subsequent hops are GETs per HTTP spec
    init = { method: "GET", headers: init?.headers };
  }

  throw new SSRFGuardError(
    "Too many redirects",
    rawUrl,
    `Redirect chain exceeded ${maxRedirects} hops`
  );
}
```

---

## Section 5 — Cloudflare WAF Managed Rules as Defense-in-Depth

Allowlist validation in code is the primary control. Cloudflare WAF managed rules provide a defense-in-depth layer that catches SSRF attempts before they reach your Worker code — useful when the Worker itself is compromised or when a bypass is found.

Enable the Cloudflare OWASP Core Rule Set and the Cloudflare Managed Rules in your zone's WAF settings:

```bash
# Via Terraform
resource "cloudflare_ruleset" "zone_waf" {
  zone_id     = var.zone_id
  name        = "Zone WAF"
  description = "Zone-level WAF rules"
  kind        = "zone"
  phase       = "http_request_firewall_managed"

  rules {
    action = "execute"
    action_parameters {
      id = "efb7b8c949ac4650a09736fc376e9aee"  # Cloudflare Managed Ruleset
      overrides {
        # Enable SSRF protection rules
        rules {
          id      = "..." # SSRF rule IDs from Cloudflare docs
          enabled = true
          action  = "block"
        }
      }
    }
    expression  = "true"
    description = "Execute Cloudflare Managed Rules"
    enabled     = true
  }
}
```

Additionally, create a custom WAF rule to block requests containing metadata IP strings in query parameters or bodies:

```bash
# Cloudflare Dashboard → Security → WAF → Custom Rules → Create Rule
# Expression:
(http.request.uri.query contains "169.254.169.254")
or (http.request.body.raw contains "169.254.169.254")
or (http.request.uri.query contains "metadata.google.internal")
or (http.request.body.raw contains "192.168.")
or (http.request.body.raw contains "10.0.")
```

Action: Block. This catches SSRF payloads before they are deserialized by Worker code.

---

## Section 6 — Centralizing the Guard in a Middleware Pattern

Wrap all user-initiated fetch calls through a single middleware rather than adding checks at each call site:

```typescript
// worker/src/middleware/ssrf-middleware.ts
import { safeFetchWithRedirects, SSRFGuardError } from "../lib/safe-fetch";

type FetchLike = (url: string, init?: RequestInit) => Promise<Response>;

/**
 * Replace globalThis.fetch with a guarded version for user-supplied URLs.
 * Call this once at the top of your Worker handler.
 * Never use the guarded fetch for internal Cloudflare bindings (KV, D1, etc.)
 * — those use binding methods, not fetch().
 */
export function createGuardedFetch(allowedOrigins: string[]): FetchLike {
  return async (url: string, init?: RequestInit): Promise<Response> => {
    try {
      return await safeFetchWithRedirects(url, init);
    } catch (err) {
      if (err instanceof SSRFGuardError) {
        console.warn("[SSRF Guard]", err.reason, "|", err.url);
        // Return a safe 422 to the caller — do not leak internal error details
        return new Response(
          JSON.stringify({ error: "Invalid or disallowed URL" }),
          {
            status: 422,
            headers: { "Content-Type": "application/json" },
          }
        );
      }
      throw err;
    }
  };
}

// Usage in the Worker entry point:
// const guardedFetch = createGuardedFetch([]);
// const result = await guardedFetch(req.body.webhookUrl);
```

---

## Anti-Patterns

- **Denylist instead of allowlist.** Blocking known-bad IPs (only `169.254.169.254`) is fragile. New metadata endpoints, internal services, or IPv6 variants emerge. Always prefer an allowlist of known-good targets.
- **Checking only the hostname, not the resolved IP.** A hostname `public.attacker.com` can resolve to `169.254.169.254` via DNS. Always resolve and validate the IP separately.
- **`redirect: "follow"` with user-supplied URLs.** Redirect chains bypass URL-level checks. Always use `redirect: "manual"` and validate each hop.
- **Allowing `http://` for external fetch targets.** Require `https://` for all external requests. HTTP offers no transport security and can be intercepted on Cloudflare's network paths.
- **Logging the full URL on SSRF block.** The blocked URL may contain credentials or sensitive path segments. Log only the hostname and reason, not the full URL.
- **Using `URL.hostname` without stripping brackets.** `new URL("http://[::1]/")`. hostname` returns `"[::1]"` with brackets. Strip them before IP range checks.

---

## Gotchas

1. **`URL.hostname` for IPv6 literals includes brackets.** `new URL("http://[::1]/").hostname` is `"[::1]"`. Your regex must strip the surrounding brackets or it will miss the loopback check.
2. **Workers `fetch()` does resolve hostnames** — the resolution happens inside Cloudflare's network, not in your code. A DoH-based pre-check adds latency (~20–50 ms). Only apply it to genuinely untrusted, user-controlled hostnames.
3. **`redirect: "manual"` returns an opaque redirect response.** The `Location` header is accessible, but `res.body` is null and `res.url` is the original URL. Build the next URL by resolving `Location` against `currentUrl`.
4. **`Host` header override in Workers.** Workers strip and re-set `Host` based on the request URL. Setting `Host` manually in `fetch()` headers may be silently ignored depending on the Workers runtime version. Test against the actual behavior; the IP-substitution approach may not work as expected.
5. **Cloudflare WAF body inspection limit.** Custom WAF rules inspect request bodies up to 128 KB by default. Larger payloads with SSRF URLs embedded deep in the body may bypass WAF rules. Code-level validation is mandatory — WAF is supplemental.

---

## Verification

```typescript
// test/ssrf-guard.test.ts
import { validateUrl, blockPrivateIp, SSRFGuardError } from "../src/lib/ssrf-guard";
import { expect, test } from "vitest";

const blocked = [
  "http://169.254.169.254/latest/meta-data/",
  "http://10.0.0.1/admin",
  "http://192.168.1.1/",
  "http://127.0.0.1/",
  "http://[::1]/",
  "http://metadata.google.internal/",
  "file:///etc/passwd",
  "ftp://internal.example.com/",
  "http://100.64.0.1/",    // CGNAT
  "http://0.0.0.0/",
];

const allowed = [
  "https://api.stripe.com/v1/events",
  "https://hooks.slack.com/services/T0/B0/abc",
];

for (const url of blocked) {
  test(`blocks ${url}`, () => {
    expect(() => validateUrl(url)).toThrow(SSRFGuardError);
  });
}

for (const url of allowed) {
  test(`allows ${url}`, () => {
    expect(() => validateUrl(url)).not.toThrow();
  });
}
```

Run with:

```bash
npx vitest run test/ssrf-guard.test.ts
```

---

## Related Articles

- `documentation/categories/security/server-side-request-forgery-ssrf.md`
- `documentation/categories/security/ssrf-url-fetch-guard.md`
- `documentation/categories/security/outbound-url-policy-ssrf-and-dns-rebinding-resistance.md`
- `documentation/categories/security/open-redirect-prevention.md`
- `documentation/categories/security/cloudflare-waf-mobile-api-false-positives.md`
- `documentation/categories/security/http-request-smuggling-desync.md`

---

## Sources

- OWASP SSRF Prevention Cheat Sheet — https://cheatsheetseries.owasp.org/cheatsheets/Server_Side_Request_Forgery_Prevention_Cheat_Sheet.html
- RFC 1918 — https://www.rfc-editor.org/rfc/rfc1918
- AWS IMDS — https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/ec2-instance-metadata.html
- Cloudflare Workers fetch() API — https://developers.cloudflare.com/workers/runtime-apis/fetch/
- Cloudflare WAF managed rules — https://developers.cloudflare.com/waf/managed-rules/
- Cloudflare DoH API — https://developers.cloudflare.com/1.1.1.1/encryption/dns-over-https/make-api-requests/json/
