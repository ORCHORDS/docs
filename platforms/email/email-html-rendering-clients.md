# email-html-rendering-clients

**Issue:** Understanding email client rendering engines and their differences
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Emails look perfect in one client and broken in another because each client uses a different rendering engine.

## Pattern / Solution
Rendering engines by client:
- **Outlook 2007-2019 (Windows):** Microsoft Word rendering engine. No flexbox, no CSS grid, limited CSS support.
- **Outlook on Mac / New Outlook (2021+):** WebKit-based; much better CSS support.
- **Gmail (web):** Blink; strips `<head>` styles; inline CSS required. Supports media queries since 2016.
- **Gmail (Android/iOS app):** Same as Gmail web.
- **Apple Mail (macOS/iOS):** WebKit; best CSS support overall.
- **Samsung Mail:** Blink; similar to Gmail.
- **Yahoo/AOL:** Gecko-based; strips some CSS properties.
- **Outlook.com:** Blink; similar to Gmail.

Build order: start with Outlook-safe baseline, layer progressive enhancements.

## Gotchas
- Outlook uses VML for background images; always include VML fallback.
- Gmail clips emails over 102 KB; split long emails or compress HTML.
- Never rely on `<link>` stylesheets; inline all CSS or use `<style>` in `<head>` with inline fallback.

## Related
- email-css-support-table, email-responsive-design, email-dark-mode-support, mjml-template-framework
