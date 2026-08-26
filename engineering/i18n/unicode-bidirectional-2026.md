# unicode-bidirectional-2026

**Issue:** A team localizes to Arabic and Hebrew. The team ships a UI that shows a product name in Latin script followed by Arabic text. The team sees the text rendered backwards: the Arabic is on the left when it should be on the right. The team needs bidirectional (bidi) text handling.

**Date:** 2026-08-10
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Symptom

The Unicode Bidirectional Algorithm (UAX #9) defines how mixed left-to-right (LTR) and right-to-left (RTL) text is rendered. Without proper `dir` attribute, the algorithm can produce "tacocat" effects - logical order OK, visual order wrong.

## Root cause

The browser applies the Unicode Bidi Algorithm based on the `dir` attribute of the nearest containing block. If the page is `dir="ltr"` but contains Arabic, the algorithm may render the Arabic segment reversed. HTML `bdi` element and CSS `unicode-bidi` give explicit control.

## The 5 mechanics

1. **HTML `dir` attribute on `<html>` or block elements.** `dir="rtl"` reverses the entire block's flow.
2. **HTML `<bdi>` element.** Isolates a span of text from the surrounding bidi context (e.g., a username in an Arabic message).
3. **HTML `<bdo>` element.** Forces the direction of a span.
4. **CSS `unicode-bidi: isolate` / `embed` / `bidi-override`.** Same as HTML but at the CSS level.
5. **CSS Logical Properties.** `margin-inline-start`, `padding-inline-end`, `inset-inline-start` instead of `margin-left`, `padding-right`, `left`. Auto-flips with `dir`.

## The 5-step bidi test pattern

1. Test with mixed text: English + Arabic + numbers + punctuation.
2. Test phone numbers in Arabic UI ("+1 555 1234" should be LTR within RTL block).
3. Test filenames and code in RTL context.
4. Test placeholder text in RTL (`<input dir="rtl" placeholder="...">`).
5. Use the browser's bidi visualizer to confirm the algorithm output.

## The 5 anti-patterns

1. **Mixing `dir` and absolute positioning.** Logical properties only.
2. **Hardcoded `left`/`right` instead of `inline-start`/`inline-end`.** Breaks in RTL.
3. **Numeric strings in RTL context** without `bdi` (e.g., phone numbers rendered right-to-left).
4. **Direction-specific icons** (arrows) that point the wrong way in RTL.
5. **Logical punctuation flipped** in RTL (parens, brackets) without auto-flip.

## The 5 best practices

1. **Set `dir` on `<html>`** based on detected locale.
2. **Use logical CSS properties** (`margin-inline-start` not `margin-left`).
3. **Wrap user-generated content** (usernames, URLs) in `<bdi>`.
4. **Mirror directional icons** with `transform: scaleX(-1)` in RTL.
5. **Test with real RTL locales** (ar, he, fa, ur) early in development.

## Gotchas

- **Numbers in RTL** stay LTR but their position in the line may flip.
- **`text-align: right` in RTL** is the "end"; use `text-align: end` for direction-aware alignment.
- **`<bdi>` is underused.** Most mixed-context bugs are fixed by it.
- **Bidirectional attacks** (Trojan Source) use control characters to make code look like one thing and execute as another. Code editors now default to showing control characters.
- **CLDR "likelySubtags"** tells you which script a locale typically uses (ar → Arab, he → Hebr).

## Source URLs (verified 2026-08-10)

- https://www.w3.org/International/articles/inline-bidi-markup/
- https://www.unicode.org/reports/tr9/
- https://developer.mozilla.org/en-US/docs/Web/HTML/Global_attributes/dir
- https://developer.mozilla.org/en-US/docs/Web/HTML/Element/bdi
- https://trojansource.codes/
