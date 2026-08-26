# Mobile Viewport Units (dvh/svh/lvh) in PWAs on Cloudflare Pages

**Date:** 2026-08-22
**Author:** example.com
**Status:** published

## Symptom

example project full-screen panels — the age-verification gate,
the story viewer, and the feed background — are visually
clipped on mobile. On iOS Safari, the bottom ~80 px of the
modal disappears behind the address bar and the home
indicator. On Android Chrome the behaviour is slightly
different: the modal initially fits, then jumps to a taller
size as the user scrolls and the address bar retracts.
Desktop is unaffected. The issue is absent in development
(localhost) but visible on the Cloudflare Pages deployment
URL and on the production domain.

## Context

Cloudflare Pages is a pure static host — it applies no
server-side viewport transformations. The issue is 100%
CSS-side, but the Cloudflare Pages context matters because:

1. The example project app is deployed as a Next.js static export
   (`output: 'export'`). There is no server to inject
   per-request styles or scripts.
2. The deployed PWA is often added to the iOS Home Screen
   (A2HS) and launched in standalone mode, which has
   different viewport and browser-chrome behaviour from
   regular Safari.
3. The `viewport` meta tag is set once at build time in
   the Next.js metadata config; it cannot vary per device
   at runtime.

This article extends `css-mobile-viewport-units-dvh-svh.md`
with Cloudflare Pages-specific deployment notes and the
behaviour difference between PWA standalone mode and browser
mode.

## The three viewport unit variants — quick reference

```
Unit    Name                  Value when visible    Value when bar hidden
─────────────────────────────────────────────────────────────────────────
svh     Small Viewport        Smallest visible      Same (bar hidden =
        Height                height (bar shown)    slightly taller but
                                                    svh does not grow)

dvh     Dynamic Viewport      Updates live as       Grows to lvh when
        Height                bar moves             bar fully retracts

lvh     Large Viewport        Full height with      Same
        Height                bar fully retracted
                              (= classic 100vh)

100vh   (legacy)              Frozen at lvh value   Same as lvh
─────────────────────────────────────────────────────────────────────────
svh = safe, static, never clips
dvh = live, causes reflow on scroll, grows smoothly
lvh = legacy alias, same as old 100vh behaviour
```

## iOS Safari vs Android Chrome differences

```
Behaviour                     iOS Safari          Android Chrome
──────────────────────────────────────────────────────────────────
Address bar position          Bottom of screen    Top of screen
                              (URL bar at bottom  (URL bar at top,
                              on iPhone; top on   slides up on scroll)
                              iPad)

Address bar retraction        Scrolling down      Scrolling down
                              retracts bar;       retracts bar;
                              any scroll up       any scroll up
                              shows it again      may keep it hidden

dvh reflow frequency          High — triggers     Moderate — bar moves
                              on every frame of   in discrete steps
                              bar animation

svh value                     Shortest possible   Shortest possible
  (with bar visible)          screen height —     screen height —
                              smallest on older   typically ~56px
                              iPhones with thick  less than lvh on
                              bottom toolbar      Chrome Mobile

Home indicator clearance      34 px bottom on     Not applicable —
  (notch / home bar)          iPhone X+;          Android uses gesture
                              env(safe-area-       navigation bar or
                              inset-bottom)        3-button nav bar,
                                                   different from iOS

PWA standalone mode           Hides Safari UI     Hides Chrome toolbar
  (added to home screen)      entirely — no bar   and nav bar; dvh
                              animation, no svh   == lvh in standalone
                              vs dvh difference;
                              svh == lvh
──────────────────────────────────────────────────────────────────
```

The PWA standalone mode row is critical for example project:
when the app is installed on iOS, the address bar is gone
and `svh === lvh === dvh`. This means the svh-vs-dvh choice
matters only in the browser tab context, not in standalone.

## Layout shift on scroll caused by dvh

On Android Chrome, using `height: 100dvh` on a container
with visible background or content causes the entire element
to visually resize as the address bar slides away. This is
not a bug — it is the intended behaviour of `dvh` — but it
reads as layout shift (and does register as CLS in Web
Vitals if the element is within the first 500 ms of load).

```
Scenario                              Use         Reason
──────────────────────────────────────────────────────────
Fixed overlay (age-gate modal)        svh         Must not move
Story viewer (fixed position)         svh         Must not resize
Feed background scroll container      dvh         OK to grow with bar
App shell wrapper (no children move)  min-h-dvh   Shell grows, CLS=0
                                                  if children are
                                                  absolutely positioned
Sticky header inside scroll           svh for     Header must not
  container                           max-height  reflow — use svh
                                      constraints
```

## Next.js viewport meta on Cloudflare Pages

Set the viewport meta in the Next.js App Router metadata
config. This is baked into `index.html` at build time by
the static export and served verbatim from Cloudflare Pages.

```tsx
// src/app/layout.tsx
import type { Metadata, Viewport } from 'next';

export const viewport: Viewport = {
  // viewport-fit=cover is required to access
  // env(safe-area-inset-*) for notch clearance.
  // Without it, safe-area-inset-bottom is always 0.
  viewportFit: 'cover',
  width: 'device-width',
  initialScale: 1,
  // Do not set maximumScale < 1 — it disables user zoom,
  // which breaks accessibility (WCAG 1.4.4).
};
```

This outputs:
```html
<meta name="viewport"
  content="width=device-width, initial-scale=1,
           viewport-fit=cover" />
```

## CSS token pattern for Cloudflare Pages deployment

Since Cloudflare Pages serves `index.html` from cache and
there is no server-side injection, all viewport token
definitions live in a global CSS file included in the
Next.js `_app` or root `layout.tsx`.

