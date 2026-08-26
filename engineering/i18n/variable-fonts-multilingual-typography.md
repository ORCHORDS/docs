# Variable Fonts for Multilingual Typography

- **Date**: 2026-08-22
- **Author**: example.com
- **Status**: production

## Symptom / Use-case

Your international site loads 14 separate font files — Regular, Bold, Italic, and
Bold-Italic for Latin, Arabic, and CJK — adding 4–8 MB to every page load. Worse, the
Arabic Bold and Latin Bold are different design systems that don't visually harmonise.
When a user's locale changes the CSS switches font families and headings suddenly jump
in size because optical sizes differ. You want one font technology choice that scales
across scripts, weights, and styles without an avalanche of requests.

## Context

**Variable fonts** (OpenType Font Variations, released in 2016 with OpenType 1.8) encode
a continuous design space along named axes — weight (`wght`), width (`wdth`), optical
size (`opsz`), slant (`slnt`) — into a single binary. The browser interpolates any point
in that space at render time. For i18n this offers three specific advantages:

1. **Cross-script weight consistency** — a single `font-weight: 700` value can correspond
   to the same perceptual weight in Latin, Arabic, Devanagari, and CJK if the typeface
   designer has coordinated the axes across scripts.
2. **Fewer HTTP requests** — one `.woff2` variable font can replace 4–8 static files.
3. **Optical size axis (`opsz`)** — automatically adjusts stroke contrast for small body
   text vs large headings, which is especially important for Arabic naskh and CJK where
   strokes at display size differ significantly from text size.

**Caveat**: Not all scripts have mature variable font support. CJK variable fonts exist
(Noto Sans CJK, UD Digi Kyokasho) but are enormous (10–40 MB) and require aggressive
subsetting. Arabic variable fonts are maturing (Scheherazade New, Reem Kufi). Latin
coverage is excellent.

## Step 1 — Font Selection by Script Coverage

Choose fonts that either share a coordinated variable design system or use complementary
fallback stacks:

```css
/* Coordinated multi-script variable font stack */
:root {
  --font-body: 'Noto Sans Variable', 'Noto Sans Arabic Variable', system-ui, sans-serif;
  --font-display: 'Noto Serif Variable', 'Noto Serif Arabic Variable', Georgia, serif;
}
```

For CJK, Noto Sans CJK is available as a variable font but requires `unicode-range`
subsetting to be practical. Alternatively, use Google Fonts' `Noto Sans JP`, `Noto Sans
SC`, etc. as static fallbacks while using a variable Latin font for the primary weight
range.

### Font decision matrix

| Script | Best variable font option | Axes available |
|---|---|---|
| Latin / Cyrillic / Greek | Noto Sans Variable, Inter, Source Sans 3 | wght, wdth, opsz |
| Arabic | Scheherazade New, Reem Kufi | wght |
| Hebrew | David Libre (partial) | wght |
| Devanagari | Mukta (limited), Noto Sans Devanagari | wght |
| CJK | Noto Sans CJK (large), UD Digi Kyokasho NKR | wght |
| Tamil / Telugu | Noto Sans (script-specific) | wght |

## Step 2 — Loading Variable Fonts Correctly

```css
/* Declare the variable font with CSS font-face */
@font-face {
  font-family: 'Noto Sans';
  src:
    url('/fonts/NotoSans-Variable.woff2') format('woff2 supports variations'),
    url('/fonts/NotoSans-Variable.woff2') format('woff2');
  font-weight: 100 900;       /* declare the full axis range */
  font-style: normal;
  font-display: swap;         /* avoid invisible text during load */
  unicode-range:              /* Latin + Latin Extended */
    U+0000-00FF, U+0100-024F, U+0250-02AF, U+1E00-1EFF;
}

@font-face {
  font-family: 'Noto Sans Arabic';
  src: url('/fonts/NotoSansArabic-Variable.woff2') format('woff2 supports variations'),
       url('/fonts/NotoSansArabic-Variable.woff2') format('woff2');
  font-weight: 100 900;
  font-style: normal;
  font-display: swap;
  unicode-range: U+0600-06FF, U+0750-077F, U+FB50-FDFF, U+FE70-FEFF;
}
```

The `unicode-range` descriptor is the critical performance technique: the browser only
downloads a font file when the page contains characters matching the declared range. This
prevents a Japanese page from downloading the Arabic variable font and vice versa.

## Step 3 — Using Font Variation Settings in CSS

```css
/* Body text */
body {
  font-family: var(--font-body);
  font-weight: 400;
  font-variation-settings: 'opsz' 14;   /* optical size: body text ~14px */
}

/* Headings */
h1, h2 {
  font-weight: 700;
  font-variation-settings: 'opsz' 32, 'wdth' 90;  /* slightly condensed at display size */
}

/* Locale-specific overrides */
:lang(ar) body {
  font-family: 'Noto Sans Arabic', var(--font-body);
  font-weight: 400;
  /* Arabic variable fonts often don't have opsz; do not set unknown axes */
  font-variation-settings: normal;
}

:lang(ja), :lang(zh), :lang(ko) {
  /* CJK: no variable font — rely on system stack */
  font-family: 'Hiragino Kaku Gothic ProN', 'Noto Sans JP', sans-serif;
  font-weight: 400;   /* maps to system font weight, not variable axis */
}
```

**Critical**: Setting a `font-variation-settings` value for an axis that the currently
active font does not support does not cause an error but may prevent CSS variable
font feature queries from working correctly. Always reset to `normal` for locales using
non-variable fallback fonts.

## Step 4 — Subsetting for CJK

CJK variable fonts (Noto Sans CJK) are 10–40 MB unsubsetted. Use `pyftsubset` (from
fonttools) with a character frequency list:

```bash
# Install
pip install fonttools brotli

