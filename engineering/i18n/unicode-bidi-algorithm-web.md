# Unicode Bidi Algorithm on the Web

**Date:** 2026-08-17
**Author:** the platform team
**Status:** published

## Symptom

A filename, username, or UI label containing RTL characters
renders with digits and punctuation in the wrong order, or
an attacker uses a hidden RTL override character to disguise
a malicious filename as something safe.

## Context

The Unicode Bidirectional Algorithm (UBA, Unicode Standard
Annex #9) determines display order for text that mixes
left-to-right and right-to-left characters. Browsers run it
automatically on every text node. Misunderstanding the UBA
leads to rendering bugs in mixed-direction UI and to the
Trojan-source / RTLO security vulnerability in user-generated
content.

## 1. How browsers apply the Bidi Algorithm

The UBA works in two passes. First it infers the base
direction of each paragraph (from the first strong-directional
character, or from the `dir` attribute). Then it resolves
the display order of every character using the character's
Unicode Bidi category (L, R, AL, AN, EN, NSM, B, S, WS, ON).

Key categories:

| Category | Meaning            | Examples              |
|----------|--------------------|-----------------------|
| L        | Strong left        | Latin, Cyrillic       |
| R        | Strong right       | Hebrew                |
| AL       | Arabic letter      | Arabic, Thaana        |
| AN       | Arabic number      | ٠١٢٣ (Arabic-Indic)  |
| EN       | European number    | 0–9, $                |
| NSM      | Non-spacing mark   | Combining diacritics  |

The HTML `dir` attribute and the CSS `direction` property
set the paragraph base direction, overriding UBA inference.

## 2. The `unicode-bidi` CSS property

`unicode-bidi` controls how the element participates in
bidi layout. It is almost always paired with `direction`.

```css
.bdi-manual { unicode-bidi: isolate; }   /* like <bdi> */
.force-rtl  { direction: rtl;
              unicode-bidi: bidi-override; } /* like <bdo> */
```

| Value           | Effect                                      |
|-----------------|---------------------------------------------|
| `normal`        | Default; participates in surrounding flow   |
| `bidi-override` | Overrides implicit bidi directions          |
| `isolate`       | Directionally neutral to surrounding text   |

Prefer the HTML elements `<bdi>` and `<bdo>` — they are
more readable and carry semantic meaning.

## 3. `<bdi>` and `<bdo>` HTML elements

`<bdi>` (Bidirectional Isolate) wraps content whose
direction is unknown at render time, isolating it from
the surrounding context. Use it for user-generated text,
product names, and dynamic strings.

```html
<!-- Without <bdi>: "by JohnDoe" may render as
     "by eoDnhoJ" if the name contains RTL chars -->
<p>Posted by <bdi>JohnDoe</bdi> at 10:00</p>

<!-- Currency in an Arabic sentence -->
<p dir="rtl">السعر: <bdi>$1,234.56</bdi></p>
```

`<bdo>` (Bidirectional Override) forces a specific
direction, overriding the UBA entirely.

```html
<!-- Force RTL regardless of character categories -->
<bdo dir="rtl">This text renders reversed</bdo>
```

Use `<bdo>` only when you need to display text in a
specific visual order that differs from its logical order
(rare; mostly for display of encoded text).

## 4. Security: RTL override characters in UGC

Unicode contains explicit directional override characters
(U+202E RIGHT-TO-LEFT OVERRIDE, U+200F RIGHT-TO-LEFT MARK,
U+202B RIGHT-TO-LEFT EMBEDDING, and the newer Bidi isolate
controls U+2066–U+2069). An attacker can embed these in
a filename, commit message, or username to disguise content.

Classic RTLO attack (Trojan Source):

```
File displayed as: "doc.txt"
Actual bytes:      "doc[U+202E]txt.exe"
```

The U+202E forces everything after it to render RTL, so
`txt.exe` visually reverses to `exe.txt` — the user sees
`doc.exe.txt` rendered as `doc.txt.exe`.

**Mitigations:**

```javascript
// Strip bidi control characters from user input
const BIDI_CONTROLS = /[‎‏‪-‮⁦-⁩]/g;
function sanitizeBidi(str) {
  return str.replace(BIDI_CONTROLS, '');
}

// Or escape them for display
function escapeBidi(str) {
  return str.replace(BIDI_CONTROLS, (c) =>
    `&#x${c.codePointAt(0).toString(16).toUpperCase()};`
  );
}
```

Always wrap user-generated strings in `<bdi>` even after
sanitization — `<bdi>` provides a fallback isolation layer.

## 5. Common rendering bugs

- **Number reordering in mixed text.** A phone number
  inside an RTL paragraph may flip its digit order. Fix:
  wrap the number in `<bdi>`.
- **Punctuation at the wrong end.** A `!` at the end of
  a sentence inside an RTL context moves to the visual
  left. Fix: set `dir` explicitly on the container.
- **Neutral characters inheriting wrong direction.** Spaces,
  hyphens, and slashes between LTR and RTL runs inherit
  direction from adjacent strong characters. Fix: use `<bdi>`
  or an explicit `dir` attribute on the inner element.
- **`dir="auto"` over-triggering.** An Arabic product name
  in a Latin paragraph flips the whole paragraph. Fix:
  wrap the dynamic value in `<bdi>` instead.

## Anti-patterns

- Displaying user-supplied filenames, usernames, or URLs
  without `<bdi>` wrapping or bidi-control sanitization.
- Using `direction: rtl; unicode-bidi: bidi-override` on
  all RTL containers — overrides prevent correct mixed-
  direction rendering within the element.
- Stripping bidi controls as the only security measure
  without also wrapping output in `<bdi>`.
- Setting `dir="auto"` on `<body>` or large containers.

## Gotchas

- Bidi control characters are invisible — standard text
  diffs and `console.log` will not reveal them. Use a
  hex dump or `[...str].map(c => c.codePointAt(0).toString(16))`
  to inspect.
- `<bdi>` does not strip bidi controls; it only isolates
  them from the surrounding visual context.
- The UBA is a display algorithm. Logical string operations
  (`.slice()`, `.indexOf()`) operate on codepoint order,
  not visual order.
- `unicode-bidi: isolate` (CSS) is equivalent to `<bdi>`;
  `unicode-bidi: bidi-override` is equivalent to `<bdo>`.

## Verification

- Render a string containing `U+202E` in a `<bdi>`; the
  surrounding paragraph direction must not change.
- Attempt to submit a filename with `U+202E` via a form;
  verify the sanitizer strips it before persistence.
- Use browser DevTools "Rendering → Force dark mode" trick
  or the Unicode Bidi Visualizer tool to inspect runs.
- Run `eslint-plugin-i18n-text` with bidi-control checks
  enabled in CI.

## Related

- `i18n/bidi-algorithm-unicode.md`
- `i18n/rtl-css-layout-patterns.md`
- `i18n/arabic-persian-text-rendering.md`
- `i18n/i18n-rtl-testing-2026.md`

## Source URLs (verified 2026-08-17)

- https://unicode.org/reports/tr9/
- https://developer.mozilla.org/en-US/docs/Web/HTML/Element/bdi
- https://developer.mozilla.org/en-US/docs/Web/CSS/unicode-bidi
- https://trojansource.codes/
- https://www.w3.org/International/articles/inline-bidi-markup/
