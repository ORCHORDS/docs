# CSS Mobile Viewport Units: dvh, svh, lvh and the 100vh Problem

**Date:** 2026-08-17
**Author:** the platform team
**Status:** published

## Symptom

A full-screen modal, fixed navbar, or hero section that fills the
entire screen perfectly on desktop is clipped on mobile — the
bottom edge hides behind the browser address bar, or a scrollbar
appears where none should exist. Rotating the device or scrolling
until the address bar retracts makes the problem disappear, then
return. The example project age-verification modal, the feed background,
and the story-viewer overlay all exhibit this on iOS Safari and
Chrome Android; desktop is unaffected.

## Context

`100vh` on mobile browsers does not mean "the visible height right
now." Browsers historically froze `vh` at the *large* viewport
(address bar fully hidden) so that page layouts did not reflow
every time the user scrolled and the browser chrome moved. The
result is that `100vh` on an iPhone with the address bar visible
is taller than the visible screen — content is painted behind the
browser UI. The CSS Working Group introduced three stable, explicit
variants in 2022–2023 that ship across all modern browsers as of
mid-2023: `svh`, `dvh`, and `lvh`. They are the correct, permanent
fix — no JavaScript required.

## What the three units mean

```
Unit   Name                    Resolves to
───────────────────────────────────────────────────────────────────
svh    Small Viewport Height   Viewport with browser chrome SHOWN
                               (address bar visible, toolbar up)
                               Smallest stable value — never clips

lvh    Large Viewport Height   Viewport with browser chrome HIDDEN
                               (address bar scrolled away)
                               Same as classic 100vh behaviour

dvh    Dynamic Viewport Height Live value — recalculates as the
                               browser chrome shows or hides during
                               scroll; can trigger layout reflow
───────────────────────────────────────────────────────────────────
Mnemonic: small = safe, large = legacy, dynamic = live
```

`100vh` is frozen at `100lvh` on most mobile browsers. This is
why it lies — it reports the maximum possible height, not the
currently visible one.

## Browser support

```
Browser                 svh / dvh / lvh    Notes
───────────────────────────────────────────────────────────────────
Chrome / Edge           108+  (2022-12)    Full support, stable
Firefox                 101+  (2022-05)    Full support, stable
Safari (iOS + macOS)    15.4+ (2022-03)   All iOS browsers inherit
                                           WebKit — consistent
Samsung Internet        21+   (2023-04)   Full support
Opera                   94+   (2022-12)   Full support

Global coverage: >92% as of mid-2026 (caniuse viewport-unit-variants)

Unsupported browsers (old Safari 14, IE) silently drop a
declaration they don't recognise — always write a vh fallback
on the line above:

  height: 100vh;   /* fallback */
  height: 100svh;  /* preferred */
```

## When to use each unit

```
Use case                                 Unit    Reason
───────────────────────────────────────────────────────────────────
Age-verification modal (example project)        svh     Fixed overlay;
Fixed full-screen overlays / dialogs             must not clip
Story-viewer overlay (example project)          svh     Same — stable

Feed/app shell background (example project)     dvh     Immersive; grows
Immersive scroll hero sections                   as bar retracts
                                                 Accept reflow cost

Off-screen panel sizing / max heights    lvh     Element must not
Anything that must fill the full                 shrink when bar
visible space when bar is fully gone             is showing
───────────────────────────────────────────────────────────────────
Rule of thumb:
  Fixed/absolute overlays → svh (stable, no reflow)
  Scroll-driven immersive content → dvh (live, accepts reflow)
  Intentionally full-bleed as bar retracts → lvh (matches vh)
```

## env(safe-area-inset-*) — notch and home indicator

Notched iPhones and Android devices with a gesture home indicator
add a second layer of obstruction *inside* the safe viewport. The
`env()` variables give those inset values in CSS. They require
`viewport-fit=cover` in the meta tag to opt into the full screen.

```html
<!-- _document.tsx / next.config.js viewport meta -->
<meta
  name="viewport"
  content="width=device-width, initial-scale=1,
           viewport-fit=cover"
/>
```

```css
/* Bottom sheet, sticky nav, or modal footer */
.modal-footer {
  padding-bottom: calc(1rem + env(safe-area-inset-bottom, 0px));
}

/* Fixed bottom bar */
.bottom-nav {
  bottom: env(safe-area-inset-bottom, 0px);
}
```

`safe-area-inset-bottom` is the home indicator clearance on iPhone
(typically 34 px on iPhone X+, 0 on older flat-bottom phones).
`safe-area-inset-top` covers the Dynamic Island / notch. Both
return `0px` on rectangular viewports — the fallback is defensive,
not required. Browser support: Baseline widely available since 2020.

## CSS custom property pattern (DRY)

Define once in `:root`; consume everywhere. This avoids repeating
the `vh` fallback + `svh`/`dvh` stack at every callsite.

```css
:root {
  /* stable full-height — fixed overlays and modals */
  --h-screen: 100svh;

  /* dynamic full-height — immersive scroll layouts */
  --h-screen-dynamic: 100dvh;

  /* notch / home indicator clearance */
  --safe-bottom: env(safe-area-inset-bottom, 0px);
  --safe-top:    env(safe-area-inset-top,    0px);
}

/* Single fallback written once, at the token definition */
@supports not (height: 1svh) {
  :root {
    --h-screen:         100vh;
    --h-screen-dynamic: 100vh;
  }
}

/* Consumers reference the token, never the raw unit */
.modal-overlay  { height: var(--h-screen); }
.feed-bg        { min-height: var(--h-screen-dynamic); }
.story-viewer   { height: var(--h-screen); }
```

