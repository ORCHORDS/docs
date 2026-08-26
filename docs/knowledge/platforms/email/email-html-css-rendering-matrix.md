# Email HTML/CSS Rendering Matrix

**Date:** 2026-08-17
**Author:** the platform team
**Status:** published

## Symptom

Email templates look correct in a browser preview but break in
Outlook. Gmail strips styles applied via class selectors.
Dark mode inverts background colours unexpectedly. Mobile
Gmail clips long emails before the tracking pixel. The team
lacks a single reference for which CSS rules are safe to use.

## Context

Email clients render HTML through radically different engines:
Outlook 2016–2021 uses the Microsoft Word layout engine (WPF),
Gmail strips the `<head>` and all class selectors in most
contexts, Apple Mail runs WebKit, and mobile Gmail uses a
sandboxed WebView. There is no agreed rendering standard. Each
client requires targeted workarounds, and MSO conditional
comments allow targeting specific Word-engine versions.

## Client Rendering Engines

| Client               | Engine              | Notes                   |
|----------------------|---------------------|-------------------------|
| Outlook 2016–2021    | Word / WPFR         | VML for images/shapes   |
| Outlook 2024 Win     | Edge WebView2       | Modern CSS supported    |
| Outlook on the Web   | Edge / WebKit       | Good CSS support        |
| Gmail (web)          | Chrome              | Strips `<head>` styles  |
| Gmail (iOS/Android)  | Chrome WebView      | Strips `<head>` styles  |
| Apple Mail (macOS)   | WebKit              | Full CSS support        |
| Apple Mail (iOS)     | WebKit              | Full CSS support        |
| Yahoo! Mail          | Chrome WebView      | Partial CSS support     |
| Samsung Email        | Chromium            | Partial CSS support     |

## CSS Property Support Matrix

| Property            | Outlook 16-21 | Gmail web | Apple Mail |
|---------------------|---------------|-----------|------------|
| `margin`            | Yes           | Yes       | Yes        |
| `padding`           | Yes           | Yes       | Yes        |
| `border`            | Partial       | Yes       | Yes        |
| `width` / `height`  | Partial       | Yes       | Yes        |
| `background-color`  | Yes           | Yes       | Yes        |
| `background-image`  | No (use VML)  | Yes       | Yes        |
| `font-family`       | System only   | Yes       | Yes        |
| `@font-face`        | No            | No        | Yes        |
| Flexbox             | No            | Yes       | Yes        |
| CSS Grid            | No            | Yes       | Yes        |
| `border-radius`     | No            | Yes       | Yes        |
| `box-shadow`        | No            | Yes       | Yes        |
| Media queries       | Partial       | Yes       | Yes        |
| `position`          | No            | No        | Yes        |
| CSS animations      | No            | No        | Yes        |

Universally safe (inline only): `width`, `height`, `color`,
`background-color`, `font-size`, `font-family`, `font-weight`,
`text-align`, `line-height`, `padding`, `margin`, `border`.

## MSO Conditional Comments

Target Word-engine Outlook (2007–2021) with HTML conditional
comments — ignored by all other clients:

```html
<!-- Constrain layout width for Outlook -->
<!--[if mso]>
<table role="presentation" cellspacing="0"
       cellpadding="0" border="0" width="600">
  <tr><td>
<![endif]-->
<div style="max-width:600px;">
  <!-- email body content -->
</div>
<!--[if mso]>
  </td></tr>
</table>
<![endif]-->
```

VML background image (Outlook Word-engine only):

```html
<!--[if gte mso 9]>
<v:rect xmlns:v="urn:schemas-microsoft-com:vml"
  fill="true" stroke="false"
  style="width:600px;height:300px;">
  <v:fill type="tile"
    src="https://cdn.example.com/bg.jpg"
    color="#ffffff" />
  <v:textbox inset="0,0,0,0">
<![endif]-->
<div><!-- foreground content --></div>
<!--[if gte mso 9]>
  </v:textbox></v:rect>
<![endif]-->
```

Conditional comment version targets:
- `<!--[if mso]>` — all Outlook desktop Word-engine versions
- `<!--[if gte mso 9]>` — Outlook 2000 and above
- `<!--[if (gte mso 9)&(lte mso 11)]>` — Outlook 2000–2003

## Dark Mode Per Client

| Client            | Dark mode CSS target                          |
|-------------------|-----------------------------------------------|
| Apple Mail        | `@media (prefers-color-scheme: dark)`         |
| Outlook on Web    | `[data-ogsb] .class`                          |
| Gmail (web)       | Not supported; ignores `prefers-color-scheme` |
| Samsung Email     | `@media (prefers-color-scheme: dark)`         |
| Yahoo Mail        | `@media (prefers-color-scheme: dark)`         |

Always declare explicit `background-color` and `color` on
every element so clients cannot apply their own inversions:

```html
<td style="background-color:#ffffff;color:#1a1a1a;">
  <!-- content -->
</td>
```

Apple Mail dark mode override:

```html
<style>
@media (prefers-color-scheme: dark) {
  .email-body { background-color: #1a1a1a !important; }
  .email-text { color: #f0f0f0 !important; }
  .email-card { background-color: #2d2d2d !important; }
}
</style>
```

Add `class` attributes alongside inline styles; Apple Mail
and Samsung Email apply the `!important` overrides, while
Gmail ignores `<style>` blocks and falls back to inline.

## Anti-patterns

- Using CSS classes without inline style fallbacks — Gmail
  strips `<style>` blocks in most client contexts; class-only
  styles do not render.
- `display:flex` on layout containers without a table-based
  fallback — the Word-engine in Outlook 2016–2021 ignores
  flex entirely.
- Percentage widths on `<td>` without a `width` HTML attribute
  — Outlook may collapse the column to its minimum content
  width.
- Setting `font-size` only via a class selector — Outlook
  falls back to its default 12pt rendering.
- Using `<div>` for structural columns — only `<table>/<td>`
  reliably creates columns in all Outlook versions.

## Gotchas

- Gmail clips emails over ~102 KB. The footer, tracking pixel,
  and unsubscribe link below the clip are hidden until the user
  clicks "View entire message".
- Outlook 2024 on Windows uses Edge WebView2 with modern CSS
  support, but Outlook 2016–2021 (dominant in enterprise) still
  uses the Word layout engine.
- Samsung Email applies its own dark-mode inversion that can
  override `!important`; test on a physical device.
- `max-width` on `<div>` is ignored by Outlook Word-engine;
  use `<table width="600">` instead.

## Verification

1. Run templates through Litmus or Email on Acid before
   production launch — both render in 90+ real clients.
2. Check HTML output size: `wc -c email.html` must be under
   102,000 bytes.
3. Consult `caniemail.com` before adding any new CSS property.
4. Send manually to a real Outlook 2016/2019 desktop client;
   screenshots alone do not catch all Word-engine rendering
   edge cases.

## Related

- email/react-email-template-system.md
- email/mjml-template-framework.md
- email/email-responsive-design.md
- email/email-dark-mode-support.md
- email/email-testing-debugging.md

## Source URLs (verified 2026-08-17)

- https://caniemail.com/
- https://www.litmus.com/email-client-market-share/
- https://www.emailonacid.com/blog/article/email-development/
- https://learn.microsoft.com/en-us/office/vba/outlook/
- https://www.hteumeuleu.com/2020/dealing-with-outlook/
