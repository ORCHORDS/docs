# Dark Mode `prefers-color-scheme` — Mobile Browser Inconsistencies

**Date:** 2026-08-17
**Author:** the platform team
**Status:** published

## Symptom

example project pages look correct in desktop Chrome but show inverted or
washed-out colors inside iOS and Android in-app browsers (Instagram,
Twitter/X). Some Android users report a white flash before the dark
background appears. On iOS 18, users on slow connections see the
light theme for 100–300 ms before dark mode applies. Windows mobile
Chromium users see forced high-contrast colors overriding the
design palette entirely. The root cause in every case is that example project
has not declared its color-scheme intent, leaving each browser to
make its own inversion decision independently.

## Context

Mobile browsers implement dark mode through three distinct paths:

1. **`prefers-color-scheme` media query** — the W3C standard. The
   OS signals a preference; the browser exposes it to CSS and JS.
   Supported on iOS Safari 12.2+, Android Chrome, Samsung Internet.
2. **Algorithmic / force-dark inversion** — the browser or WebView
   forcibly inverts page colors when no dark stylesheet is declared.
   Dominant on Android WebView through API 32; still present in
   some in-app browser builds.
3. **iOS Smart Invert** — an Accessibility setting (not dark mode)
   that inverts all content except images. Triggered only when the
   user enables it explicitly; has no relation to `prefers-color-
   scheme`.

Cloudflare Pages delivers identical static HTML to every device.
The entire dark-mode burden falls on client-side CSS and a `<meta>`
tag in `<head>`.

## iOS Safari: auto-dark and `prefers-color-scheme`

iOS Safari does NOT algorithmically invert pages. It exposes
`prefers-color-scheme: dark` only when Dark Mode is on (Settings
→ Display & Brightness). Smart Invert is a separate path.

```
Mechanism            Trigger               Who handles it
──────────────────────────────────────────────────────────────
prefers-color-       iOS Dark Mode on      CSS @media query or
  scheme: dark                             JS matchMedia()
Smart Invert         Accessibility →       Browser: inverts all
                     Smart Invert          non-image content
Auto-Dark (iOS)      Does NOT exist —      n/a: iOS Safari never
                     no force-inversion    inverts without user
                     for unlisted pages    action
```

iOS in-app browsers (WKWebView) inherit the host app's
`prefers-color-scheme`. If example project ships only light CSS, dark-mode
users see white backgrounds in every iOS in-app browser — no
inversion fallback exists.

## Android WebView: algorithmic darkening

Apps targeting Android 13 (API 33)+ replace the deprecated
`setForceDark` with `setAlgorithmicDarkeningAllowed`. Behavior
differs across API levels:

```
API level  Method                        Page effect
──────────────────────────────────────────────────────────────
≤ API 32   setForceDark(FORCE_DARK_ON)   Inverts all colors
                                         including images;
                                         ignores CSS dark styles
≥ API 33   setAlgorithmicDarkeningAllowed Respects web-author
           (default: false)              dark CSS first; only
                                         inverts if none found
```

The web-page opt-out for both API levels: declare
`color-scheme: light dark`. WebView skips algorithmic darkening
when this is present, even if the host app has `FORCE_DARK_ON`.

## `color-scheme` meta tag and CSS property

The highest-priority single fix — one line in `<head>`:

```html
<!-- Declare dark-mode support; prevents WebView inversion
     and themes native UI controls (scrollbars, inputs)   -->
<meta name="color-scheme" content="light dark">
```

```css
/* CSS equivalent — meta tag preferred: parsed before the
   stylesheet loads on slow connections                   */
:root { color-scheme: light dark; }
```

Declaring `color-scheme: light dark` does three things:

- Android WebView skips algorithmic darkening (most important).
- Browser chrome (scrollbars, canvas background, form inputs)
  adapts to the system theme without custom CSS rules.
- iOS Safari renders native form controls in the correct scheme.

If example project drops light-mode entirely, use `color-scheme: dark` only
— this prevents the browser from ever showing light-theme native
controls even if the user switches OS themes.

## iOS Safari FOUC — dark mode fires after first paint

When dark mode is applied via JavaScript (reading `matchMedia`
then toggling `.dark` on `<html>`), the script runs after the
browser has already painted with the default light background.

```
JS class toggle (FOUC path):
  0 ms   HTML parsed, <head> processed
 30 ms   CSS loaded — paint with light background  ← white flash
 80 ms   React hydrates; matchMedia read; .dark added
 85 ms   Repaint with dark background

CSS-only @media (prefers-color-scheme: dark):
  0 ms   HTML parsed, <meta name="color-scheme"> read
 30 ms   CSS (including dark @media) loaded
 31 ms   Single correct dark paint — no flash
```

Use a synchronous inline script (see Next.js/Tailwind section)
when a user-toggle is required. Treat CSS `@media (prefers-color-
scheme: dark)` as ground truth for the initial render; the class
toggle is additive on top.

## Next.js / Tailwind: class strategy vs media strategy

