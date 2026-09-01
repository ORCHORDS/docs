# CSS Text Wrap Balance Headlines

## Scope

Using `text-wrap: balance` on headlines, card titles, and callouts to distribute wrapped lines more evenly instead of leaving a stranded last word. Covers where balancing pays off, where it must not be used (long paragraphs), interaction with container queries and dynamic content, and the related `text-wrap: pretty` for orphans in body copy. Excludes hyphenation control (`hyphens`) and manual `<wbr>`/`&shy;` insertion except as fallbacks.

## Workflow or implementation guidance

Default line breaking is greedy: the browser fills each line as far as possible, so a two-line headline often ends with a one- or two-word second line. Balanced wrapping runs a line-breaking pass that considers the whole block and distributes the text.

Apply it selectively, by element role, and only to short multi-line candidates.

```css
h1, h2, .headline, .card__title {
  text-wrap: balance;
}

.lede, .card__summary {
  text-wrap: pretty;
}
```

The cost model matters. Balancing is more expensive than greedy breaking because the layout engine evaluates alternatives across the block. Browsers cap the number of lines that will be balanced (implementations limit balancing to a handful of lines and a bounded text length), which is exactly why the feature is safe on headlines and wrong on paragraphs. Do not write a blanket `* { text-wrap: balance }` reset.

Where it composes best is dynamic layouts: a title inside a container that changes width with a container query, a card grid where column count shifts between breakpoints, or localized strings whose length varies by locale. Balanced wrapping re-runs on resize, so a headline that fits one line at wide widths and three lines at narrow widths stays evenly distributed without JavaScript measurement or server-side string tuning.

```css
.card {
  container-type: inline-size;
}

@container (max-width: 280px) {
  .card__title { font-size: 1.05rem; }
  .card__title { text-wrap: balance; } /* re-balances per container width */
}
```

Contrast with `text-wrap: pretty`, which targets the orphans-and-widows problem in longer text — it primarily avoids a single word alone on the last line — and is the right value for paragraphs and summaries. `balance` optimizes line-length equality for short blocks; `pretty` optimizes the tail of longer blocks.

Fallback is graceful: unsupported engines keep greedy wrapping, so the declaration needs no `@supports` guard unless the design depends on balance for a hard requirement. When a layout must not show a stranded word in older browsers, the remaining options are editorial: shorten the copy, or insert a `<br>` at the designed break point and accept that it overrides balancing in browsers that do support it (an explicit break wins over the balancer).

Interaction with truncation: `text-overflow: ellipsis` and balancing do not combine meaningfully; ellipsis applies to single-line overflow (`white-space: nowrap`), while balancing applies to wrapped multi-line text. For clamped summaries, keep `line-clamp` and use `pretty`, not `balance`, because clamped blocks end mid-text and balancing a clamped block can pull the ellipsis onto a shorter line than intended.

Vertical rhythm note: balancing changes line count in edge cases, so components that reserve fixed height for a headline should reserve for the maximum plausible line count rather than the greedy-wrapping count, or rely on the balanced result being equal or shorter in height.

## Controls

- `text-wrap: balance` on headline-class elements only (typically up to about six rendered lines).
- `text-wrap: pretty` on body copy, summaries, and clamped text.
- No global selector reset applying balance; enforce via a stylelint selector-pattern or code review checklist.
- Fixed-height headline containers sized to the maximum line count, not the greedy count.
- Locale QA pass for translated headlines, since balanced results differ by language and script.

## Validation evidence

- Screenshot-diff each headline at the narrowest supported viewport width and at the container-query boundary; assert visually that no line is shorter than roughly half the longest line.
- Measure layout time on a headline-heavy page (for example a news index) before and after, using performance traces; confirm no regression at the p95 long-task bucket.
- Verify unsupported browsers fall back to greedy wrapping without console errors by testing an engine without the feature.
- Check with localized builds (long-locale and short-locale) that balance still produces acceptable shapes; line-break opportunities differ by script.

## Failure modes and correction

- Applied to paragraphs: layout cost grows and results look uneven because the browser caps the balanced line count. Restrict to short blocks.
- Stranded word persists: the element has a `white-space` or `width` constraint (for example `nowrap`, an inline-block, or a float) that prevents multi-line breaking; fix the constraint rather than the wrap mode.
- `<br>` inserted for old browsers overrides the balancer in new ones and produces an odd short line. Remove the hard break once the support floor includes balancing, or gate the break behind an `@supports not (text-wrap: balance)` block.
- Headline jumps by one line between layouts and overlaps a sibling in a fixed-height grid. Reserve height for the max line count or let the row grow.
- Balance fights justified text: `text-align: justify` with balancing produces stretched inter-word spacing on the balanced lines; keep balanced headlines left- or center-aligned.
- Clamped (`-webkit-line-clamp`) blocks balanced unexpectedly: switch to `pretty` or drop balance on clamped components.

## Limitations

- Balancing is capped by implementations to a small number of lines and bounded text length; long blocks silently get greedy behavior for the tail.
- `pretty` is a separate value shipping separately from `balance`; support matrices differ between them and between engines.
- Only affects inline-level wrapping of the element's own text content; it does not reflow floats, exclusions, or shaped text around images.
- No direct control over the target line count or balance ratio; the algorithm's notion of "balanced" is not author-tunable.
- Vertical-writing-mode and mixed-script blocks may balance differently or not at all in some engines; verify per locale.

## Canonical sources

- CSS Working Group, CSS Text Module Level 4, `text-wrap`: https://drafts.csswg.org/css-text-4/#text-wrap
- MDN, `text-wrap` property: https://developer.mozilla.org/en-US/docs/Web/CSS/text-wrap
- MDN, CSS text module overview: https://developer.mozilla.org/en-US/docs/Web/CSS/CSS_containment
