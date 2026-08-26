# RTL Layout on Cloudflare Pages with CSS Logical Properties and Mobile Safari Fixes

- **Date**: 2026-08-22
- **Author**: example.com
- **Status**: active

## Symptom

Arabic and Hebrew pages on example project (example.com) render with mirrored icons and misaligned
form fields on mobile Safari 17 even though the desktop layout is correct. Flex
containers switch direction but `box-shadow`, `border-radius`, and `text-align` remain
LTR-anchored. The `dir="rtl"` attribute is missing from the `<html>` element on the
initial static HTML shell from Cloudflare Pages, causing a flash of LTR content before
client-side hydration corrects it.

## Context

example project is a Next.js static export on Cloudflare Pages. The API layer is Cloudflare
Workers with D1 and R2. RTL languages supported: Arabic (`ar`, `ar-SA`, `ar-EG`),
Hebrew (`he`), Persian (`fa`), Urdu (`ur`). The static export means per-locale HTML
files are pre-built; the Worker can also inject `dir` via response transformation using
`HTMLRewriter`. Mobile Safari on iOS has known RTL rendering bugs in flexbox and sticky
positioning that require targeted workarounds.

---

## CSS Logical Properties: The Correct RTL Foundation

Physical CSS properties (`margin-left`, `padding-right`, `border-left`, `text-align:
left`) are hardcoded to the LTR visual axis. Logical properties map to the *inline* or
*block* flow direction and flip automatically when `dir="rtl"` is set on an ancestor.

| Physical property       | Logical equivalent       | RTL result         |
|-------------------------|--------------------------|---------------------|
| `margin-left`           | `margin-inline-start`    | becomes right side  |
| `padding-right`         | `padding-inline-end`     | becomes left side   |
| `border-left`           | `border-inline-start`    | becomes right side  |
| `left: 0`               | `inset-inline-start: 0`  | becomes right: 0    |
| `text-align: left`      | `text-align: start`      | aligns to RTL start |
| `float: right`          | `float: inline-end`      | RTL-aware float     |

```css
/* Before — breaks RTL */
.card {
  margin-left: 1rem;
  padding-right: 0.75rem;
  border-left: 3px solid var(--accent);
  text-align: left;
}

/* After — RTL-safe */
.card {
  margin-inline-start: 1rem;
  padding-inline-end: 0.75rem;
  border-inline-start: 3px solid var(--accent);
  text-align: start;
}
```

Logical properties are supported in all evergreen browsers including mobile Safari 15+
and Android Chrome 89+. Use the PostCSS `postcss-logical` plugin only for targets older
than 2022.

---

## Injecting the dir Attribute via Cloudflare Workers HTMLRewriter

For the static export the `dir` attribute must be in the initial HTML to avoid FOWC.
The Worker sits in front of Cloudflare Pages via a `_routes.json` exclusion list and
uses `HTMLRewriter` to inject `dir` and `lang` on the HTML element.

```typescript
// workers/src/dir-injector.ts
const RTL_LANGUAGES = new Set(["ar", "he", "fa", "ur", "yi", "dv", "ps"]);

function isRTL(locale: string): boolean {
  const lang = locale.split(/[-_]/)[0].toLowerCase();
  return RTL_LANGUAGES.has(lang);
}

export function injectDirAttribute(
  response: Response,
  locale: string
): Response {
  const dir = isRTL(locale) ? "rtl" : "ltr";
  return new HTMLRewriter()
    .on("html", {
      element(el) {
        el.setAttribute("dir", dir);
        el.setAttribute("lang", locale);
      },
    })
    .transform(response);
}
```

```typescript
// workers/src/index.ts
export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const locale = detectLocale(request); // from cookie / Accept-Language
    const upstream = await env.ASSETS.fetch(request);
    if (upstream.headers.get("content-type")?.includes("text/html")) {
      return injectDirAttribute(upstream, locale);
    }
    return upstream;
  },
};
```

`HTMLRewriter` streams the response — no buffering penalty on large pages.

---

## Mobile Safari RTL Bugs and Workarounds

iOS Safari has a distinct rendering pipeline (WebKit) that diverges from desktop Safari
and Chrome on several RTL edge cases.

| Bug                                              | Affected versions  | Workaround                                      |
|--------------------------------------------------|--------------------|-------------------------------------------------|
| `position: sticky` ignores `inset-inline-*`      | Safari ≤ 17.3      | Use `right`/`left` with `[dir=rtl]` override    |
| Flex `row-reverse` double-reversal with RTL dir  | Safari 16.x        | Use `flex-direction: row` + `dir="rtl"` instead |
| `scroll-snap-align: start` snaps to wrong edge   | Safari 17.0–17.2   | Add `scroll-snap-align: end` in `[dir=rtl]`     |
| SVG `transform: scaleX(-1)` mirror ignores RTL   | All Safari         | Flip SVG paths or use `direction: rtl` on SVG   |
| `border-inline-start` on `<input>` renders wrong | Safari ≤ 16.5      | Apply `border-right` in `[dir=rtl] input`       |

