# vertical-writing-modes-typography

**Issue:** Most web platforms treat horizontal left-to-right layout as the only writing direction, but Japanese traditional print (tategaki), traditional Chinese, Korean vertical typesetting, and Mongolian script are written vertically with columns flowing right-to-left (or left-to-right for Mongolian). When a product localizes for Japanese markets — long-form reading apps, digital novels, museum exhibits, signage, or decorative headings — the standard flexbox/grid layouts break: text overflows horizontally, punctuation renders on the wrong side of the column, Latin fragments and numerals rotate incorrectly, and line-breaking rules (kinsoku shori) differ from horizontal mode. The engineering problem is implementing CSS Writing Modes Level 4 correctly so that vertical-rl containers, logical properties, text orientation, and tate-chū-yoko (horizontal-in-vertical numerals) all compose without a per-page hack, while keeping horizontal locales unaffected.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Core CSS mechanics

1. **writing-mode is the root switch.** Set writing-mode: vertical-rl on the reading container for Japanese tategaki — block flow becomes right-to-left columns, and inline flow runs top-to-bottom. Per the W3C i18n guide on styling vertical CJK and Mongolian text, use vertical-lr only for Mongolian (and traditional vertically-set Korean manhwa), never for Japanese. Apply it on a content wrapper, not the html element, so chrome around the reading surface stays horizontal.
2. **text-orientation controls Latin behavior.** The default mixed orientation rotates Latin fragments and digits 90 degrees to run down the column, which is correct for Japanese prose. Use text-orientation: upright when Latin characters must remain upright side-by-side in the column (common for brand names, or when following guidance for tategaki display text); apply it to spans, not whole documents, since upright Latin reads poorly in long passages.
3. **tate-chū-yoko for short numerals.** Two- and three-digit numbers and years compress horizontally inside a vertical column via text-combine-upright: all on the containing span. This is typographically required for dates like "2026" in vertical Japanese; without it, four rotated digits are hard to read.
4. **Logical properties, not physical ones.** In vertical mode, margin-left becomes the block-end direction and width/height swap roles. Use margin-block/margin-inline, padding-block/padding-inline, inline-size/block-size, and border-block/border-inline throughout the component library so the same stylesheet works in both modes. A single physical margin-top in a shared card component silently breaks the vertical layout.
5. **Punctuation and kinsoku still apply.** Browsers apply Japanese line-breaking prohibitions (kinsoku shori) in vertical mode automatically — certain characters may not start or end a line — but only when the lang attribute is set correctly (lang="ja"). Mis-tagged Japanese content as lang="zh" changes both hyphenation-adjacent breaking and quotation mark orientation.

## Layout and interaction consequences

1. **Scrolling direction flips.** In vertical-rl, the natural block overflow direction is leftward: the beginning of the document is at the right edge. Horizontal scroll containers must be authored with logical scroll APIs or tested explicitly, because scrollLeft semantics differ across browsers in vertical writing modes (some report negative values). Prefer overflow with logical handling and test with Puppeteer assertions on visual output, not scrollLeft arithmetic.
2. **Progress indicators and pagination.** Reading progress "top to bottom" becomes "right to left" for Japanese vertical readers. Any progress bar, stepper, or carousel that assumes left-to-right progression must invert for vertical-rl and rtl contexts; derive direction from the writing mode via CSS logical inset properties and getComputedWritingMode checks in tests.
3. **Form controls can go vertical.** Chrome supports vertical writing modes on form controls (buttons, inputs), but older Safari/Firefox render them horizontally regardless. Wrap button labels rather than fighting the control: keep the control horizontal and set the label span to vertical-rl where the platform cannot.
4. **Selection, caret, and accessibility.** Screen readers announce vertical text correctly only when the DOM order matches the logical reading order, which it does naturally — never reorder DOM nodes to match visual column order. The caret moves down the column and jumps left to the next column; test text entry components with real Japanese IME input in vertical mode before shipping.

## Fonts and rendering pitfalls

1. **Mincho/Gothic vertical variants.** Japanese fonts carry vert OpenType features that substitute punctuation and brackets into vertical forms (、、 「」 rotated corner brackets). Verify the chosen webfont includes vert glyph variants; some Latin-heavy fallback stacks omit them and render vertical Japanese punctuation sideways or in the wrong position.
2. **Fallback stack order matters more in vertical mode.** A missing glyph falls back to a horizontal-only Latin font, which then rotates 90 degrees in mixed orientation and looks broken. Order the stack: Japanese font first, then Latin, and test with a synthetic missing-glyph fixture.
3. **Line height resolves differently.** In vertical-rl, line-height controls column gap (the inline-axis spacing becomes visual width between columns). Tune it against the font's metrics; default line-height: normal in Mincho fonts often produces cramped columns. The CSS line-height: 1 is common for Japanese vertical prose.
4. **Subsetting with vert features intact.** CJK subsetting pipelines strip glyphs deemed unused; ensure the subsetter keeps vertical substitution features (vert, vrt2) or vertical punctuation will lose its rotated forms in production despite working locally with the full font.

## Testing strategy

1. **Visual regression per writing mode.** Add a screenshot suite that renders the same components in horizontal-tb, vertical-rl, and (if Mongolian is in scope) vertical-lr. Vertical layout bugs are visual by nature; unit assertions on class names will not catch a column that overflows.
2. **A vertical pseudolocale.** Extend pseudo-localization tooling with a vertical-rl wrapper mode so English-speaking developers exercising the layout daily see their components in vertical orientation with readable pseudo text — the vertical equivalent of pseudo-RTL testing.
3. **Cross-browser matrix.** Chromium, Firefox, and WebKit differ in text-orientation edge cases, combined numerals, and vertical form-control support. Test the actual reading surface in all three plus iOS Safari; vertical-rl is a first-class layout on Japanese mobile, where WebKit quirks directly hit users.
4. **Readability review by native readers.** Automated tests prove geometry, not typography. Have a Japanese reader confirm column order, punctuation placement, and tate-chū-yoko usage on real content before launch — the difference between technically-vertical and correctly-typeset vertical text is exactly what native review catches.
