# subresource-integrity-sri

**Issue:** Sites routinely load JavaScript, fonts, and CSS from third-party CDNs — analytics, widget libraries, jQuery from jsDelivr, and so on. Each third-party origin is a supply-chain dependency: if the CDN, the package publisher, or an upstream account is compromised, the attacker's script executes with full page authority, able to steal credentials, session tokens, and payment data. Subresource Integrity (SRI) pins an explicit cryptographic hash of the expected resource in the integrity attribute of script and link tags, so the browser refuses to execute anything whose bytes do not match. SRI is cheap, standardized, and browser-enforced, yet adoption remains spotty because it interacts awkwardly with bundlers, dynamic imports, and evergreen CDN URLs. As of 2025-2026 the tooling story has matured on the Webpack/Rspack side while Vite still lacks first-class support, making build integration the main engineering decision.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## The Problem: Third-Party Script Risk

1. **A CDN compromise is page compromise.** A script tag grants the loaded code the page's origin, DOM access, cookies, and keystrokes — there is no sandbox. Supply-chain incidents in npm publishing and CDN accounts have demonstrated the entire class of risk.
2. **Version drift breaks hashes silently.** Referencing latest or floating CDN versions defeats SRI outright because the bytes change out from under the hash; SRI is only meaningful with exact, immutable versions.
3. **Same compromise, cached longer.** CDN caching that makes third-party scripts fast also extends the lifetime of a malicious build; SRI caps the blast radius at zero execution regardless of how widely the bad asset propagated.
4. **Compliance pressure.** PCI DSS 6.4.3 and 6.4.3-adjacent requirements for inventorying and justifying client-side scripts make SRI a natural control to evidence that the executed script set is pinned.

## How SRI Works

1. **The integrity attribute.** A script or link element carries integrity="sha384-base64hash"; the browser fetches the resource, hashes the exact bytes, and executes it only on a match, failing hard otherwise.
2. **Cross-origin requires crossorigin.** For cross-origin resources SRI only applies when the request is made in CORS mode, so the element must also set crossorigin="anonymous" and the CDN must send the matching CORS headers — a missing crossorigin attribute is the number-one integration bug.
3. **Hash on the exact served bytes.** The hash must be computed over the precise byte stream the client receives; any server-side transformation (minification, charset re-encoding, injected headers like Cloudflare features) invalidates the hash, so pin transformations off for SRI-protected paths.
4. **Multiple hash algorithms allowed.** The attribute accepts several hash types separated by spaces, enabling algorithm migration without a flag day.
5. **Failure is silent-ish.** Mismatched resources are blocked, but the page may simply break; pair SRI with CSP report-uri / report-to collection to learn when a third party republishes bytes and starts breaking your site.

## Bundler and Build Integration

1. **Webpack: webpack-subresource-integrity.** The established plugin computes hashes for emitted assets at build time and injects integrity plus crossorigin on generated script and link tags, including dynamically imported chunks loaded by Webpack's runtime.
2. **Rspack: built-in SubresourceIntegrityPlugin.** Rspack ships first-class SRI support that automatically sets integrity and crossorigin for generated chunk-loading tags, covering lazy-loaded routes without extra wiring.
3. **Vite: still plugin territory.** Vite has no native SRI support (open feature request vitejs/vite#19367); community plugins such as @small-tech/vite-plugin-sri cover entry assets, and teams should verify dynamic import chains are hashed rather than assuming.
4. **Generate hashes in CI, never by hand.** Hash computation belongs in the build pipeline so hashes cannot drift from artifacts; a hand-copied hash is a future outage or, worse, a removed hash after one incident.
5. **Vendor third-party scripts when SRI is impossible.** When a third party refuses CORS or pins (some tag managers, A/B tools), self-host the script on your own origin and hash it — trading auto-updates for integrity, which is usually the right trade.

## Limitations and Gaps

1. **No coverage for dynamic runtime injection.** Scripts inserted by other scripts, JSONP-style loaders, or eval-based loaders bypass the attribute entirely; SRI protects declared static references, not the whole execution graph.
2. **Interplay with CSP strict-dynamic.** strict-dynamic propagates trust to scripts injected by already-trusted scripts, and those injected loads do not carry integrity attributes; combine SRI with CSP carefully and test the combined policy rather than each in isolation.
3. **Update workflow friction.** Legitimate upstream updates change the hash, so third-party upgrades become deliberate releases instead of silent rollouts — a feature for security, but one that must be owned by a scheduled process or the attribute gets deleted under pressure.
4. **Not a substitute for trusting the vendor.** SRI guarantees the bytes did not change since pinning; if the original pinned version was already malicious, SRI faithfully executes it. Pinning must follow a review of what is being pinned.
5. **No sub-resource scoping.** A pinned script still runs with full page authority once loaded; SRI controls which bytes run, not what those bytes may do — pair it with CSP, sandboxed iframes, and permission-restricted placements for high-risk widgets.

## Program Controls

1. **Inventory all third-party origins.** Maintain a list of every external hostname that serves executable code to pages; review it quarterly and require justification per entry, as PCI DSS expects.
2. **CI check for unprotected tags.** A lint rule or CI scan should fail any HTML that references a cross-origin script or stylesheet without both integrity and crossorigin attributes.
3. **Monitor CSP reports.** Collect integrity-failure reports and alert on them — a spike means either a broken vendor release or an active supply-chain event, and both need response within hours.
4. **Prefer same-origin bundling by default.** The lowest-risk architecture is bundling dependencies into your own hashed assets; reserve third-party CDN loading for cases where self-hosting is genuinely infeasible, and SRI those cases.
