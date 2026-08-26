# Dark Mode and Accessibility in HTML Email

**Date:** 2026-08-16
**Author:** the platform team
**Status:** published

## Symptom

Your HTML emails look broken in dark mode — white backgrounds become
dark, logos with transparent backgrounds disappear, dark text on
dark backgrounds becomes unreadable, and brand colors shift
unpredictably. Users on screen readers cannot navigate your emails
because they rely on images-as-text, missing alt attributes, and
table-based layouts without semantic structure. Your emails fail
accessibility audits, and 40%+ of your subscribers use dark mode by
default.

## Context

Dark mode email rendering varies dramatically across clients. Apple
Mail, Outlook (Windows/Mac), and Gmail each apply different color
inversion strategies — some honor `prefers-color-scheme` media queries,
some partially invert colors, and some fully invert everything
including images. In 2026, dark mode usage exceeds 40% across email
clients, making dark mode optimization a baseline requirement rather
than an enhancement. Email accessibility follows WCAG 2.2 guidelines
but is complicated by the limited subset of HTML and CSS that email
clients support — no JavaScript, no external stylesheets in many
clients, and inconsistent CSS property support.

## Dark mode rendering behavior

| Email client | Dark mode behavior | CSS support |
|---|---|---|
| Apple Mail | Honors `prefers-color-scheme` | Full |
| Outlook (Windows) | Partial inversion, ignores media query | Limited |
| Outlook (Mac) | Honors `prefers-color-scheme` | Good |
| Gmail (web) | Full color inversion | No media query |
| Gmail (mobile) | Full color inversion | No media query |
| Yahoo Mail | Honors `prefers-color-scheme` | Good |
| Outlook.com | Partial inversion | Limited |

### Three dark mode strategies

```
1. Nothing (let client decide)
   → Client applies automatic inversion
   → Least control, most breakage
   → Use only for simple text-only emails

2. Meta tag opt-in
   → <meta name="color-scheme" content="light dark">
   → Tells client you support dark mode
   → Prevents some aggressive auto-inversions

3. Full CSS control
   → @media (prefers-color-scheme: dark) { ... }
   → Override colors, swap images, adjust contrast
   → Best results in supporting clients
```

## Dark mode CSS implementation

```html
<head>
  <meta name="color-scheme" content="light dark">
  <meta name="supported-color-schemes" content="light dark">
  <style>
    :root {
      color-scheme: light dark;
    }

    /* Light mode defaults */
    .email-body {
      background-color: #FFFFFF;
      color: #1A1A1A;
    }
    .card {
      background-color: #F5F5F5;
      border: 1px solid #E0E0E0;
    }
    .heading { color: #111111; }
    .body-text { color: #333333; }
    .muted-text { color: #666666; }

    /* Dark mode overrides */
    @media (prefers-color-scheme: dark) {
      .email-body {
        background-color: #1A1A1A !important;
        color: #F0F0F0 !important;
      }
      .card {
        background-color: #2A2A2A !important;
        border-color: #3A3A3A !important;
      }
      .heading { color: #FFFFFF !important; }
      .body-text { color: #E0E0E0 !important; }
      .muted-text { color: #AAAAAA !important; }
    }

    /* Outlook dark mode (data-ogsc) */
    [data-ogsc] .email-body {
      background-color: #1A1A1A !important;
      color: #F0F0F0 !important;
    }
  </style>
</head>
```

## Logo handling in dark mode

```html
<!-- Option 1: Swap logos with media query -->
<picture>
  <source
    srcset="logo-dark-mode.png"
    media="(prefers-color-scheme: dark)">
  <img  alt="Company Name"
       style="width: 150px; height: auto;">
</picture>

<!-- Option 2: Add padding/background to transparent logo -->
<img  alt="Company Name"
     style="background-color: #FFFFFF;
            padding: 8px;
            border-radius: 4px;">

<!-- Option 3: Use logo with built-in light outline -->
<!-- Ensure logo has a subtle light stroke around dark elements -->
```

## Accessibility checklist

### Structure

```html
<!-- Use semantic roles for screen readers -->
<table role="presentation" ...>  <!-- layout tables -->
<table role="table" ...>         <!-- data tables -->

<!-- Language declaration -->
<html lang="en" dir="ltr">

<!-- Proper heading hierarchy -->
<h1 style="...">Main Heading</h1>
<h2 style="...">Section Heading</h2>
<!-- Never skip heading levels -->
```

### Images and alt text

