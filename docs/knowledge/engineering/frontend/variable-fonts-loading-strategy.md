# variable-fonts-loading-strategy

**Issue:** A product ships a variable font to get "all weights in one file," then Lighthouse CLS jumps: fallback text renders in the system font, the variable font arrives late with `font-display: swap`, and every headline, button, and card shifts because the fallback and web font have different widths, ascenders, and line heights. Teams respond by choosing `font-display: block` (invisible text for 3 seconds) or dropping to one static weight (losing the design). The correct strategy has three coordinated parts: only use a variable file when the weight count justifies it, fence the fallback with `size-adjust`/`ascent-override` metrics overrides so the swap is invisible, and pick the `font-display` value that matches whether that font is above or below the fold.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## When a variable font actually wins

1. **The break-even math.** A single variable font file (Latin subset) typically runs 30–60 KB woff2, while one static weight of the same family runs 10–25 KB. Two or more used weights → the variable file usually wins on bytes; one weight (most body-text sites) → a static 400 plus a static 700 may still beat it. Check real numbers with `woff2_compress` output or the foundry's file sizes, not folklore.
2. **Register the axis range, not one weight.** In `@font-face`, declare `font-weight: 400 700;` (and `font-stretch`/`font-style` ranges if the file carries those axes) so all intermediate weights — including animated weight transitions and `font-weight: 550` from design tokens — resolve without extra requests.
3. **Subset before anything else.** Subsetting a variable font (pyftsubset/glyphhanger, or the foundry's unicode-range subsets) cuts 60–80% of bytes for Latin-only sites, and it composes with everything below. Google Fonts' CSS API serves per-script subsets with `unicode-range` by default — self-hosting loses this unless you replicate it.
4. **Preload exactly one critical file.** `<link rel="preload" as="font" crossorigin>` for the single above-the-fold font only; preloading two weights of the same family plus a variable file triples the high-priority queue and delays LCP. If `next/font` is available it does preload + fallback fencing automatically (`adjustFontFallback` defaults to on).

## Fallback metrics fencing (the CLS fix)

1. **The four override descriptors.** A fallback `@font-face` for the local system font can declare `size-adjust` (uniform scale of the fallback glyphs), `ascent-override`, `descent-override`, and `line-gap-override` so its metrics match the web font. The swap then changes glyph shapes without changing line boxes — CLS from the swap drops to near zero even with `font-display: swap`.
   ```css
   @font-face {
     font-family: 'Inter-fallback';
     src: local('Arial');
     size-adjust: 107.4%;
     ascent-override: 90.2%;
     descent-override: 22.4%;
     line-gap-override: 0%;
   }
   body { font-family: 'Inter', 'Inter-fallback', sans-serif; }
   ```
2. **Compute values from font metadata, not by eye.** The `@capsizecss/metrics` package ships metric tables for every Google/system font; tools like Fontpie and screenspan.net's Fallback Font Generator emit the whole `@font-face` block from the two family names. Hand-tuning until "it looks close" does not survive a font upgrade — regenerate on version bumps.
3. **`size-adjust` fences the horizontal shift too.** Late font swaps shift text horizontally (different average glyph widths rewrap lines), which is the CLS that actually hurts on paragraphs. `size-adjust` normalizes overall width; the ascent/descent/line-gap trio normalizes the vertical line box. You need all four for both axes of the shift.
4. **Fence per weight-pairing, and mind the limits.** Overrides are per-`@font-face`, so a bold headline fallback needs its own fenced face against the web font's 700. And per Vincent Bernat's 2024 analysis, proportional fonts with unusual letter distributions cannot be perfectly width-matched — fencing gets you from a big jump to a sub-pixel shimmer; `optional` (below) is the only way to fully zero the swap.
5. **Reserve space for capped text with Capsize-style trimming.** If the design uses tight cap-height alignment, Capsize's metadata approach (trimming the leading above caps/below baseline) both improves rhythm and removes the invisible headroom where swaps used to shift — sizing by cap height makes the box match the ink.

## font-display: the tradeoff matrix

1. **`swap` — best perceived speed, safe only with fencing.** Fallback shows immediately, web font swaps in whenever it loads. Without metric fencing this is the CLS generator; with the overrides above it is the default choice for above-the-fold text.
2. **`optional` — zero CLS, first-visit lottery.** ~100ms block period; if the font isn't there, the browser keeps the fallback for the page lifetime and caches the font in the background — second visit shows the web font. This is the correct choice for body text when you'd rather have no shift than a specific font on first load (Chrome's recommendation for non-critical fonts).
3. **`block` and `fallback` — mostly legacy choices.** `block` gives up to ~3s of invisible text (FOIT): measurable LCP damage, never worth it in 2026. `fallback` is a 100ms-block then swap-with-deadline; it behaves like a worse `optional` for most sites. Prefer `swap`+fencing or `optional`.
4. **One font stack, one policy per role.** Headline font (LCP element): `swap` + fenced fallback + preload, so real text is always visible and the swap is invisible. Body/UI font: `optional`. Icon fonts: `block` is tolerable only because ligature/icons blanking is cosmetic — but inline SVG is the actual fix.

## Measurement and gotchas

1. **Measure the shift, not vibes.** In Chrome DevTools, render with network throttling (Slow 4G) and CPU 4x slowdown, and read CLS in Lighthouse / the Performance panel's layout-shift regions; the red overlay shows exactly which text blocks shift. Verify the fenced fallback actually gets used — a typo'd `local()` name in the fallback face silently falls back to the un-overridden default.
2. **`local()` sources vary by OS.** Arial on Windows, Helvetica on macOS, Liberation Sans on Linux — generate a fenced fallback per target system font or accept slight variance; test the primary OS of your audience (for this repo: Android/Chrome, where Roboto is the local font to fence against).
3. **Variable + `unicode-range` subsetting conflicts.** Splitting a variable font into many unicode-range subsets can make the browser download several files (one per encountered subset), each with axis tables repeated. Prefer one Latin subset variable file over per-subset variables; keep `unicode-range` for scripts you actually use.
4. **Self-hosted fonts need long-lived immutable caching.** Late font arrival is often just cache misses — self-host with hashed filenames (`inter-latin-var.abc123.woff2`) and `Cache-Control: public, max-age=31536000, immutable` so the swap cost is paid once ever, making `swap`+fencing effectively free on repeat visits.

## Related

- `font-loading-optimization.md` (baseline: font-display values, preload)
- `next-js-font-optimization.md` (next/font does fencing automatically)
- `html-web-vitals-cls.md`
- `critical-css-extraction.md`
