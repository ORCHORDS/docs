# subresource-integrity-sri-cdn-assets

**Date:** 2026-08-17
**Author:** the platform team
**Status:** published

## Symptom

A CDN delivers a third-party analytics script that was silently
updated overnight; the new version exfiltrates session tokens. The app
loads it with no `integrity` attribute. Separately, a CI pipeline
generates SRI hashes at build time, deploys them, and Cloudflare's
Rocket Loader then rewrites the script tag — the browser rejects it:
`Failed to find a valid digest in the 'integrity' attribute`.

## Context

Subresource Integrity (SRI) instructs the browser to verify that a
fetched resource's exact bytes match a cryptographic hash before
executing it. It is the primary browser-enforced control against CDN
compromise, package publisher account takeover, and in-path script
injection. SRI is free to implement and supported in all modern
browsers, but interacts with Cloudflare features (Rocket Loader, Zaraz)
and CI-generated versioned URLs in ways that require deliberate
integration.

## Generating SRI hashes with openssl dgst -sha384

SHA-384 is the recommended algorithm: stronger than SHA-256 and
universally supported.

```bash
# Hash a local file
openssl dgst -sha384 -binary path/to/script.js \
  | openssl base64 -A

# Hash a remote versioned asset
curl -fsSL https://cdn.example.com/lib@2.1.0/dist/lib.min.js \
  | openssl dgst -sha384 -binary | openssl base64 -A

# Build the complete integrity value
echo "sha384-$(curl -fsSL \
  https://cdn.example.com/lib@2.1.0/dist/lib.min.js \
  | openssl dgst -sha384 -binary | openssl base64 -A)"
```

Multiple algorithms for migration:
```html
integrity="sha384-<hash1> sha512-<hash2>"
```
The browser uses the strongest algorithm it supports. Drop the weaker
one after all clients have upgraded.

## integrity and crossorigin attributes

Both attributes are required for cross-origin resources.

```html
<!-- External script -->
<script
  src="https://cdn.example.com/lib@2.1.0/dist/lib.min.js"
  integrity="sha384-oqVuAfXRKap7fdgcCY5uykM6+R9GqQ8K..."
  crossorigin="anonymous">
</script>

<!-- External stylesheet -->
<link
  rel="stylesheet"
  href="https://cdn.example.com/theme@3.0.0/dist/theme.min.css"
  integrity="sha384-xyz789..."
  crossorigin="anonymous">
```

`crossorigin="anonymous"` forces a CORS request; the CDN must return
`Access-Control-Allow-Origin: *`. Without `crossorigin`, SRI is not
enforced for cross-origin resources — it is silently ignored.

Do not use `crossorigin="use-credentials"` for CDN assets: it sends
cookies and requires the CDN to echo the exact origin, breaking
shared caching.

## SRI for dynamically versioned assets — CI generates hashes

When asset URLs include a build hash that changes each release, hashes
must be generated in CI and written into the HTML template at build
time. Never compute or copy SRI hashes by hand.

```yaml
# .github/workflows/build.yml
- name: Download asset and generate SRI
  run: |
    ASSET_URL="https://cdn.example.com/lib@${LIB_VERSION}/dist/lib.min.js"
    curl -fsSL "$ASSET_URL" -o dist/vendor/lib.min.js
    HASH=$(openssl dgst -sha384 -binary dist/vendor/lib.min.js \
      | openssl base64 -A)
    echo "LIB_SRI=sha384-${HASH}" >> "$GITHUB_ENV"

- name: Inject SRI into HTML template
  run: sed -i "s|__LIB_SRI__|${LIB_SRI}|g" public/index.html
```

```html
<!-- public/index.html — placeholder replaced by CI -->
<script src="https://cdn.example.com/lib@2.1.0/dist/lib.min.js"
        integrity="__LIB_SRI__"
        crossorigin="anonymous"></script>
```

## Interaction with Cloudflare Cache and Rocket Loader

Any feature that rewrites HTML or modifies script bytes will
invalidate SRI hashes:

| Feature | Effect | Mitigation |
|---|---|---|
| Rocket Loader | Rewrites `<script>` tags | `data-cfasync="false"` or disable |
| Zaraz | Replaces third-party tags | Use Zaraz proxy instead of SRI |
| CF JS/CSS minification | Modifies bytes | Disable for SRI-protected assets |

```html
<!-- Opt out of Rocket Loader for a specific script -->
<script data-cfasync="false"
        src="https://cdn.example.com/lib@2.1.0/dist/lib.min.js"
        integrity="sha384-..."
        crossorigin="anonymous"></script>
```

SRI hashes must match the **exact bytes served**. Any in-flight
modification produces a hash mismatch and blocks the resource.

## What SRI cannot protect against

1. **A malicious version was pinned at origin.** If the originally
   pinned version was already compromised, SRI faithfully executes it.
   Pinning must follow a review of what is being pinned.
2. **Runtime-injected scripts.** Scripts inserted by other scripts,
   JSONP loaders, and `eval()` bypass SRI entirely.
3. **Post-execution behaviour.** Once a script passes the hash check,
   it runs with full page authority. Pair SRI with CSP `sandbox` and
   permissions policies to limit blast radius.
4. **Always-latest CDN URLs.** A URL like
   `https://cdn.example.com/lib/latest/lib.min.js` cannot be SRI
   protected — bytes change on every release. Always use immutable
   versioned URLs.

## Anti-patterns

- `crossorigin` without `integrity` — CORS requests without a hash.
- `integrity` without `crossorigin` on cross-origin resources — the
  attribute is silently ignored.
- Hand-copying SRI hashes into source — they go stale silently.
- Adding `integrity` to dynamically created script elements — browsers
  do not enforce SRI on `document.createElement("script")`.
- Using `sha256` for new implementations — prefer `sha384` or above.

## Gotchas

- **CORS must be configured on the CDN.** Verify `curl -I` shows
  `Access-Control-Allow-Origin` before deploying SRI.
- **CDN cache vs origin bytes.** Purge the Cloudflare cache when a
  CDN asset version changes; a stale cached response can have
  different bytes than the freshly hashed version.
- **CSP `strict-dynamic` interaction.** Scripts loaded by a
  trusted script do not carry `integrity`; test CSP and SRI together.
- **Multiple algorithms.** A browser skipping an unknown algorithm
  falls back to the next; ensure at least one listed algorithm is
  universally supported (sha384 is).

## Verification

- `curl -sI https://cdn.example.com/lib@2.1.0/dist/lib.min.js` shows
  `Access-Control-Allow-Origin: *`.
- Browser DevTools Network tab shows the script loaded with status 200
  and no integrity error in the console.
- Manually corrupt the hash in a test build; confirm the browser
  blocks execution and logs an integrity failure.
- CI artifact hash matches local `openssl dgst -sha384` computation.
- All SRI-protected `<script>` tags include `data-cfasync="false"`.

## Related

- `security/subresource-integrity-sri.md`
- `security/content-security-policy-workers-pages.md`
- `security/supply-chain-npm-security.md`
- `security/dependency-supply-chain-security-npm.md`
- `cloudflare/pages-headers-configuration.md`

## Source URLs (verified 2026-08-17)

- https://developer.mozilla.org/en-US/docs/Web/Security/Subresource_Integrity
- https://www.w3.org/TR/SRI/
- https://developers.cloudflare.com/speed/optimization/content/rocket-loader/
- https://developers.cloudflare.com/zaraz/
- https://cheatsheetseries.owasp.org/cheatsheets/Third_Party_Javascript_Management_Cheat_Sheet.html
