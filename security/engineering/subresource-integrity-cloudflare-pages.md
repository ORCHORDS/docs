# Subresource Integrity on Cloudflare Pages

- **Date**: 2026-08-22
- **Author**: example.com
- **Status**: active

## Symptom

A third-party analytics script on example project served via CDN was silently replaced by a compromised
version; SRI would have blocked it. Mobile clients show `net::ERR_INTEGRITY_MISMATCH` for a
script that works fine on desktop, caused by a build pipeline that generates different bundles per
target. Cloudflare Rocket Loader rewrites `<script>` tags, stripping `integrity` attributes.
`_headers` in Cloudflare Pages does not propagate `require-sri-for` to sub-resources loaded inside
Workers-rendered HTML.

## Context

example project (example.com) uses Cloudflare Pages for static asset hosting and Cloudflare Workers for the
API/render layer. Third-party scripts (analytics, error monitoring) are loaded from external CDNs.
SRI (Subresource Integrity) prevents a compromised CDN from serving malicious JS without
triggering a browser block. example project must also deal with Cloudflare-specific behaviours: Rocket Loader
modifies `<script>` elements, the Pages `_headers` file controls HTTP headers for static assets,
and Workers-rendered HTML requires SRI to be injected at render time.

---

## Generating SRI Hashes

SRI hashes are generated at build time from the exact bytes that will be served. Hash the
canonical CDN URL content at the pinned version.

```bash
# Generate SHA-384 hash for a specific pinned CDN asset
curl -sL "https://cdn.example.com/analytics/v2.3.1/analytics.min.js" \
  | openssl dgst -sha384 -binary \
  | openssl base64 -A
# Output: abc123...

# Automate in the build pipeline (Node.js)
node -e "
const { createHash } = require('crypto');
const { readFileSync } = require('fs');
const data = readFileSync('vendor/analytics.min.js');
const hash = createHash('sha384').update(data).digest('base64');
console.log('sha384-' + hash);
"
```

```ts
// scripts/generate-sri.ts  — run in CI to update sri-manifest.json
import { createHash } from 'crypto';
import { readFileSync, writeFileSync } from 'fs';

const THIRD_PARTY = {
  analytics: 'https://cdn.example.com/analytics/v2.3.1/analytics.min.js',
  sentry: 'https://browser.sentry-cdn.com/7.100.0/bundle.min.js',
};

async function generateManifest() {
  const manifest: Record<string, { url: string; integrity: string }> = {};
  for (const [name, url] of Object.entries(THIRD_PARTY)) {
    const res = await fetch(url);
    const buf = await res.arrayBuffer();
    const hash = createHash('sha384').update(Buffer.from(buf)).digest('base64');
    manifest[name] = { url, integrity: `sha384-${hash}` };
  }
  writeFileSync('src/sri-manifest.json', JSON.stringify(manifest, null, 2));
  console.log('SRI manifest updated');
}

generateManifest();
```

```html
<!-- HTML template — integrity + crossorigin are both required -->
<script
  src="https://cdn.example.com/analytics/v2.3.1/analytics.min.js"
  integrity="sha384-abc123..."
  crossorigin="anonymous"
  defer
></script>
```

`crossorigin="anonymous"` is required even for scripts loaded without credentials; without it,
browsers refuse to apply SRI checking.

---

## Cloudflare Pages `_headers` for SRI-related Headers

```text
# public/_headers  (Cloudflare Pages static header rules)

# Require SRI for scripts and styles on all HTML pages
/
  Content-Security-Policy: require-sri-for script style; default-src 'self'; script-src 'self' https://cdn.example.com https://browser.sentry-cdn.com; style-src 'self' https://fonts.googleapis.com

# Subresource integrity cannot be set as an HTTP header —
# it is an HTML attribute. _headers controls the HTTP response headers;
# the integrity attribute lives in the HTML served by Workers.

# Cache control for versioned static assets
/assets/*
  Cache-Control: public, max-age=31536000, immutable
  X-Content-Type-Options: nosniff

# HTML pages — short cache, fresh CSP
/*.html
  Cache-Control: no-cache
  X-Content-Type-Options: nosniff
```

