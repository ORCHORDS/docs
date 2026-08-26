# Workers URL API SSRF Bypass via Spec-Compliant Edge Cases

Date: 2026-08-24 / Author: example.com / Status: production

---

## Symptom / Use-case

A Cloudflare Worker proxies or validates a caller-supplied URL before passing it to `fetch()`.
The Worker uses `new URL(input)` to parse and inspect the host, but certain spec-compliant URL
forms — credential embedding, numeric IP representations, Unicode normalization, embedded null
bytes, and scheme-relative forms — let an attacker reach internal or disallowed origins even
though the host-check branch evaluated to safe.

Affected patterns:

- Proxy Workers that forward to allow-listed domains
- CORS proxies that gate on hostname
- Workers that call third-party APIs with caller-controlled paths/subdomains
- Any Worker that normalizes a URL and then `fetch()`es the normalized value

---

## Context

The WHATWG URL Standard defines normalization rules designed for interoperability, not security.
Cloudflare Workers implement that same standard faithfully, meaning the parser accepts and
silently transforms inputs that a naive string check passes but that route to unexpected hosts.

Common bypasses fall into four categories:

| Category | Example input | Parsed host |
|---|---|---|
| Embedded credentials | `https://evil.com@allowed.com/` | `allowed.com` (string), but fetch target is `evil.com` |
| Numeric IP forms | `http://0x7f000001/` | `127.0.0.1` |
| Unicode NFC collapse | `https://аllowed.com/` (Cyrillic а) | Punycode → different domain |
| Scheme-relative | `//evil.com/` supplied to `new URL(input, base)` | Inherits caller scheme, resolves to `evil.com` |

Workers that call `url.hostname` or `url.host` after parsing may observe the attacker-chosen
value; the WHATWG parser moves credentials to `url.username`/`url.password` and sets `hostname`
to the portion *after* the `@`, but `fetch()` treats the full serialized URL differently.

---

## Code sections

### 1. Vulnerable allow-list check

```typescript
// VULNERABLE — do not use
export default {
  async fetch(request: Request): Promise<Response> {
    const target = new URL(request.url).searchParams.get("url") ?? "";
    const parsed = new URL(target);

    // Attacker supplies: https://evil.com@allowed.com/
    // parsed.hostname === "allowed.com"  <- passes
    // fetch(target) resolves to evil.com <- bypasses check
    if (parsed.hostname !== "allowed.com") {
      return new Response("Forbidden", { status: 403 });
    }
    return fetch(target);  // routes to attacker-controlled host
  },
};
```

### 2. Safe allow-list with serialized re-construction

Always re-serialize the URL through the WHATWG parser, reject any URL that contains a username
or password, and then build a new URL from only the components you control.

```typescript
const ALLOWED_HOSTS = new Set(["allowed.com", "api.allowed.com"]);

function safeParseProxyTarget(raw: string, base?: string): URL {
  let parsed: URL;
  try {
    parsed = new URL(raw, base);
  } catch {
    throw new Error("Invalid URL");
  }

  // Reject credentials — they alter fetch routing
  if (parsed.username !== "" || parsed.password !== "") {
    throw new Error("URL must not contain credentials");
  }

  // Only permit https
  if (parsed.protocol !== "https:") {
    throw new Error("Only https: URLs are permitted");
  }

  // Check canonical hostname (already punycode-normalised by parser)
  if (!ALLOWED_HOSTS.has(parsed.hostname)) {
    throw new Error(`Host ${parsed.hostname} is not allowed`);
  }

  // Reconstruct from safe components only — discard any attacker-supplied authority
  return new URL(`https://${parsed.hostname}${parsed.pathname}${parsed.search}`);
}

export default {
  async fetch(request: Request): Promise<Response> {
    const raw = new URL(request.url).searchParams.get("url") ?? "";
    let safe: URL;
    try {
      safe = safeParseProxyTarget(raw);
    } catch (e) {
      return new Response(String(e), { status: 400 });
    }
    return fetch(safe.toString());
  },
};
```

### 3. Blocking numeric IP representations

```typescript
// IPv4-mapped IPv6, decimal, octal, hex integer forms all normalize to loopback
function isPrivateOrLoopback(hostname: string): boolean {
  // After WHATWG parsing, IPv4 is always dotted-decimal; IPv6 is bracketed
  const ipv4Re = /^(\d{1,3})\.(\d{1,3})\.(\d{1,3})\.(\d{1,3})$/;
  const m = ipv4Re.exec(hostname);
  if (m) {
    const [, a, b, c, d] = m.map(Number);
    if (
      a === 127 ||                          // loopback
      a === 10 ||                           // RFC-1918
      (a === 172 && b >= 16 && b <= 31) ||  // RFC-1918
      (a === 192 && b === 168) ||           // RFC-1918
      a === 169 && b === 254 ||             // link-local
      a === 100 && b >= 64 && b <= 127      // CGN
    ) return true;
  }

  // IPv6 loopback ::1 and link-local fe80::
  if (hostname === "[::1]") return true;
  if (hostname.startsWith("[fe80:")) return true;
  if (hostname.startsWith("[fc") || hostname.startsWith("[fd")) return true;

  return false;
}
```

### 4. Scheme-relative URL injection via `new URL(input, base)`

```typescript
// VULNERABLE: caller-supplied path joined to base
function buildEndpoint(path: string): URL {
  // If path is "//evil.com/steal", new URL resolves to https://evil.com/steal
  return new URL(path, "https://api.internal.example/");
}

