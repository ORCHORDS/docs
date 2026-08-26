# rtl-bidi-handling

**Issue:** A form in Arabic shows labels on the wrong side, numbers inside Arabic text display in reverse order, and a back-arrow icon points the wrong way. The page works in English; it ships broken in Arabic, Hebrew, Farsi, and Urdu.
**Date:** 2026-08-10
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Symptom

Right-to-left languages (Arabic, Hebrew, Farsi, Urdu, plus others using Arabic or Hebrew scripts) need a mirrored layout: text flows right-to-left, alignment flips, icons that point forward in LTR must point backward in RTL, and mixed-direction text (LTR email in an RTL paragraph) needs explicit handling. Most LTR-only codebases break all of these by default.

## Root cause

Three structural issues:

1. **Physical CSS properties.** `margin-left`, `padding-right`, `text-align: left` are direction-agnostic in syntax but direction-specific in effect. In RTL, the "left" of the box is the "right" of the reader.
2. **Directional icons.** A back arrow pointing left in LTR must point right in RTL. A progress indicator that fills left-to-right must fill right-to-left.
3. **Mixed-direction text.** A price `$49.00` or a phone number `+1 555-1234` embedded in Arabic text needs to be isolated so digits and symbols don't get reordered by the Unicode Bidirectional Algorithm.

## The `dir` attribute is the primary mechanism

The `dir` attribute on the HTML element sets the base direction for the document:

```html
<html dir="rtl" lang="ar">
```

All block elements inherit this setting unless explicitly overridden. For pages that are mostly LTR but contain some RTL content (or vice versa), set `dir="rtl"` on the specific elements that need it.

The W3C and MDN explicitly recommend the HTML `dir` attribute over the CSS `direction` property for setting base direction. Do not use `direction: rtl` in CSS to set the page's base direction; use `dir="rtl"` on the element.

For user-generated content where direction is unknown, use `dir="auto"` — the browser infers direction from the first strongly-typed character.

## The CSS logical properties pattern

Modern CSS provides logical properties that automatically adapt to writing mode and direction, replacing physical properties with logical ones:

| Physical | Logical | LTR | RTL |
|---|---|---|---|
| `margin-left` | `margin-inline-start` | `margin-left` | `margin-right` |
| `margin-right` | `margin-inline-end` | `margin-right` | `margin-left` |
| `padding-left` | `padding-inline-start` | `padding-left` | `padding-right` |
| `padding-right` | `padding-inline-end` | `padding-right` | `padding-left` |
| `border-left` | `border-inline-start` | `border-left` | `border-right` |
| `left: 0` | `inset-inline-start: 0` | `left: 0` | `right: 0` |
| `text-align: left` | `text-align: start` | `text-align: left` | `text-align: right` |

The inline axis runs in the text direction (LTR or RTL); the block axis runs perpendicular. `margin-inline-start` automatically maps to the left in LTR and the right in RTL — so one stylesheet serves both directions with no `[dir="rtl"]` overrides.

This is the modern replacement for maintaining separate LTR/RTL CSS. Use logical properties by default, even in LTR-only products — they are future-proofing for free.

## The mixed-direction content pattern

When LTR content (email, URL, number, code) is embedded in RTL text, the Unicode Bidirectional Algorithm can scramble the order. Two solutions:

**HTML isolation with `<bdi>`:**

```html
<p>
  البريد الإلكتروني: <bdi>user@example.com</bdi>
</p>
```

The `<bdi>` element isolates the content, preventing direction spillover. The browser treats the email as a separate directional run.

**Unicode bidi control characters:**

| Character | Code | Use |
|---|---|---|
| LRM (Left-to-Right Mark) | U+200E | Force LTR in ambiguous context |
| RLM (Right-to-Left Mark) | U+200F | Force RTL in ambiguous context |
| LRE / RLE / PDF | U+202A / U+202B / U+202C | Embedding (rarely needed in modern code) |

```javascript
const arabicWithEmail = `البريد الإلكتروني: ‪user@example.com‬`
// Forces email to stay LTR within RTL context
```