```
Strategy   How it works            Mobile in-app browser
──────────────────────────────────────────────────────────────
media      Tailwind emits @media   Safe: zero JS required.
(default)  (prefers-color-         prefers-color-scheme is
           scheme: dark) rules     forwarded by all major
                                   WebViews to CSS
class      JS adds .dark to        Risky: if JS fails,
           <html> via              is blocked, or hydrates
           localStorage or         late, wrong theme shows
           matchMedia()            until React mounts
```

Recommended hybrid (user toggle + WebView-safe fallback):

```js
// tailwind.config.js
module.exports = { darkMode: 'class' };
```

```html
<!-- Synchronous in <head> before any <link rel="stylesheet"> -->
<script>
  (function () {
    var s = localStorage.getItem('example project-theme');
    var sys =
      window.matchMedia('(prefers-color-scheme: dark)').matches;
    if (s === 'dark' || (!s && sys))
      document.documentElement.classList.add('dark');
  })();
</script>
```

In-app browsers that block `localStorage` (some Twitter/X builds
on Android) fall through to the `sys` branch and read
`prefers-color-scheme` directly — no stored value needed.

## Forced colors on Windows mobile

Windows mobile devices (Surface Duo, x86 Chromium tablets) may
have Forced Colors / High Contrast mode enabled. This is
independent of `prefers-color-scheme` and overrides all custom
hex palette values.

```css
@media (forced-colors: active) {
  /* Hex values are silently ignored here.
     Use system color keywords only.       */
  .btn-primary {
    background-color: ButtonFace;
    color: ButtonText;
    border: 2px solid ButtonBorder;
  }
}
```

A user can have dark mode AND forced colors on simultaneously.
Always test both axes: forced colors wins over any dark palette.

## Anti-patterns

- **No `color-scheme` meta tag** — Android WebViews with
  `FORCE_DARK_ON` (API ≤ 32) invert image colors and produce
  garish UI on example project's media feed.
- **JS-only class toggle without an inline `<script>`** — React
  effects run after paint; a white flash is guaranteed on every
  hard reload in iOS Safari.
- **Mixing `@media (prefers-color-scheme)` CSS with Tailwind
  `darkMode: 'class'`** — Tailwind class-strategy `dark:` utilities
  are inert until `.dark` is on `<html>`. Without the inline
  script bridge, in-app browsers show partially-themed pages.
- **Hex values inside `@media (forced-colors: active)`** —
  forced-colors mode ignores all custom hex colors silently.

## Gotchas

- `color-scheme: dark` (no `light`) prevents native controls from
  rendering in light mode even after an OS switch. Match the
  declared value to your actual CSS coverage.
- Some older Instagram and Twitter/X in-app browser builds on
  Android freeze `prefers-color-scheme` to `light` regardless of
  the OS setting. The `color-scheme` meta tag suppresses inversion
  but the CSS dark path never activates in those builds.
- The `matchMedia change` event does not fire in WKWebViews unless
  the host app explicitly propagates OS theme changes.
- Cloudflare Pages delivers identical HTML to all clients — there
  is no server-side UA branch to pre-theme the response.
- `forced-colors` and `prefers-color-scheme` are orthogonal. Test
  all four combinations: light/dark × forced/not-forced.

## Verification

- `<meta name="color-scheme" content="light dark">` is in `<head>`
  before any stylesheet; confirm with View Source on production.
- Open example project in iOS Safari (Dark Mode on) on throttled slow-3G;
  no white flash on hard-reload.
- Open example project in the Twitter/X in-app browser (Android, Dark Mode
  on); no color-inversion artifacts on post images.
- Disable `localStorage` in DevTools; reload — system dark-mode
  preference still applied via the `sys` matchMedia fallback.
- Enable High Contrast on a Windows Chromium browser; example project UI
  remains legible with `forced-colors` styles active.

## Related

- `documentation/categories/frontend/tailwind-dark-mode.md`
- `documentation/categories/frontend/css-custom-properties-theming.md`
- `documentation/categories/frontend/css-mobile-viewport-units-dvh-svh.md`
- `documentation/categories/frontend/virtual-keyboard-viewport-handling.md`
- `documentation/categories/cloudflare/cloudflare-pages-static-assets.md`

## Source URLs (verified 2026-08-17)

- Android WebView dark theme guide —
  https://developer.android.com/develop/ui/views/layout/webapps/dark-theme
- Android 13 behavior changes (WebView force-dark deprecated) —
  https://developer.android.com/about/versions/13/behavior-changes-13
- Improve dark mode defaults with color-scheme (web.dev) —
  https://web.dev/articles/color-scheme
- Strange quirks of Safari's dark color scheme handling —
  https://tyhopp.com/notes/safari-dark-color-scheme-handling
- Tailwind CSS dark mode strategy docs —
  https://tailwindcss.com/docs/dark-mode
- CSS-Tricks: A Complete Guide to Dark Mode on the Web —
  https://css-tricks.com/a-complete-guide-to-dark-mode-on-the-web/