`require-sri-for script style` in CSP instructs the browser to refuse any `<script>` or `<link
rel="stylesheet">` that lacks a valid `integrity` attribute. This is a defence-in-depth layer on
top of the `integrity` attributes already in the HTML.

---

## Hash Mismatch: Mobile vs Desktop

Hash mismatches between mobile and desktop typically have three causes:

| Cause                                        | Symptom                                        | Fix                                                      |
|----------------------------------------------|------------------------------------------------|----------------------------------------------------------|
| CDN serves different gzip variants           | Hash works on desktop, fails in some clients   | Hash the raw uncompressed bytes; CDN decompresses before delivery |
| Build pipeline generates per-platform bundles| Mobile bundle differs from desktop hash        | Pin a single universal bundle or maintain per-platform hashes |
| Rocket Loader minifies or rewrites the script| Hash of original ≠ hash of Rocket Loader output| Disable Rocket Loader for SRI-protected scripts (see below) |
| CDN version drift (version range `@latest`)  | Works on first load, breaks after CDN update   | Always pin an exact version, never use `@latest` or `^` |
| Brotli vs uncompressed hash source           | Mismatch on clients that decompress differently| Always hash pre-compression bytes                        |

```bash
# Verify the hash the browser will see (after CDN decompression)
# Do NOT hash the gzipped Content-Encoding output
curl -sL --compressed "https://cdn.example.com/analytics/v2.3.1/analytics.min.js" \
  | openssl dgst -sha384 -binary | openssl base64 -A
```

---

## Cloudflare Rocket Loader Conflict

Rocket Loader improves page performance by deferring JS execution. It does so by rewriting
`<script >` to `<script type="text/rocketscript" data-cf->`, which breaks SRI
because:
1. The `integrity` attribute is silently dropped.
2. The browser no longer matches the SRI hash to the modified tag.

```ts
// Workers HTML rewriting — inject data-cfasync="false" to opt out per script
import { HTMLRewriter } from '@cloudflare/workers-types';

function disableRocketLoaderForSriScripts(response: Response): Response {
  return new HTMLRewriter()
    .on('script[integrity]', {
      element(el) {
        // Rocket Loader skips scripts with data-cfasync="false"
        el.setAttribute('data-cfasync', 'false');
      },
    })
    .transform(response);
}
```

Alternatively, disable Rocket Loader globally via the Cloudflare dashboard:
Speed → Optimization → Content Optimization → Rocket Loader → Off.

Or scope it via a Page Rule / Cache Rule matching `example.com/*` with Rocket Loader = Off.

---

## Workers-Rendered HTML: Runtime SRI Injection

When Workers renders HTML (next-on-pages), SRI hashes must come from the build manifest:

```ts
// workers/src/lib/sri.ts
import sriManifest from '../../src/sri-manifest.json';

export function injectSriAttributes(html: string): string {
  // Use HTMLRewriter for streaming; this is for illustration
  for (const { url, integrity } of Object.values(sriManifest)) {
    const escapedUrl = url.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
    const regex = new RegExp(`(<script[^>]+src=["']${escapedUrl}["'][^>]*)(>)`, 'gi');
    html = html.replace(regex, (_m, before, end) => {
      if (before.includes('integrity=')) return _m; // already has integrity
      return `${before} integrity="${integrity}" crossorigin="anonymous"${end}`;
    });
  }
  return html;
}

