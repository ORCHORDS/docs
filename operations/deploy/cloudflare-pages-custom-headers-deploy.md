# Cloudflare Pages Custom Headers Deploy

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

You need to ship custom HTTP response headers with your Cloudflare Pages site — security
headers (CSP, HSTS, Permissions-Policy), cache-control overrides for specific asset
patterns, CORS headers for API routes served through Pages Functions, or cross-origin
isolation headers (`COOP`/`COEP`) required by `SharedArrayBuffer`. These must be
managed as code, version-controlled, and validated in CI before reaching production.

## Context

Cloudflare Pages respects a special `_headers` plain-text file placed at the root of
the **build output directory**. At deploy time the edge reads this file and merges its
rules into responses. Rules apply in order; later matching rules do not override earlier
ones for the same header (first-match wins per header name). The `_headers` file is an
alternative to writing a Pages Function middleware purely for header injection.

Pages Functions middleware (`functions/_middleware.ts`) is the programmatic alternative
when header logic needs dynamic values (e.g. nonce injection for CSP). Use `_headers`
for static, path-pattern-based rules.

---

## _headers File Format

```text
# Syntax: URL path pattern (one per section)
# followed by indented "Header-Name: value" lines

# Root and all sub-paths
/*
  X-Frame-Options: DENY
  X-Content-Type-Options: nosniff
  Referrer-Policy: strict-origin-when-cross-origin
  Permissions-Policy: camera=(), microphone=(), geolocation=()

# Strict security headers for the app shell
/index.html
  Content-Security-Policy: default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' data: https:; connect-src 'self' https://api.example.com; frame-ancestors 'none'
  X-Frame-Options: DENY
  Cross-Origin-Opener-Policy: same-origin
  Cross-Origin-Embedder-Policy: require-corp

# Long-lived cache for hashed static assets
/assets/*
  Cache-Control: public, max-age=31536000, immutable

# No caching for service worker
/sw.js
  Cache-Control: no-cache, no-store, must-revalidate

# API proxy through Pages Functions — CORS
/api/*
  Access-Control-Allow-Origin: https://app.example.com
  Access-Control-Allow-Methods: GET, POST, OPTIONS
  Access-Control-Allow-Headers: Content-Type, Authorization
  Access-Control-Max-Age: 86400
```

---

## Placing _headers in the Build Output

The file must live in the directory you configure as `pages_build_output_dir` in
`wrangler.toml`, **not** in the repo root.

```toml
# wrangler.toml
name        = "my-app"
pages_build_output_dir = "dist"
```

```bash
# Vite / React / Vue build: put _headers in public/ so Vite copies it to dist/
cp _headers public/_headers

# Or configure via vite.config.ts to always copy:
```

```typescript
// vite.config.ts
import { defineConfig } from "vite";
import { viteStaticCopy } from "vite-plugin-static-copy";

export default defineConfig({
  plugins: [
    viteStaticCopy({
      targets: [{ src: "_headers", dest: "." }],
    }),
  ],
  build: { outDir: "dist" },
});
```

For Next.js (via `@cloudflare/next-on-pages`):

```bash
# _headers goes in the project root; next-on-pages copies it to .vercel/output/static
# Verify after build:
ls .vercel/output/static/_headers
```

---

## CI Validation Gate

Validate the `_headers` file before every deploy to catch syntax errors early.

```typescript
// scripts/validate-headers.ts
import { readFileSync } from "fs";
import { resolve } from "path";

function validateHeaders(filePath: string): void {
  const lines = readFileSync(filePath, "utf8").split("\n");
  let inBlock = false;
  let errors: string[] = [];

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    const lineNum = i + 1;

    if (!line.trim() || line.startsWith("#")) continue;

    if (!line.startsWith(" ") && !line.startsWith("\t")) {
      // Path rule
      if (!line.startsWith("/")) {
        errors.push(`Line ${lineNum}: path rule must start with /`);
      }
      inBlock = true;
    } else if (inBlock) {
      // Header line
      const trimmed = line.trim();
      if (!trimmed.includes(":")) {
        errors.push(`Line ${lineNum}: header line missing colon — "${trimmed}"`);
      }
    }
  }

  if (errors.length > 0) {
    console.error("_headers validation failed:\n" + errors.join("\n"));
    process.exit(1);
  }
  console.log(`_headers OK — ${lines.length} lines validated`);
}

validateHeaders(resolve(process.cwd(), "public/_headers"));
```

