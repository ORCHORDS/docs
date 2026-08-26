# Cloudflare Pages Security Headers via _headers File

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

A Cloudflare Pages site needs security headers (HSTS, CSP, X-Frame-Options, Permissions-
Policy, etc.) on every page. Adding a Pages Function just to set headers on static assets
is wasteful — it adds cold-start latency and counts against function invocations. The
`_headers` file applies headers at the CDN layer, before any function runs, with zero
execution overhead.

## Context

Cloudflare Pages respects a `_headers` file placed at the root of the published output
directory. Rules are matched top-to-bottom; the first match wins for each response.
Headers added here are merged with any headers the origin or a Pages Function also sets —
but `_headers` rules apply before Functions, so a Function can override them if needed.
The file is not served to clients; it is read by the Pages runtime at build time.

---

## File Location and Format

Place `_headers` in the same directory as your `index.html` (the output root). For
frameworks: `public/_headers` (Hugo, Eleventy), `dist/_headers` (Vite, Astro),
`out/_headers` (Next.js static export).

```
# _headers
# Format: URL pattern (one per line), then header directives indented with spaces or tabs.
# Comments start with #. Blank lines are ignored.

/
  Header-Name: value

/path/*
  Header-Name: value
```

---

## Security Headers Template

```
/*
  Strict-Transport-Security: max-age=31536000; includeSubDomains; preload
  X-Content-Type-Options: nosniff
  X-Frame-Options: DENY
  Referrer-Policy: strict-origin-when-cross-origin
  Permissions-Policy: camera=(), microphone=(), geolocation=(), interest-cohort=()
  Cross-Origin-Opener-Policy: same-origin
  Cross-Origin-Embedder-Policy: require-corp
  Cross-Origin-Resource-Policy: same-origin

/
  Content-Security-Policy: default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: https://images.example.com; font-src 'self'; connect-src 'self' https://api.example.com; frame-ancestors 'none'; base-uri 'self'; form-action 'self'

/blog/*
  Content-Security-Policy: default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: https:; font-src 'self'; frame-ancestors 'none'
```

---

## API Routes — Remove Caching Headers, Add Security Headers

For Pages Functions that act as API endpoints, suppress the CDN cache and add API-specific
headers:

```
/api/*
  Cache-Control: no-store
  X-Content-Type-Options: nosniff
  X-Robots-Tag: noindex
  Access-Control-Allow-Origin: https://app.example.com
```

---

## Static Asset Caching with Immutable Flag

Long-cache fingerprinted assets combined with security headers:

```
/assets/*
  Cache-Control: public, max-age=31536000, immutable
  X-Content-Type-Options: nosniff
  Cross-Origin-Resource-Policy: cross-origin
```

`CORP: cross-origin` is correct here — static assets (fonts, images, scripts) must be
loadable cross-origin. Apply `same-origin` only to document responses.

---

## Removing Unwanted Default Headers

Pages adds `ETag` and sometimes `CF-Ray` to static responses. The `_headers` file can
remove headers too:

```
/*
  ! Server
  ! X-Powered-By
```

The `!` prefix removes a header. Use this to strip headers that disclose server software
or framework versions.

---

## Overriding Headers per Content Type

HTML files need a CSP; JSON files do not. Use path-based rules rather than trying to
match on Content-Type (the `_headers` file has no content-type matching):

```
/*.html
  Content-Security-Policy: default-src 'self'; frame-ancestors 'none'

/*.json
  Content-Security-Policy:
  X-Content-Type-Options: nosniff
```

Setting a header to an empty value removes it for that path (in Pages, an empty value
replaces the parent rule).

---

## Build-Time Verification Script

Add this to CI to catch missing security headers before deployment:

```typescript
// scripts/verify-headers.ts — run with: npx tsx scripts/verify-headers.ts
import { readFileSync } from "fs";

const REQUIRED_ON_ALL_PATHS = [
  "Strict-Transport-Security",
  "X-Content-Type-Options",
  "X-Frame-Options",
  "Referrer-Policy",
];

interface Rule {
  pattern: string;
  headers: Record<string, string>;
}

function parseHeadersFile(path: string): Rule[] {
  const lines = readFileSync(path, "utf8").split("\n");
  const rules: Rule[] = [];
  let current: Rule | null = null;

  for (const rawLine of lines) {
    const line = rawLine.trimEnd();
    if (!line || line.startsWith("#")) continue;

    if (!line.startsWith(" ") && !line.startsWith("\t")) {
      // New URL pattern.
      current = { pattern: line.trim(), headers: {} };
      rules.push(current);
    } else if (current) {
      const colonIdx = line.indexOf(":");
      if (colonIdx === -1) continue;
      const name  = line.slice(0, colonIdx).trim();
      const value = line.slice(colonIdx + 1).trim();
      if (!name.startsWith("!")) {
        current.headers[name.toLowerCase()] = value;
      }
    }
  }

  return rules;
}

function verifyHeaders(headersFilePath: string): void {
  const rules = parseHeadersFile(headersFilePath);
  const wildcardRule = rules.find((r) => r.pattern === "/*");

  if (!wildcardRule) {
    console.error("ERROR: No /* rule found in _headers");
    process.exit(1);
  }

  let failed = false;
  for (const required of REQUIRED_ON_ALL_PATHS) {
    if (!(required.toLowerCase() in wildcardRule.headers)) {
      console.error(`MISSING on /*: ${required}`);
      failed = true;
    }
  }

  if (failed) process.exit(1);
  console.log("_headers verification passed.");
}

verifyHeaders("public/_headers");
```

---

## Anti-patterns

- **Setting `Content-Security-Policy` only on `/*` with `'unsafe-inline'` scripts** —
  use path-specific rules and tighten the CSP for HTML pages.
- **Using `_headers` for dynamic values** — the file is static; nonces, CSRF tokens, or
  per-user headers must come from Pages Functions.
- **Setting `Access-Control-Allow-Origin: *` in `_headers` for authenticated routes** —
  CORS wildcards bypass credential checks. Scope CORS rules to `/api/*` and use specific
  origins.
- **Forgetting `frame-ancestors 'none'` in CSP while also setting `X-Frame-Options`** —
  both are needed; `X-Frame-Options` is for older browsers but CSP `frame-ancestors`
  takes precedence in modern browsers.
- **Long `max-age` on the root HTML** — fingerprinted assets can have `max-age=31536000`,
  but `index.html` should use `Cache-Control: no-cache` to allow instant revalidation.

## Gotchas

- The `_headers` file is case-insensitive for header names but case-sensitive for URL
  patterns. `/About` and `/about` are different patterns.
- Pages limits `_headers` to 100 rules and 2000 characters per header value.
- If a Pages Function also sets a header with the same name, the Function's value wins —
  the `_headers` value is overwritten, not appended.
- `preload` in HSTS requires your domain to be on the HSTS preload list; adding it
  without prior submission permanently marks the domain HTTPS-only in browsers.
- `Cross-Origin-Embedder-Policy: require-corp` breaks loading third-party resources
  without CORP headers (e.g., many CDN-hosted images and analytics scripts).

## Verification

```bash
# After deployment, check headers on root:
curl -si https://your-site.pages.dev/ \
  | grep -iE "strict-transport|content-security|x-frame|x-content-type|referrer"

# Check that /api/* has no-store:
curl -si https://your-site.pages.dev/api/health \
  | grep -i cache-control

# Confirm assets have immutable:
curl -si https://your-site.pages.dev/assets/main-abc123.js \
  | grep -i cache-control

# Observatory / security header scanner:
# https://observatory.mozilla.org/analyze/your-site.pages.dev
```

## Related

- `content-security-policy-workers-pages.md` — CSP with Pages Functions
- `hsts-preload-list-management-workers.md` — HSTS preload submission and management
- `security-headers-comprehensive.md` — full header reference
- `permissions-policy-header.md` — Permissions-Policy directive catalogue

## Sources

- Cloudflare Pages _headers file: https://developers.cloudflare.com/pages/configuration/headers/
- MDN HTTP headers security reference: https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers#security
- Mozilla Observatory: https://observatory.mozilla.org/
- HSTS Preload list: https://hstspreload.org/