// Better: use HTMLRewriter for streaming response
export function withSriInjection(response: Response): Response {
  return new HTMLRewriter()
    .on('script[src]', {
      element(el) {
        const src = el.getAttribute('src') ?? '';
        for (const { url, integrity } of Object.values(sriManifest)) {
          if (src === url && !el.getAttribute('integrity')) {
            el.setAttribute('integrity', integrity);
            el.setAttribute('crossorigin', 'anonymous');
            el.setAttribute('data-cfasync', 'false'); // disable Rocket Loader
          }
        }
      },
    })
    .transform(response);
}
```

---

## SRI Coverage Matrix for example project

| Asset type                     | SRI feasible? | Strategy                                          |
|--------------------------------|---------------|---------------------------------------------------|
| Third-party analytics script   | Yes           | Pin version, hash at build time                   |
| Sentry browser SDK             | Yes           | Use Sentry's published SRI hashes per release     |
| Google Fonts stylesheet        | No (dynamic)  | Use CSP `style-src` allowlist instead             |
| Self-hosted Cloudflare Pages assets| Yes (auto)| Next.js content-hash filenames; `integrity` in manifest |
| Web Workers (Worker scripts)   | Yes           | `integrity` on `new Worker(url, {credentials:'...'})` |
| Dynamic `import()` chunks      | Partial       | `importmap` with integrity (limited browser support)|

---

## Anti-patterns

- Using `sha256` instead of `sha384` or `sha512`: SHA-256 is technically acceptable but SHA-384
  is the example project standard for new assets; some CSP `require-sri-for` implementations prefer the
  stronger hash.
- Generating the hash from a local dev copy rather than the CDN-served bytes: the CDN may serve
  a differently whitespace-normalised or minified file.
- Adding `integrity` without `crossorigin`: browsers treat the fetch as no-CORS and cannot
  compare the hash; the SRI check silently does not run.
- Checking in `sri-manifest.json` without a CI step that re-validates hashes against live CDN
  URLs: the manifest goes stale when CDN content changes.
- Applying SRI to first-party assets via `_headers` CDN rules that cache-bust with query params:
  the URL changes but the hash in the HTML does not update.

## Gotchas

- Firefox enforces `require-sri-for` strictly — Chrome historically treated it as advisory;
  test on Firefox to catch missing integrity attributes early.
- Cloudflare's Minify feature (JS/CSS/HTML minification) can alter script bytes after SRI hashes
  are baked into HTML — disable minification for SRI-protected scripts or minify before hashing.
- `integrity` on `<link rel="preload" as="script">` is separate from `integrity` on the
  corresponding `<script>` tag — both must have matching hashes or Chrome rejects the preload.
- example project's Workers environment does not have `fs` — the build-time SRI manifest must be bundled
  into the Worker as a JSON import, not read from disk at runtime.

## Verification

```bash
# 1. Confirm integrity attributes are present in HTML response
curl -s https://example.com/ | grep -o 'integrity="[^"]*"'

# 2. Manually validate a hash
curl -sL "https://cdn.example.com/analytics/v2.3.1/analytics.min.js" \
  | openssl dgst -sha384 -binary | openssl base64 -A
# Must match the value in HTML

# 3. Test SRI rejection in browser
# Change one character in the integrity hash, reload — expect net::ERR_INTEGRITY_MISMATCH

# 4. Confirm Rocket Loader is not stripping integrity
curl -s https://example.com/ | grep -A2 'cdn.example.com' | grep 'data-cfasync\|integrity'
# Expect: integrity attribute present AND data-cfasync="false"

# 5. CI gate — fail if any third-party script lacks integrity
node -e "
const html = require('fs').readFileSync('dist/index.html', 'utf8');
const scripts = [...html.matchAll(/<script[^>]+src=[\"'][^\"']*\/\/[^\"']*[\"'][^>]*>/g)];
scripts.forEach(([tag]) => {
  if (!tag.includes('integrity=')) {
    console.error('Missing SRI:', tag);
    process.exit(1);
  }
});
console.log('All external scripts have SRI hashes');
"
```

## Related

- `subresource-integrity-sri.md`
- `subresource-integrity-sri-cdn-assets.md`
- `content-security-policy-workers-nonce.md`
- `content-security-policy-workers-pages.md`
- `supply-chain-security-slsa-sigstore.md`
- `dependency-supply-chain-security-npm.md`

## Sources

- W3C SRI spec: https://www.w3.org/TR/SRI/
- MDN SRI: https://developer.mozilla.org/en-US/docs/Web/Security/Subresource_Integrity
- Cloudflare Rocket Loader: https://developers.cloudflare.com/speed/optimization/content/rocket-loader/
- Cloudflare Pages _headers: https://developers.cloudflare.com/pages/configuration/headers/
- require-sri-for CSP directive: https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers/Content-Security-Policy/require-sri-for