# Generate a frequency-based subset (top 3000 characters cover ~99.5% of Japanese web text)
pyftsubset NotoSansCJKjp-VF.ttf \
  --unicodes-file=ja-top-3000.txt \
  --flavor=woff2 \
  --layout-features='*' \      # preserve all OpenType features (kerning, liga)
  --output-file=NotoSansCJKjp-VF-subset.woff2

# Result: typically 300-800 KB instead of 40 MB
```

Where `ja-top-3000.txt` is a Unicode code point list (`U+4E00\nU+4E01\n...`) derived
from corpus analysis of your target content domain.

For dynamic content (user-generated text with unpredictable kanji), use a font service
or the Google Fonts `text=` parameter to request character-specific subsets at runtime:

```html
<!-- Google Fonts dynamic subset — request only the characters on this page -->
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="stylesheet"
  href="https://fonts.googleapis.com/css2?family=Noto+Sans+JP:wght@400;700&text=東京春祭">
```

## Step 5 — Preloading for Core Scripts

Preload the primary variable font for the page's dominant script to eliminate the font
FOUT (Flash Of Unstyled Text):

```html
<!-- Preload the Latin variable font (applies to ~75% of your traffic) -->
<link rel="preload"

  as="font"
  type="font/woff2"
  crossorigin>

<!-- Locale-specific preload (rendered server-side based on request locale) -->
{#if locale.startsWith('ar')}
<link rel="preload"

  as="font"
  type="font/woff2"
  crossorigin>
{/if}
```

In a Cloudflare Worker or Next.js middleware, inject the correct preload link based on
the detected locale before the HTML reaches the client.

## Step 6 — Optical Size Axis for Mixed-Script Headings

When a heading mixes scripts (e.g. an English product name within a Japanese sentence),
the `opsz` axis of the Latin variable font will activate but the Japanese system font
won't have one. Use `font-size-adjust` to harmonize x-heights across the mixed run:

```css
/* Equalize x-height: Noto Sans has an x-height ratio of ~0.52 */
/* Japanese system fonts vary; Hiragino is ~0.51 */
.heading-mixed-script {
  font-size-adjust: 0.52;   /* normalizes x-height across all fonts in the stack */
}
```

`font-size-adjust` is now supported in all major browsers as of 2023.

## Anti-patterns

- **Loading a variable font without `unicode-range`** — the browser downloads it for
  every page even if the page has no characters in that script, wasting bandwidth.
- **Setting `font-variation-settings` instead of `font-weight`** — `font-weight: 700`
  is composable and works with bold inheritance; `font-variation-settings: 'wght' 700`
  resets all other axes to their defaults on every declaration and does not inherit
  intermediate values cleanly.
- **Using a CJK variable font unsub-setted in a web page** — a 40 MB font file causes
  a ~10 second FOUT on mobile; always subset before deploying.
- **Assuming all scripts need the same weight mapping** — Arabic Bold at `wght: 700`
  may appear heavier than Latin Bold at `wght: 700` due to stroke density; test each
  locale at each weight level in your design system.
- **Hosting fonts from a third-party CDN that is blocked in some regions** — some fonts.
  googleapis.com requests are slow or blocked in China; host the font files yourself and
  serve them from Cloudflare R2 for consistent global latency.

## Gotchas

- `font-display: swap` causes FOUT; for LCP (Largest Contentful Paint) headlines use
  `font-display: block` with a tight 100ms timeout, or preload the font.
- Safari on macOS < 13 has intermittent bugs with variable font rendering at fractional
  pixel sizes; test on older Safari builds.
- Variable fonts do not eliminate the need for `font-synthesis: none` in RTL contexts —
  synthetic bold/italic applied to Arabic variable fonts can distort letterforms.
- The `wdth` (width) axis is not available for Arabic or most CJK variable fonts; avoid
  CSS that applies `font-stretch` to non-Latin scripts.
- Not all font axes are registered; custom axes use four-character uppercase tags like
  `YTLC` (Roboto Flex). Document any custom axes used in your design system.

## Verification

```javascript
// Feature-detect variable font support in the browser
const isVariableFont = CSS.supports('font-variation-settings', '"wght" 400');

// Log loaded font for a specific element (Chrome DevTools alternative)
document.fonts.ready.then(() => {
  const el = document.querySelector('h1');
  const computed = getComputedStyle(el);
  console.log('Font family in use:', computed.fontFamily);
  // Inspect in DevTools: Elements → Computed → font-variation-settings
});
```

Run Lighthouse or WebPageTest with locale-specific URLs to confirm font file sizes and
request counts per locale. Aim for < 150 KB total variable font payload per page.

## Related

- `multilingual-font-loading-subsetting.md`
- `r2-font-subsetting-multi-script-pipeline-2026.md`
- `chinese-japanese-cjk-fonts.md`
- `arabic-persian-text-rendering.md`
- `indic-script-rendering.md`
- `css-logical-properties-2026.md`
- `bidi-rtl-layout-css.md`

## Sources

- OpenType Specification 1.9, Microsoft Typography — Font Variations
- Google Fonts Knowledge: Variable fonts guide
- MDN Web Docs: Variable fonts guide
- CSS Fonts Level 4 specification — `font-variation-settings`, `font-size-adjust`
- fonttools/pyftsubset documentation: https://fonttools.readthedocs.io/
- W3C International: Styling Arabic text
- Noto Fonts variable font releases: https://github.com/notofonts/noto-fonts