// SAFE: strip leading slashes, percent-encode, append to base explicitly
function buildEndpointSafe(path: string): URL {
  // Strip any leading slashes to prevent authority override
  const stripped = path.replace(/^\/+/, "");
  // The base URL guarantees authority; only the encoded path segment is caller-supplied
  const base = new URL("https://api.internal.example/");
  base.pathname = "/" + stripped.split("/").map(encodeURIComponent).join("/");
  return base;
}
```

### 5. Unicode homograph detection

```typescript
// After WHATWG parsing, IDN labels are converted to punycode.
// Detect if the punycode form differs from the ASCII expected form.
function rejectHomograph(hostname: string, expected: string): void {
  // The parser has already converted e.g. "аllowed.com" → "xn--llowed-uba.com"
  if (hostname !== expected) {
    throw new Error(
      `Homograph or IDN mismatch: got ${hostname}, expected ${expected}`
    );
  }
}

// Usage after URL construction:
const parsed = new URL(raw);
rejectHomograph(parsed.hostname, "allowed.com");
```

### 6. Integration test harness (Vitest)

```typescript
import { describe, it, expect } from "vitest";
import { safeParseProxyTarget } from "./url-guard";

describe("safeParseProxyTarget", () => {
  it("blocks credential injection", () => {
    expect(() =>
      safeParseProxyTarget("https://evil.com@allowed.com/data")
    ).toThrow("credentials");
  });

  it("blocks numeric loopback", () => {
    // 0x7f000001 normalizes to 127.0.0.1 after WHATWG parse
    expect(() => safeParseProxyTarget("http://0x7f000001/")).toThrow();
  });

  it("blocks scheme-relative URL via base", () => {
    expect(() =>
      safeParseProxyTarget("//evil.com/", "https://allowed.com/")
    ).toThrow("https:");
  });

  it("passes a clean URL on the allow-list", () => {
    const u = safeParseProxyTarget("https://allowed.com/api/v1/data?q=1");
    expect(u.hostname).toBe("allowed.com");
    expect(u.username).toBe("");
  });
});
```

---

## Anti-patterns

- Using `url.hostname` as the sole gate and then `fetch(originalString)` — these may differ.
- Checking `.host` (includes port) for equality while allowing arbitrary ports — `allowed.com:8080` passes a `.hostname` check but may reach an internal service.
- Blocking a static denylist of private CIDRs without also blocking non-standard IP forms.
- Relying on `URL.canParse()` to indicate safety — it only checks syntax, not routing destination.
- Allowing `data:`, `blob:`, `javascript:`, or `file:` schemes by omitting a protocol allowlist.

---

## Gotchas

- Workers' `fetch()` follows redirects by default (`redirect: "follow"`). A safe origin can redirect to an unsafe one. Pass `redirect: "error"` or `redirect: "manual"` for proxy Workers.
- The WHATWG parser accepts null bytes inside percent-encoded sequences (`%00`) in path position. Reject any URL whose raw string contains `\0` or `%00` before parsing.
- `url.href` and `url.toString()` return the serialized canonical form; always fetch the re-serialized form, never the attacker-supplied raw string.
- Cloudflare's network blocks RFC-1918 space at the fetch layer, but that protection is not a substitute for application-level validation — it may change, and it does not protect same-network resources reachable via your account (Tunnels, Service Bindings).
- Subdomains of an allowed host are NOT allowed implicitly; `.hostname` must be compared with `===`, not `.endsWith()`.

---

## Verification

```bash
# 1. Unit tests
npx vitest run workers/url-guard.test.ts

# 2. Manual spot-check against credential injection
curl "https://worker.example.com/proxy?url=https://evil.com%40allowed.com/"
# expect: 400 with "credentials" message

# 3. Redirect-follow check
curl -v "https://worker.example.com/proxy?url=https://allowed.com/redirect-to-127"
# expect: 5xx or 400 if redirect: "error" is set

# 4. Wrangler local smoke test
npx wrangler dev &
curl "http://localhost:8787/proxy?url=//evil.com/"
# expect: 400 with scheme error
```

---

## Related

- `ssrf-prevention-workers-fetch-allowlist.md`
- `ssrf-url-fetch-guard.md`
- `open-redirect-prevention.md`
- `workers-fetch-ssrf-redirect-following.md`
- `outbound-url-policy-ssrf-and-dns-rebinding-resistance.md`

---

## Sources

- WHATWG URL Standard — https://url.spec.whatwg.org/
- PortSwigger: SSRF via URL parser confusion — https://portswigger.net/research/ssrf-in-php
- Cloudflare Workers `fetch()` documentation — https://developers.cloudflare.com/workers/runtime-apis/fetch/
- Orange Tsai: "A New Era of SSRF" (BlackHat USA 2017)
- RFC 3986 §3.2.1 — userinfo in authority component