```css
/* styles/globals.css */

:root {
  /* Stable height — address bar always considered visible.
     Use for anything position: fixed or position: absolute
     overlays. Never causes layout shift. */
  --screen-h: 100svh;

  /* Dynamic height — grows as address bar retracts.
     Use for scroll-driven immersive layouts.
     Causes reflow; avoid on painted backgrounds. */
  --screen-h-dynamic: 100dvh;

  /* Safe-area insets for notch / home indicator */
  --safe-top:    env(safe-area-inset-top,    0px);
  --safe-bottom: env(safe-area-inset-bottom, 0px);
  --safe-left:   env(safe-area-inset-left,   0px);
  --safe-right:  env(safe-area-inset-right,  0px);
}

/* Fallback for browsers without svh/dvh (< 1% global) */
@supports not (height: 1svh) {
  :root {
    --screen-h:         100vh;
    --screen-h-dynamic: 100vh;
  }
}
```

## PWA standalone mode on iOS: special considerations

When example project is added to the iOS Home Screen and launched
in standalone mode:

- `window.navigator.standalone === true` (Safari only)
- The address bar is completely absent
- `svh`, `dvh`, and `lvh` all resolve to the same value
- `env(safe-area-inset-top)` equals the status bar height
  (~47 px on iPhones with Dynamic Island, ~44 px on Face
  ID iPhones, ~20 px on older ones)
- `env(safe-area-inset-bottom)` equals the home indicator
  clearance (~34 px on Face ID, ~0 on older flat-bottom)

```tsx
// Detect standalone mode to adjust layout if needed
function useIsStandalone() {
  const [standalone, setStandalone] = React.useState(false);
  React.useEffect(() => {
    setStandalone(
      window.matchMedia('(display-mode: standalone)').matches ||
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      (window.navigator as any).standalone === true
    );
  }, []);
  return standalone;
}
```

In standalone mode, apply `padding-top: env(safe-area-inset-top)`
to the app shell or the top navigation bar so content is
not hidden behind the status bar (which is still visible but
not part of the browser chrome).

## Anti-patterns

- **`height: 100vh` on position:fixed overlays** — clips
  content behind the iOS address bar or home indicator.
  Replace with `var(--screen-h)` (100svh) everywhere.
- **`height: 100dvh` on position:fixed elements** — the
  element resizes on every frame of the address bar
  animation. On a fixed overlay this creates visible jitter.
  Use `svh` for anything `position: fixed`.
- **Ignoring safe-area insets after adding
  `viewport-fit=cover`** — opting in to the full screen
  exposes the notch area. Any interactive element in the top
  or bottom 34–47 px of the screen must have padding to
  clear the system UI.
- **Setting `maximum-scale=1` in the viewport meta** —
  disables user pinch-zoom, violating WCAG 1.4.4. Do not
  do this to "fix" viewport issues.
- **Hardcoding pixel offsets for notch clearance** —
  `padding-top: 44px` is fragile across device generations.
  Always use `env(safe-area-inset-top, 0px)`.

## Gotchas

- **Cloudflare Pages serves `index.html` with
  `Cache-Control: no-cache` by default** — the viewport
  meta is re-read on every navigation. If you change the
  viewport meta, users get it on next hard load. No CDN
  cache purge needed for the meta tag itself.
- **`dvh` and CLS** — Cumulative Layout Shift is measured
  during the first 500 ms after the document loads. If a
  `dvh`-sized element shifts during that window (address bar
  retracts during page load on Android), it registers as CLS.
  Prefer `svh` for above-the-fold elements to protect your
  Core Web Vitals score.
- **In-app browsers on iOS (Instagram, TikTok)** — social
  app WebViews typically hide the address bar permanently;
  `svh`, `dvh`, and `lvh` are all equal to the WebView
  height. Test the example project share sheet link in Instagram
  and TikTok in-app browsers explicitly.
- **iOS 15.0–15.3 had broken `dvh` updates** — the dynamic
  value did not animate smoothly on those OS versions.
  Market share is below 0.5% as of 2026; `svh` is unaffected.

## Verification

- The age-verification modal and story viewer are not
  clipped on an iPhone with iOS Safari address bar visible.
- Scrolling the feed on Android Chrome does not cause the
  background to visibly jump or resize (use svh for fixed
  backgrounds, dvh only for scroll container min-height).
- `env(safe-area-inset-bottom)` is non-zero (34 px) when
  tested on a Face ID iPhone in Safari with
  `viewport-fit=cover` set.
- The app shell has `padding-top: env(safe-area-inset-top)`
  applied when running in iOS standalone mode.
- CLS score in Lighthouse mobile audit is 0 or < 0.05.

## Related

- `documentation/categories/frontend/css-mobile-viewport-units-dvh-svh.md`
- `documentation/categories/frontend/nextjs-static-export-cloudflare-pages-routing.md`
- `documentation/categories/frontend/virtual-keyboard-viewport-handling.md`
- `documentation/categories/mobile/mobile-keyboard-safe-area-handling.md`
- `documentation/categories/frontend/pwa-manifest-config.md`

## Source URLs (verified 2026-08-22)

- New Viewport Units — Ahmad Shadeed —
  https://ishadeed.com/article/new-viewport-units/
- MDN — env() —
  https://developer.mozilla.org/en-US/docs/Web/CSS/env
- Next.js — Metadata viewport —
  https://nextjs.org/docs/app/api-reference/functions/generate-viewport
- web.dev — Cumulative Layout Shift —
  https://web.dev/articles/cls
- Apple — Configuring a Web Application (standalone meta) —
  https://developer.apple.com/library/archive/documentation/AppleApplications/Reference/SafariWebContent/ConfiguringWebApplications/ConfiguringWebApplications.html
