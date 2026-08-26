# Rocket Loader and Mirage: Mobile-Only Breakage from Edge Rewriting

**Date:** 2026-08-17
**Author:** the platform team
**Status:** published

## Symptom

Images render as gray placeholders or never upgrade past a
low-resolution blur — but only on mobile devices; desktop is fine.
Or: interactive JS (menus, hydration, wallet connect buttons) works
on desktop but is dead or races on mobile, with console errors about
scripts executing out of order. Nothing in the app changed; the
irregularity maps exactly to Cloudflare zone settings that rewrite
HTML at the edge — Mirage (mobile-targeted image proxying) and
Rocket Loader (async script rewriting).

## Context

Both features modify the origin's HTML in-flight, so the page that
mobile users execute is not the page you shipped or tested. Mirage
specifically targeted slow mobile connections: it replaced `<img>`
tags with low-res placeholders upgraded client-side by
`mirage2.min.js`. Rocket Loader rewrites `<script>` tags to
`type="…-text/javascript"` and re-executes them through its own
loader, changing execution timing and ordering.

**Mirage was deprecated by Cloudflare effective September 15,
2025** — the toggle is gone from new configurations and the docs
page is marked deprecated. Zones that still carry the setting via
API state should treat it as dead code. Before deprecation, Mirage
2.0 was documented in the field breaking images on essentially all
mobile devices for some sites (served the placeholder, never
upgraded) — a pure mobile/desktop disproportion because desktop
UAs were not targeted.

example project relevance: a Next.js static export already ships optimized,
hashed, fingerprinted assets and hydration-ordered scripts. Any
edge HTML rewriting is pure risk with no upside — modern bundlers
make Rocket Loader redundant, and its rewriting can break
hydration order, CSP nonces, and Solana wallet-adapter injection
timing.

## What each feature did / does

```
Feature        Target          Mechanism                    Status
──────────────────────────────────────────────────────────────────
Mirage         Mobile UAs on   <img> → placeholder +        Deprecated
               slow / HTTP/1   mirage2.min.js client        2025-09-15
               connections     upgrade
Rocket Loader  All UAs, but    <script> rewritten to        Still
               timing bugs     deferred custom loader;      available;
               surface worst   executes after paint         off by
               on slow mobile                               default
Auto Minify    HTML/CSS/JS     minification at edge         Removed
                                                            2024-08
```

Slow mobile CPUs and networks make Rocket Loader's reordering
*visible*: races that resolve harmlessly in 5ms on desktop take
300ms on a mid-range Android, so listeners attach after user
interaction, and "works on my machine (desktop)" bugs ship.

## Diagnosis

```
1. Fetch the page as a mobile UA THROUGH Cloudflare and diff
   against the origin/Pages direct output:
     curl -s https://app.example.com/ -A "<mobile UA>" \
       | grep -oE 'rocket-loader|mirage|data-cfasync|cdn-cgi'

   Markers of edge rewriting:
     /cdn-cgi/scripts/…/rocket-loader.min.js
     type="xxxxx-text/javascript"   (Rocket Loader)
     mirage2.min.js, data-cfsrc     (Mirage, legacy)

2. Toggle test: disable the feature (or bypass with a
   "Configuration Rule → Rocket Loader: off" on one path),
   retest on a real mobile device — not an emulated viewport,
   since targeting was UA + connection based.

3. Check API state for zombie settings on old zones:
     GET /zones/:id/settings/mirage
     GET /zones/:id/settings/rocket_loader
```

## Correct configuration for an SPA / static export

```
Speed → Optimization:
  Rocket Loader: OFF   (bundler already code-splits and defers)
  Mirage:        gone  (deprecated; ensure API value is "off"
                        on zones created before 2025)

If Rocket Loader must stay on for a legacy marketing zone,
exempt individual scripts:
  <script data-cfasync="false" ></script>

CSP note: Rocket Loader injects its own inline/loader script —
strict CSP with nonces breaks it (or it breaks CSP). Pick one.
```

## Anti-patterns

- **Enabling every Speed toggle on a modern framework app** —
  Rocket Loader predates ES modules, HTTP/2+, and framework
  hydration; on a Next.js export it can only reorder what the
  framework already ordered correctly.
- **Debugging mobile-only JS/image bugs in the app repo first** —
  when desktop is fine and mobile is broken across unrelated
  releases, check edge rewriting features before bisecting app
  code.
- **Testing "mobile" via desktop DevTools emulation only** —
  Mirage-class features keyed on UA and connection type; emulated
  viewports with desktop UA never reproduced the mobile-only path.
- **Leaving deprecated features' API state unaudited** — settings
  removed from the dashboard can persist in zone state; terraform
  or API audits should assert them off.

## Gotchas

- **`data-cfasync="false"` must appear before the script is
  rewritten** — it exempts a script from Rocket Loader, but only
  works on same-origin HTML that Cloudflare proxies; injected
  scripts added at runtime are not rewritten anyway.
- **Rocket Loader + wallet extensions** — crypto wallet content
  scripts expect provider injection before dapp scripts run;
  deferring dapp bundles behind Rocket Loader flips the race the
  other way on slow devices.
- **Mirage's placeholder bug hit `srcset` responsive images
  hardest** — sites using proper responsive images saw them
  downgraded to Mirage's pipeline on mobile; the fix at the time
  was disabling Mirage, which is now the permanent state.
- **A/B irregularity between colos during rollouts** — edge
  features deploy progressively; "sometimes broken on mobile"
  during a feature rollout window can be colo-dependent, which
  looks like user error until correlated with `cf-ray`.

## Verification

- Zone API reports `rocket_loader: off` and (legacy zones)
  `mirage: off`.
- Proxied mobile-UA HTML is byte-identical to Pages/origin output
  (no `/cdn-cgi/` script injection besides email obfuscation if
  intentionally enabled).
- Real-device mobile smoke test passes for hydration-dependent
  flows (age gate, login, wallet connect).
- CSP report endpoint shows no violations from `cdn-cgi` loader
  scripts.

## Related

- `documentation/categories/cloudflare/cache-device-type-segmentation-mobile-desktop.md`
- `documentation/categories/cloudflare/images-best-practices.md`
- `documentation/categories/frontend/html-srcset-responsive-images.md`
- `documentation/categories/security/csp-nonce-hash-strategies.md`

## Source URLs (verified 2026-08-17)

- Mirage deprecation notice (effective 2025-09-15) — https://community.cloudflare.com/t/deprecation-notice-mirage-effective-september-15-2025/824602
- Cloudflare Mirage (deprecated) docs — https://developers.cloudflare.com/speed/optimization/images/mirage/
- Field report: Mirage 2.0 breaking images on all mobile devices — https://nooshu.com/blog/2025/01/07/cloudflares-mirage-2-0-broke-my-images-on-all-mobile-devices/
- Community: Mirage & Rocket Loader performance issues — https://community.cloudflare.com/t/mirage-rocketloader-performance-issues/415884