```css
/* Sticky header RTL Safari fix */
.sticky-header {
  position: sticky;
  inset-block-start: 0;          /* block axis — fine everywhere */
  inset-inline-start: 0;         /* logical */
}

/* Safari ≤ 17.3 override */
[dir="rtl"] .sticky-header {
  left: auto;
  right: 0;
}
```

```css
/* Scroll snap RTL fix */
.carousel-item {
  scroll-snap-align: start;
}
[dir="rtl"] .carousel-item {
  scroll-snap-align: end;
}
```

---

## Next.js Static Export: Pre-Building RTL HTML Files

In a `next export` setup, each locale gets its own directory. Configure `next.config.js`
to output locale-specific directories and set `dir` at build time for RTL locales.

```javascript
// next.config.js
const RTL = new Set(["ar", "he", "fa", "ur"]);

/** @type {import('next').NextConfig} */
module.exports = {
  output: "export",
  i18n: undefined, // static export does not support Next.js built-in i18n router
  // Use next-intl or similar with generateStaticParams instead
};
```

```tsx
// app/[locale]/layout.tsx
import { localeMetadata } from "@/lib/i18n";

export default function RootLayout({
  children,
  params: { locale },
}: {
  children: React.ReactNode;
  params: { locale: string };
}) {
  const { dir } = localeMetadata(locale);
  return (
    <html lang={locale} dir={dir}>
      <body>{children}</body>
    </html>
  );
}
```

When the Worker's `HTMLRewriter` is active it overwrites the static `dir` — this is
safe and idempotent, but ensure both sources agree to avoid a double-transform.

---

## Anti-patterns

- Using `direction: rtl` on `<body>` without `dir="rtl"` on `<html>` — screen readers
  and some browsers read `dir` from the HTML element, not CSS `direction`.
- Mixing physical and logical properties in the same rule — causes precedence bugs in
  RTL mode where both apply to the same edge.
- Mirroring icons via `transform: scaleX(-1)` on the entire page container — this
  mirrors text as well unless text is explicitly un-transformed.
- Using `[dir=rtl]` overrides in a separate stylesheet loaded after the main one —
  specificity issues on mobile browsers with cached stylesheets.
- Relying on `Accept-Language` alone for RTL detection without also checking
  `CF-IPCountry` or a user preference cookie — a US-based Arabic speaker sends
  `Accept-Language: ar` but is served an LTR page if the locale router falls through.

---

## Gotchas

- `HTMLRewriter` in Workers does not process streaming SSR responses from a Node.js
  origin — only static assets from Cloudflare Pages are safe to transform this way.
- Persian (`fa`) and Urdu (`ur`) use RTL script but are often listed with LTR language
  tags in older CMS exports; validate against script, not just language subtag.
- `<input type="number">` ignores `dir="rtl"` in some Android WebViews — the numeric
  keypad and cursor behaviour remains LTR.
- Icons from icon fonts (Font Awesome etc.) sometimes need explicit `dir="ltr"` on the
  `<i>` element to prevent letter-mirroring in RTL context.
- Cloudflare Pages does not support server-side middleware; all `dir` injection must
  happen in a Worker or be baked into the static HTML at build time.

---

## Verification

```bash
# Check that dir attribute is present in the initial HTML response
curl -s -H "Accept-Language: ar" \
     https://example.com/ar/ | grep -o 'dir="[^"]*"'
# Expected: dir="rtl"

# Check for logical property usage with a PostCSS audit
npx postcss-logical-audit --dir ./src/styles
```

```javascript
// Playwright RTL layout test
test("Arabic page has dir=rtl on html element", async ({ page }) => {
  await page.goto("/ar/");
  const dir = await page.locator("html").getAttribute("dir");
  expect(dir).toBe("rtl");
});
```

---

## Related

- `rtl-bidi-handling.md`
- `bidi-rtl-layout-css.md`
- `css-logical-properties-2026.md`
- `hebrew-rtl-react.md`
- `arabic-persian-text-rendering.md`
- `i18n-rtl-testing-2026.md`

---

## Sources

- MDN CSS Logical Properties: https://developer.mozilla.org/en-US/docs/Web/CSS/CSS_logical_properties_and_values
- Cloudflare HTMLRewriter: https://developers.cloudflare.com/workers/runtime-apis/html-rewriter/
- WebKit Bug Tracker — RTL flex issues: https://bugs.webkit.org/
- W3C CSS Writing Modes Level 4: https://www.w3.org/TR/css-writing-modes-4/
- Unicode Bidirectional Algorithm: https://unicode.org/reports/tr9/