Prefer `<bdi>` over Unicode control characters in modern code. The HTML form is auditable; the Unicode form is invisible in source.

## The directional icons pattern

Icons that imply direction (back arrow, forward arrow, progress bar) must mirror in RTL. Two patterns:

**CSS `transform: scaleX(-1)`:**

```css
[dir="rtl"] .icon-back {
  transform: scaleX(-1);
}
```

Quick and dirty. Works for symmetric icons (back arrow, chevron). Does not work for asymmetric icons (a car pointing forward, a hand pointing right).

**Per-direction asset:**

```html
<img class="icon-back"  alt="Back" />
```

```css
[dir="rtl"] .icon-back { content: url(back-rtl.svg); }
```

Cleaner. Required for asymmetric icons. Two assets to maintain.

**Unicode bidi-isolated emoji:** Some emoji are inherently directional (← →). Modern browsers handle them in bidi context; don't try to override.

Numbers, logos, and orientation-fixed glyphs (a clock face, a music note) must NOT mirror in RTL. Test that the clock still shows 3 on the right.

## The empty/error/success state mirroring

Error icons, empty-state illustrations, and CTA alignment flip in RTL. A "no results" illustration with a magnifying glass on the left needs the magnifying glass on the right. An error message with a left-aligned red icon needs right-alignment in RTL.

This is the most-missed direction-aware pattern. Test the empty state, the error state, the success state, and the loading state in a real RTL locale (Arabic or Hebrew), not by translating strings alone.

## The first-render discipline

Set `dir` from the first render. Do not render LTR then snap to RTL — the user sees a flash of wrong-direction content before the locale is detected.

```html
<!DOCTYPE html>
<html lang="ar" dir="rtl">
  <!-- server-rendered with correct dir to avoid LTR flash -->
</html>
```

The `dir` attribute is determined server-side from the user's preferred locale (or `Accept-Language` header), then the full HTML is rendered with the correct direction from byte one. RTL flash is a real UX bug.

## Verification

The tell that RTL is working:

- Set the device language to Arabic or Hebrew; every screen mirrors correctly
- Mixed-direction content (emails, phone numbers, prices) is isolated and reads correctly
- Directional icons (back, forward, progress) flip where they should and don't flip where they shouldn't (logos, numbers)
- The first render is RTL; no LTR flash
- Empty/error/loading states mirror

The tell it isn't:

- A back arrow points the wrong way
- An email inside Arabic text shows in reverse character order
- Layout breaks on first render then snaps to RTL
- A "next" button stays on the right in RTL when it should be on the left

## Gotchas

- **Set `dir` on the element, not via CSS `direction` property.** The W3C and MDN are explicit on this.
- **Use `dir="auto"` for user-generated content of unknown language.** The browser infers from the first strongly-typed character.
- **Numbers, logos, and orientation-fixed glyphs do NOT mirror.** Test asymmetric icons carefully.
- **`<bdi>` is the modern way to isolate direction in inline content.** Use it over Unicode bidi controls in HTML.
- **The first-render direction matters.** Render RTL on the server. Do not let the client flash LTR before redirecting.
- **Empty, error, success, and loading states must be tested in a real RTL locale.** They are the most-missed mirrors.

## Related

- `i18n/icu-message-format.md` — MessageFormat strings preserve direction with `dir`
- `i18n/locale-negotiation.md` — choosing which locale to set `dir` from
- `i18n/pseudo-localization.md` — RTL pseudo-locale surfaces direction bugs

## Source URLs (verified 2026-08-10)

- https://intlpull.com/blog/rtl-language-support-arabic-hebrew-guide-2026
- https://www.w3.org/International/questions/qa-html-dir.en.html
- https://www.w3.org/TR/css-writing-modes-4/
- https://developer.mozilla.org/en-US/docs/Web/CSS/Reference/Properties/direction
- https://www.tyrs.studio/wiki/10-content-design/rtl-and-bidirectional.html