## Tailwind integration (v3.4+)

Tailwind v3.4 (released December 2023) ships `h-svh`, `h-dvh`,
`h-lvh`, and the corresponding `min-h-*` / `max-h-*` variants
out of the box. No config needed.

```
Class       CSS output              Use in example project
────────────────────────────────────────────────────────────────
h-svh       height: 100svh          Age-gate modal, story viewer
h-dvh       height: 100dvh          Feed shell, immersive hero
h-lvh       height: 100lvh          Rarely needed; mirrors vh
min-h-svh   min-height: 100svh      App shell wrapper
min-h-dvh   min-height: 100dvh      Scroll containers
```

```jsx
{/* Age-verification modal — fixed overlay */}
<div className="fixed inset-0 h-svh bg-black/80 z-50">
  …
</div>

{/* Story viewer — full-screen, stable */}
<div className="h-svh w-full overflow-hidden">
  …
</div>

{/* Feed background — grows as bar retracts */}
<main className="min-h-dvh">
  …
</main>
```

Arbitrary values work as expected: `h-[85dvh]`, `max-h-[90svh]`.

## overscroll-behavior — stop rubber-banding behind overlays

On iOS, unconstrained scroll containers inside a full-screen modal
propagate to the document and cause the browser chrome to rubber-
band through the overlay. Fix with `overscroll-behavior: contain`.

```css
.modal-scroll-body {
  overflow-y: auto;
  overscroll-behavior-y: contain; /* stop bounce bleeding out */
  -webkit-overflow-scrolling: touch;
}
```

In Tailwind: `overscroll-y-contain` class.

## Anti-patterns

- **`height: 100vh` on fixed overlays** — clips content behind the
  address bar on iOS Safari and Chrome Android. Replace with
  `100svh` or `var(--h-screen)`.
- **`height: 100dvh` on fixed position elements** — `dvh` reflows
  as the address bar moves; a fixed overlay that resizes mid-scroll
  creates visual jitter. Use `svh` for anything `position: fixed`.
- **Hardcoding notch clearance in pixels** — `padding-top: 44px`
  for the Dynamic Island breaks on older iPhones, iPads, and
  Android. Always use `env(safe-area-inset-top, 0px)`.
- **Omitting the `vh` fallback** — browsers that don't support
  `svh` silently discard the declaration, leaving no height at all.
  Write `100vh` on the line above as a fallback.
- **Setting `viewport-fit=cover` then ignoring safe-area insets** —
  opting in exposes content to the notch; failing to add inset
  padding then clips interactive elements.

## Gotchas

- **`dvh` triggers layout reflow on every address bar frame** —
  this is intentional and cheap for simple layouts (height only),
  but avoid using `dvh` on elements with expensive paint (large
  box-shadows, complex gradients) or you will see jank on lower-
  end Android devices.
- **iOS 15 and 15.3 had dvh bugs** — the dynamic value did not
  always update smoothly during the bar animation. Both are below
  1% marketshare as of 2026 and the `svh` fallback is unaffected.
- **In-app browsers (Instagram, TikTok) on iOS** — WebView-hosted
  pages in social app browsers may suppress the address bar
  entirely, making `svh` and `dvh` equal to `lvh`. This is usually
  fine — fullscreen remains correct — but test on example project's top
  referral surfaces (Instagram and TikTok in-app).
- **`min-height` vs `height`** — a `height: 100svh` on a flex
  container that has taller children will overflow; prefer
  `min-height: 100svh` for containers that must grow.
- **`@supports` guard for `svh`** — use `@supports (height: 1svh)`
  rather than checking the unit in JS; feature detection in CSS is
  more reliable and has no flash.

## Verification

- `height: 100vh` replaced with `100svh` on the age-verification
  modal, story-viewer overlay, and any `position: fixed` full-
  height element.
- `min-height: 100dvh` used for the feed shell and scroll-driven
  sections (not `position: fixed`).
- `viewport-fit=cover` set in the Next.js metadata viewport config.
- `env(safe-area-inset-bottom)` applied to the bottom nav and any
  sticky footer / sheet.
- `overscroll-behavior-y: contain` set on scrollable modal bodies.
- `vh` fallback line present above every `svh`/`dvh` declaration
  (or handled via CSS custom property `@supports` block).
- Tested on physical iOS Safari (address bar visible) and Chrome
  Android; not only desktop or emulator.

## Related

- `documentation/categories/frontend/virtual-keyboard-viewport-handling.md`
- `documentation/categories/frontend/tailwind-responsive-design.md`
- `documentation/categories/mobile/mobile-keyboard-safe-area-handling.md`
- `documentation/categories/frontend/css-custom-properties-theming.md`

## Source URLs (verified 2026-08-17)

- New Viewport Units (Ahmad Shadeed) —
  https://ishadeed.com/article/new-viewport-units/
- Tailwind CSS v3.4 release notes —
  https://tailwindcss.com/blog/tailwindcss-v3-4
- Can I use — Small, Large, and Dynamic viewport units —
  https://caniuse.com/viewport-unit-variants
- MDN — env() / safe-area-inset-* —
  https://developer.mozilla.org/en-US/docs/Web/CSS/env
- CSS dvh, svh and lvh cross-browser guide (Zenn / tonkotsuboy) —
  https://zenn.dev/tonkotsuboy_com/articles/svh-dvh-lvh-for-all-browser
