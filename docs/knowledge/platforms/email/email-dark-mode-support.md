# email-dark-mode-support

**Issue:** Making email templates render correctly in dark mode
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Dark mode is enabled by ~35% of email users; poorly designed emails appear broken with white blocks on dark backgrounds.

## Pattern / Solution
1. Use `prefers-color-scheme` media query:
```css
@media (prefers-color-scheme: dark) {
  body, .wrapper { background-color: #1a1a1a !important; }
  .content { background-color: #2d2d2d !important; }
  p, td { color: #e0e0e0 !important; }
}
```
2. Use `[data-ogsc]` selectors for Outlook.com dark mode:
```css
[data-ogsc] .content { background-color: #2d2d2d !important; }
```
3. SVG logos: use `fill="currentColor"` or provide separate dark-mode logo via `<picture>` with media query.
4. Avoid hardcoded `#ffffff` text on colored backgrounds; use high-contrast color pairs.
5. Test dark mode in Apple Mail, Gmail app, and Outlook.com.

## Gotchas
- Outlook 2019 (Windows) does not support dark mode media queries; use `mso-` conditional comments.
- Gmail's dark mode auto-inverts some colors; add `color-scheme: light dark` meta tag to signal support.
- Background images may not invert; always pair with a dark background color fallback.

## Related
- email-html-rendering-clients, email-css-support-table, email-responsive-design