```yaml
# .github/workflows/pages-deploy.yml
name: Pages Deploy

on:
  push:
    branches: [main, staging]

jobs:
  validate-and-deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-node@v4
        with: { node-version: "22" }

      - run: npm ci

      - name: Validate _headers
        run: npx tsx scripts/validate-headers.ts

      - name: Build
        run: npm run build

      - name: Verify _headers in output
        run: |
          if [[ ! -f dist/_headers ]]; then
            echo "ERROR: _headers missing from dist/" && exit 1
          fi
          echo "Found $(wc -l < dist/_headers) lines in dist/_headers"

      - name: Deploy to Pages
        run: npx wrangler pages deploy dist --project-name my-app
        env:
          CLOUDFLARE_API_TOKEN: ${{ secrets.CF_API_TOKEN }}
          CLOUDFLARE_ACCOUNT_ID: ${{ secrets.CF_ACCOUNT_ID }}
```

---

## Header Precedence Rules

- `_headers` rules apply **before** Pages Functions middleware response headers.
- When both `_headers` and a Function set the same header name, the **Function wins**
  because it runs after the static asset response is assembled.
- To override a header set in `_headers` from a Function, call
  `response.headers.set(name, value)` explicitly.
- Multiple matching path patterns in `_headers` for the same URL: **first match wins**
  per header. Put more specific paths earlier in the file.

---

## Security Headers Quick-Reference

```text
# _headers — production security baseline
/*
  Strict-Transport-Security: max-age=63072000; includeSubDomains; preload
  X-Content-Type-Options: nosniff
  X-Frame-Options: DENY
  Referrer-Policy: strict-origin-when-cross-origin
  Permissions-Policy: accelerometer=(), camera=(), geolocation=(), gyroscope=(), magnetometer=(), microphone=(), payment=(), usb=()

/index.html
  Content-Security-Policy: default-src 'self'; object-src 'none'; base-uri 'self'; form-action 'self'; frame-ancestors 'none'; upgrade-insecure-requests
  Cross-Origin-Opener-Policy: same-origin
  Cross-Origin-Resource-Policy: same-origin
```

---

## Anti-patterns

- **Putting `_headers` in the repo root instead of the build output directory** — Pages
  only reads the file from the output dir; it is silently ignored otherwise.
- **Using `_headers` for dynamic nonces in CSP** — nonces must be generated per-request;
  use Pages Functions middleware for that.
- **Overly broad `Access-Control-Allow-Origin: *` on all routes** — scope CORS to
  `/api/*` only, never to `/*`.
- **Forgetting `Cache-Control` for hashed assets** — without `immutable` the browser
  revalidates on every load even though the URL will never change.

## Gotchas

- The Pages preview environment uses the **same** `_headers` file as production; there
  is no per-environment override mechanism within `_headers`. Use Pages Functions
  middleware with `env.ENVIRONMENT` bindings for env-specific header logic.
- `_headers` does not support wildcards mid-path like `/api/v*/endpoint`. Only prefix
  wildcards (`/api/*`) are supported.
- Large `_headers` files (thousands of rules) can noticeably slow cache lookup at the
  edge. Consolidate rules with broader patterns where possible.
- Headers with multiple values (e.g. `Link: <foo>; rel=preload, <bar>; rel=preload`)
  must be on a single line; `_headers` has no multi-line value syntax.

## Verification

```bash
# Deploy then probe headers
wrangler pages deploy dist --project-name my-app

# Inspect response headers from the production URL
curl -sI https://my-app.pages.dev/ | grep -E "x-frame|content-security|cache-control|strict-transport"

# Check a specific asset path
curl -sI https://my-app.pages.dev/assets/main.abc123.js | grep cache-control
# Expected: cache-control: public, max-age=31536000, immutable
```

## Related

- `cloudflare-pages-ab-test-deploy-headers.md`
- `cloudflare-pages-redirect-rule-deploy-validation.md`
- `pages-functions-middleware-deploy-chain-validation.md`
- `cloudflare-pages-custom-build-config.md`

## Sources

- https://developers.cloudflare.com/pages/configuration/headers/
- https://developers.cloudflare.com/pages/functions/middleware/
- https://developers.cloudflare.com/pages/configuration/build-configuration/#build-output-directory
- https://web.dev/security-headers/
