# email-responsive-design

**Issue:** Building email templates that adapt to mobile and desktop screen sizes
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Over 60% of emails are opened on mobile; templates must be readable without zooming or horizontal scrolling.

## Pattern / Solution
1. Use fluid/hybrid layouts: `width: 100%; max-width: 600px` on outer container.
2. Use table-based layouts for Outlook compatibility:
```html
<table width="100%" cellpadding="0" cellspacing="0"><tr><td align="center">
  <table width="600" style="max-width:600px;width:100%">...</table>
</td></tr></table>
```
3. Apply media queries for mobile breakpoints:
```css
@media (max-width: 600px) {
  .full-width { width: 100% !important; }
  .hide-mobile { display: none !important; }
}
```
4. Use `font-size` minimum 14px body, 22px headings on mobile.
5. CTA buttons minimum 44x44px touch target.

## Gotchas
- Outlook ignores `max-width`; set explicit `width` on tables for Outlook and override with `max-width` via CSS.
- `display: none` on mobile hiding requires `!important` due to inline style precedence.
- Images must have `width="100%"` attribute and `max-width:100%;` inline style.

## Related
- email-html-rendering-clients, email-css-support-table, email-dark-mode-support, mjml-template-framework