```html
<!-- Informative images: descriptive alt -->
<img  alt="Blue running shoes, size 10, $89.99">

<!-- Decorative images: empty alt -->
<img  alt="" role="presentation">

<!-- Never use images for text content -->
<!-- BAD -->
<img  alt="50% off sale">
<!-- GOOD -->
<h2 style="font-size: 24px; color: #CC0000;">50% Off Sale</h2>
```

### Color contrast

```
WCAG 2.2 minimum contrast ratios:
  Normal text (< 18px): 4.5:1
  Large text (≥ 18px bold or ≥ 24px): 3:1
  UI components and icons: 3:1

Light mode examples:
  ✓ #333333 on #FFFFFF = 12.6:1 (excellent)
  ✓ #666666 on #FFFFFF = 5.7:1 (good)
  ✗ #999999 on #FFFFFF = 2.8:1 (fails)

Dark mode examples:
  ✓ #E0E0E0 on #1A1A1A = 14.5:1 (excellent)
  ✓ #AAAAAA on #1A1A1A = 8.0:1 (good)
  ✗ #666666 on #1A1A1A = 3.4:1 (fails for body text)
```

### Links and CTAs

```html
<!-- Links must be distinguishable by more than color -->
<a  style="color: #0066CC;
                     text-decoration: underline;
                     font-weight: bold;">
  View your order
</a>

<!-- CTA buttons: sufficient size and contrast -->
<a  style="display: inline-block;
                     padding: 14px 28px;
                     font-size: 16px;
                     background-color: #0066CC;
                     color: #FFFFFF;
                     text-decoration: none;
                     border-radius: 4px;">
  Complete Purchase
</a>
<!-- Minimum touch target: 44×44px (WCAG 2.2) -->
```

## Anti-patterns

- **Images as text** — rendering headings, CTAs, or body copy as
  images. Screen readers cannot read them (beyond alt text), they
  do not scale with user font preferences, and they break in dark
  mode. Use live HTML text with inline styles.
- **Ignoring dark mode** — not testing or optimizing for dark mode.
  Automatic color inversion breaks logos, reduces contrast, and
  creates visual artifacts. At minimum, add the `color-scheme` meta
  tag and test in Apple Mail and Outlook dark mode.
- **Low contrast text** — using light gray text (#999999) on white
  backgrounds for "subtle" styling. This fails WCAG contrast
  requirements and is unreadable for users with low vision.
- **Missing alt attributes** — omitting `alt` on `<img>` tags.
  Screen readers announce the image filename, which is confusing
  ("image_2847_v3_final.png"). Every image needs `alt` — descriptive
  for informative images, empty (`alt=""`) for decorative ones.

## Gotchas

- **Gmail ignores prefers-color-scheme** — Gmail applies its own
  full color inversion in dark mode and does not support the
  `prefers-color-scheme` media query. Design for invertibility: use
  softer colors (#F9F9F9 instead of #FFFFFF) that invert gracefully.
- **Outlook uses data-ogsc** — Outlook on Windows uses its own
  `[data-ogsc]` selector for dark mode overrides, not standard
  media queries. Include Outlook-specific selectors alongside
  `prefers-color-scheme` rules.
- **Email client CSS stripping** — many clients strip `<style>` tags
  entirely (older Gmail, some mobile clients). Critical styles must
  be inline. Use a CSS inliner in your build pipeline.
- **Font size minimums** — body text below 14px is difficult to read
  on mobile. Use 16px as the default body text size and never go
  below 14px for any readable content.

## Verification

- Emails render correctly in dark mode across Apple Mail, Outlook,
  and Gmail.
- Color-scheme meta tag is present in all email templates.
- All images have appropriate alt text (descriptive or empty).
- Text contrast meets WCAG 2.2 minimums (4.5:1 for body text).
- No critical content is rendered as images.
- Emails are tested with a screen reader (VoiceOver, NVDA).
- Touch targets for links and buttons meet 44×44px minimum.

## Related

- `documentation/docs/policies/email/bimi-brand-indicators-email.md`
- `documentation/docs/policies/email/spf-dkim-dmarc-email-auth.md`
- `documentation/docs/policies/frontend/accessibility-patterns.md`

## Source URLs (verified 2026-08-16)

- Email Accessibility and Design Best Practices 2026 — https://emfluence.com/blog/email-accessibility-and-design-best-practices-in-2026
- Dark Mode Email Design Best Practices 2026 — https://www.enchantagency.com/blog/dark-mode-email-design-best-practices-css-guide-2026
- Email Design for Dark Mode 2026 — https://www.maildesigner365.com/email-design-for-dark-mode/
- Ultimate Guide to Dark Mode Email — https://www.litmus.com/blog/the-ultimate-guide-to-dark-mode-for-email-marketers
